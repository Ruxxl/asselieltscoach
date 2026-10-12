"""Копия важных данных в Google Таблице (через Apps Script из sheets/apps_script.gs).

SQLite на Render free стирается при каждом деплое и перезапуске, поэтому учеников, покупки курсов,
платежи Halyk и прогресс по урокам сервер дублирует в Таблицу, а при старте восстанавливает из неё.
Рабочей базой остаётся SQLite: Таблица медленная (1–3 с на запрос) и с лимитами, читать из неё
на каждый запрос нельзя.

Запись — после успешного commit (событие сессии), через фоновую очередь с повторами, чтобы
ответ ученику не ждал Google. Курсы храним кодом (B55), а не id: id зависят от порядка сидинга.
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime

import aiohttp
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.config import SHEETS_ENABLED, SHEETS_SECRET, SHEETS_WEBHOOK_URL
from backend.database import SessionLocal
from backend.models import Course, CoursePurchase, LessonProgress, Payment, User

logger = logging.getLogger(__name__)

SHEETS = ["users", "purchases", "payments", "lesson_progress"]
_TIMEOUT = aiohttp.ClientTimeout(total=60)
_BATCH = 50

_queue: asyncio.Queue[tuple[str, dict]] | None = None
_worker_task: asyncio.Task | None = None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ", timespec="seconds") if value else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _snapshot(obj, is_new: bool) -> tuple[str, dict] | None:
    """Строка для Таблицы из объекта модели. created_at с server_default после flush ещё не
    загружен (и подгрузить его в событии нельзя) — поэтому для новых строк берём текущее время."""
    now = _iso(datetime.utcnow())
    if isinstance(obj, User):
        row = {"key": str(obj.id), "id": obj.id, "username": obj.username, "full_name": obj.full_name, "level": obj.level}
        sheet = "users"
    elif isinstance(obj, CoursePurchase):
        row = {"user_id": obj.user_id, "course_id": obj.course_id, "price_paid": obj.price_paid}
        sheet = "purchases"
    elif isinstance(obj, LessonProgress):
        row = {"key": f"{obj.user_id}:{obj.lesson_id}", "user_id": obj.user_id, "lesson_id": obj.lesson_id}
        sheet = "lesson_progress"
    elif isinstance(obj, Payment):
        # secret_hash не пишем: Таблицу видит больше людей, чем сервер. После восстановления
        # postLink по старым заказам проигнорируется, а статус всё равно сверится с банком.
        row = {
            "key": obj.invoice_id,
            "id": obj.id,
            "user_id": obj.user_id,
            "course_id": obj.course_id,
            "amount_kzt": obj.amount_kzt,
            "invoice_id": obj.invoice_id,
            "status": obj.status,
            "provider_status": obj.provider_status,
            "provider_reference": obj.provider_reference,
            "card_mask": obj.card_mask,
            "failure_reason": obj.failure_reason,
            "paid_at": _iso(obj.paid_at),
        }
        sheet = "payments"
    else:
        return None
    if is_new:
        row["created_at"] = now
    row["updated_at"] = now
    return sheet, row


@event.listens_for(Session, "after_flush")
def _collect(session: Session, flush_context) -> None:
    if not SHEETS_ENABLED or session.info.get("sheets_skip"):
        return
    pending = session.info.setdefault("sheets_pending", [])
    for obj in session.new:
        snap = _snapshot(obj, is_new=True)
        if snap:
            pending.append(snap)
    for obj in session.dirty:
        if session.is_modified(obj):
            snap = _snapshot(obj, is_new=False)
            if snap:
                pending.append(snap)


@event.listens_for(Session, "after_commit")
def _enqueue(session: Session) -> None:
    pending = session.info.pop("sheets_pending", None)
    if not pending or _queue is None:
        return
    for item in pending:
        _queue.put_nowait(item)


@event.listens_for(Session, "after_rollback")
def _drop(session: Session) -> None:
    session.info.pop("sheets_pending", None)


async def _call(payload: dict) -> dict:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        # Apps Script отвечает редиректом на googleusercontent.com — aiohttp идёт по нему сам.
        async with http.post(SHEETS_WEBHOOK_URL, json={"secret": SHEETS_SECRET, **payload}) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Sheets webhook HTTP {resp.status}: {body[:300]}")
    try:
        data = json.loads(body)
    except ValueError:
        raise RuntimeError(f"Sheets webhook returned non-JSON: {body[:300]}")
    if not data.get("ok"):
        raise RuntimeError(f"Sheets webhook error: {data.get('error')}")
    return data


async def _course_codes() -> dict[int, str]:
    async with SessionLocal() as session:
        rows = await session.execute(select(Course.id, Course.code))
        return {course_id: code for course_id, code in rows.all()}


async def _send(sheet: str, rows: list[dict]) -> None:
    if any("course_id" in r for r in rows):
        codes = await _course_codes()
        for r in rows:
            if "course_id" in r:
                r["course_code"] = codes.get(r.pop("course_id"), "")
                if sheet == "purchases":
                    r["key"] = f"{r['user_id']}:{r['course_code']}"
    delay = 2
    for attempt in range(8):
        try:
            await _call({"action": "upsert", "sheet": sheet, "rows": rows})
            return
        except Exception as e:
            logger.warning("Sheets upsert to %s failed (attempt %s): %s", sheet, attempt + 1, e)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
    # Не дошло после всех попыток — хотя бы оставляем строки в логах Render, чтобы внести руками.
    logger.error("Sheets upsert to %s gave up, rows: %s", sheet, rows)


async def _worker() -> None:
    assert _queue is not None
    while True:
        first = await _queue.get()
        batch = [first]
        while len(batch) < _BATCH and not _queue.empty():
            batch.append(_queue.get_nowait())
        # Несколько изменений одной строки подряд склеиваем в одно — поля последнего важнее.
        by_sheet: dict[str, dict[str, dict]] = {}
        for sheet, row in batch:
            rows = by_sheet.setdefault(sheet, {})
            key = row.get("key") or f"{row.get('user_id')}:{row.get('course_id')}"
            rows[key] = {**rows.get(key, {}), **row}
        for sheet, rows in by_sheet.items():
            await _send(sheet, list(rows.values()))
        for _ in batch:
            _queue.task_done()


def start() -> None:
    global _queue, _worker_task
    if not SHEETS_ENABLED or _worker_task:
        return
    _queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_worker())


async def stop() -> None:
    """При остановке (деплой) даём очереди дописаться, но не дольше 20 с."""
    global _worker_task
    if not _worker_task or _queue is None:
        return
    try:
        await asyncio.wait_for(_queue.join(), timeout=20)
    except asyncio.TimeoutError:
        logger.error("Sheets queue not flushed on shutdown, %s items lost", _queue.qsize())
    _worker_task.cancel()
    _worker_task = None


async def restore(session: AsyncSession) -> None:
    """Заливает в пустую после деплоя SQLite то, что есть в Таблице. Уже существующие строки не трогает."""
    if not SHEETS_ENABLED:
        return
    data = None
    for attempt in range(3):
        try:
            data = (await _call({"action": "dump", "sheets": SHEETS}))["data"]
            break
        except Exception as e:
            logger.warning("Sheets restore failed (attempt %s): %s", attempt + 1, e)
            await asyncio.sleep(3)
    if data is None:
        logger.error("Sheets restore gave up — app starts without restored purchases")
        return

    session.info["sheets_skip"] = True
    try:
        code_to_id = {code: cid for cid, code in (await _course_codes()).items()}

        users = 0
        for r in data.get("users") or []:
            if not r.get("id") or await session.get(User, int(r["id"])):
                continue
            session.add(
                User(
                    id=int(r["id"]),
                    username=r.get("username"),
                    full_name=r.get("full_name"),
                    level=r.get("level"),
                    created_at=_parse_dt(r.get("created_at")) or datetime.utcnow(),
                )
            )
            users += 1
        await session.flush()

        owned = {(u, c) for u, c in (await session.execute(select(CoursePurchase.user_id, CoursePurchase.course_id))).all()}
        purchases = 0
        for r in data.get("purchases") or []:
            course_id = code_to_id.get(r.get("course_code") or "")
            if not course_id or not r.get("user_id"):
                if r.get("course_code"):
                    logger.error("Sheets restore: unknown course %s for user %s", r.get("course_code"), r.get("user_id"))
                continue
            pair = (int(r["user_id"]), course_id)
            if pair in owned:
                continue
            session.add(
                CoursePurchase(
                    user_id=pair[0],
                    course_id=course_id,
                    price_paid=int(float(r.get("price_paid") or 0)),
                    created_at=_parse_dt(r.get("created_at")) or datetime.utcnow(),
                )
            )
            owned.add(pair)
            purchases += 1

        done = {(u, l) for u, l in (await session.execute(select(LessonProgress.user_id, LessonProgress.lesson_id))).all()}
        progress = 0
        for r in data.get("lesson_progress") or []:
            if not r.get("user_id") or not r.get("lesson_id"):
                continue
            pair = (int(r["user_id"]), int(r["lesson_id"]))
            if pair in done:
                continue
            session.add(
                LessonProgress(
                    user_id=pair[0],
                    lesson_id=pair[1],
                    completed_at=_parse_dt(r.get("created_at")) or datetime.utcnow(),
                )
            )
            done.add(pair)
            progress += 1

        known = set((await session.execute(select(Payment.invoice_id))).scalars().all())
        payments = 0
        for r in data.get("payments") or []:
            course_id = code_to_id.get(r.get("course_code") or "")
            if not r.get("invoice_id") or r["invoice_id"] in known or not course_id:
                continue
            session.add(
                Payment(
                    # Тот же id: он в backLink (?payment=<id>), если ученик платил как раз во время деплоя.
                    id=int(r["id"]) if r.get("id") else None,
                    user_id=int(r["user_id"]),
                    course_id=course_id,
                    amount_kzt=int(float(r.get("amount_kzt") or 0)),
                    invoice_id=r["invoice_id"],
                    secret_hash=secrets.token_hex(16),
                    status=r.get("status") or "pending",
                    provider_status=r.get("provider_status"),
                    provider_reference=r.get("provider_reference"),
                    card_mask=r.get("card_mask"),
                    failure_reason=r.get("failure_reason"),
                    created_at=_parse_dt(r.get("created_at")) or datetime.utcnow(),
                    paid_at=_parse_dt(r.get("paid_at")),
                )
            )
            known.add(r["invoice_id"])
            payments += 1

        await session.commit()
        logger.info(
            "Sheets restore: %s users, %s purchases, %s lesson progress, %s payments",
            users, purchases, progress, payments,
        )
    finally:
        session.info.pop("sheets_skip", None)
