"""Покупка курса через Halyk ePay (платёжная страница банка, см. backend/services/halyk.py).

1. POST /api/payments/courses/{code} — создаём заказ, берём у банка токен, отдаём фронтенду объект
   для halyk.pay(); тот уводит ученика на страницу Halyk.
2. Банк шлёт результат на POST /api/payments/halyk/postlink; ученик возвращается в мини-апп на
   backLink/failureBackLink (?payment=<id>) и опрашивает GET /api/payments/{id}.
3. Оплаченным заказ считаем, только когда check-status банка вернул CHARGE/AUTH с нашей суммой, —
   тогда создаётся CoursePurchase, по которой открываются уроки.
"""

import hmac
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_user
from backend.config import HALYK_ENABLED, HALYK_TERMINAL_ID, WEBAPP_URL
from backend.database import get_session
from backend.models import Course, CoursePurchase, Payment
from backend.schemas import PaymentStartOut, PaymentStatusOut
from backend.services import halyk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


def _base_url() -> str:
    return WEBAPP_URL.rstrip("/")


async def _grant_course(session: AsyncSession, user_id: int, course_id: int, price: int) -> None:
    already = await session.execute(
        select(CoursePurchase.id).where(CoursePurchase.user_id == user_id, CoursePurchase.course_id == course_id)
    )
    if not already.first():
        session.add(CoursePurchase(user_id=user_id, course_id=course_id, price_paid=price))


async def _sync_with_bank(session: AsyncSession, payment: Payment) -> None:
    """Сверяем заказ со статусом транзакции в банке; при подтверждённой оплате выдаём курс.
    failed тоже сверяем: на странице банка ученик может после отказа повторить оплату тем же заказом."""
    if payment.status == "paid":
        return
    try:
        tx = await halyk.fetch_transaction(payment.invoice_id)
    except Exception:
        logger.exception("Halyk check-status failed for payment %s", payment.id)
        return
    if not tx:
        return
    status_name = str(tx.get("statusName") or "").upper()
    payment.provider_status = status_name or None
    payment.provider_reference = tx.get("reference") or payment.provider_reference
    payment.card_mask = tx.get("cardMask") or payment.card_mask
    if status_name in halyk.PAID_STATUSES:
        amount_ok = round(float(tx.get("amount") or 0)) == payment.amount_kzt
        currency_ok = (tx.get("currency") or halyk.CURRENCY) == halyk.CURRENCY
        terminal_ok = (tx.get("terminalID") or HALYK_TERMINAL_ID) == HALYK_TERMINAL_ID
        if not (amount_ok and currency_ok and terminal_ok):
            # Не выдаём курс: в банке не та сумма/валюта/терминал, что мы выставили. Разбираться вручную.
            logger.error("Halyk transaction mismatch for payment %s: %s", payment.id, tx)
            payment.failure_reason = "Сумма оплаты не совпала с ценой курса"
        else:
            payment.status = "paid"
            payment.failure_reason = None
            payment.paid_at = datetime.utcnow()
            await _grant_course(session, payment.user_id, payment.course_id, payment.amount_kzt)
    await session.commit()


@router.post("/courses/{code}", response_model=PaymentStartOut)
async def start_course_payment(
    code: str,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    result = await session.execute(select(Course).where(Course.code == code.upper()))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    already = await session.execute(
        select(CoursePurchase.id).where(CoursePurchase.user_id == user.id, CoursePurchase.course_id == course.id)
    )
    if already.first():
        return PaymentStartOut(owned=True)

    if not HALYK_ENABLED:
        # Пилот до подключения банка: курс открывается сразу, без списания — как было раньше.
        await _grant_course(session, user.id, course.id, course.price_kzt)
        await session.commit()
        return PaymentStartOut(owned=True)

    # Ученик мог оплатить, но не вернуться в мини-апп, а postLink не дошёл (Render free спит) —
    # перед новым заказом досверяем недавние незавершённые, чтобы не взять деньги дважды.
    recent = await session.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.course_id == course.id,
            Payment.status == "pending",
            Payment.created_at >= datetime.utcnow() - timedelta(days=1),
        )
    )
    for pending in recent.scalars().all():
        await _sync_with_bank(session, pending)
        if pending.status == "paid":
            return PaymentStartOut(owned=True)

    payment = Payment(
        user_id=user.id,
        course_id=course.id,
        amount_kzt=course.price_kzt,
        invoice_id=halyk.new_invoice_id(),
        secret_hash=halyk.new_secret_hash(),
    )
    session.add(payment)
    await session.commit()

    base = _base_url()
    post_link = f"{base}/api/payments/halyk/postlink"
    try:
        auth = await halyk.payment_token(
            invoice_id=payment.invoice_id,
            amount=payment.amount_kzt,
            secret_hash=payment.secret_hash,
            post_link=post_link,
        )
    except halyk.HalykError as e:
        payment.status = "failed"
        payment.failure_reason = str(e)
        await session.commit()
        raise HTTPException(status_code=502, detail=str(e))

    return PaymentStartOut(
        payment_id=payment.id,
        js_url=halyk.PAYMENT_JS_URL,
        payment={
            "invoiceId": payment.invoice_id,
            "backLink": f"{base}/?payment={payment.id}",
            "failureBackLink": f"{base}/?payment={payment.id}",
            "postLink": post_link,
            "failurePostLink": post_link,
            "language": "rus",
            "description": f"Курс {course.title}"[:60],
            "accountId": str(user.id),
            "terminal": HALYK_TERMINAL_ID,
            "amount": payment.amount_kzt,
            "currency": halyk.CURRENCY,
            "auth": auth,
        },
    )


@router.get("/{payment_id}", response_model=PaymentStatusOut)
async def get_payment_status(
    payment_id: int,
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_user(session, x_telegram_init_data)
    payment = await session.get(Payment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Платёж не найден")
    if HALYK_ENABLED:
        await _sync_with_bank(session, payment)
    course = await session.get(Course, payment.course_id)
    return PaymentStatusOut(
        status=payment.status, course_code=course.code if course else "", failure_reason=payment.failure_reason
    )


@router.post("/halyk/postlink")
async def halyk_postlink(request: Request, session: AsyncSession = Depends(get_session)):
    """Уведомление банка о результате оплаты (и postLink, и failurePostLink). Само по себе
    оплату не подтверждает — только запускает сверку со статусом транзакции в банке."""
    try:
        data = await request.json()
    except Exception:
        data = dict(await request.form())
    invoice_id = str(data.get("invoiceId") or data.get("invoiceID") or "")
    result = await session.execute(select(Payment).where(Payment.invoice_id == invoice_id))
    payment = result.scalar_one_or_none()
    if not payment or not hmac.compare_digest(str(data.get("secret_hash") or ""), payment.secret_hash):
        logger.warning("Halyk postLink for unknown invoice or wrong secret_hash: %s", invoice_id)
        return {"status": "ignored"}

    if str(data.get("code") or "").lower() == "ok":
        await _sync_with_bank(session, payment)
    elif payment.status == "pending":
        payment.status = "failed"
        payment.failure_reason = str(data.get("reason") or "Оплата не прошла")[:500]
        await session.commit()
    return {"status": "ok"}
