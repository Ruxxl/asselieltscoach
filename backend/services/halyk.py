"""Halyk ePay: оплата на платёжной странице банка (https://epayment.kz/ru-RU/docs/platezhnaya-stranica).

Схема: сервер получает у банка токен на конкретный заказ (invoiceId + сумма), фронтенд передаёт его
в halyk.pay() из скрипта банка, и тот уводит ученика на страницу Halyk, где он вводит карту и проходит
3-D Secure. Данные карты к нам не попадают — поэтому PCI DSS не нужен. Результат банк присылает на
postLink, а мы дополнительно сверяем его запросом статуса транзакции (check-status) — это и есть
источник истины, а не уведомление и не возврат ученика на backLink.
"""

import logging
import secrets
import time

import aiohttp

from backend.config import HALYK_CLIENT_ID, HALYK_CLIENT_SECRET, HALYK_TERMINAL_ID, HALYK_TEST_MODE

logger = logging.getLogger(__name__)

# Адреса из документации ePay. Тестовый check-status из документации (testepay.homebank.kz) не
# отвечает — рабочий проверен вручную; боевые адреса сверить с тем, что выдаст банк.
if HALYK_TEST_MODE:
    OAUTH_URL = "https://test-epay-oauth.epayment.kz/oauth2/token"
    PAYMENT_JS_URL = "https://test-epay.epayment.kz/payform/payment-api.js"
    STATUS_URL = "https://test-epay-api.epayment.kz/check-status/payment/transaction/{invoice_id}"
else:
    OAUTH_URL = "https://epay-oauth.homebank.kz/oauth2/token"
    PAYMENT_JS_URL = "https://epay.homebank.kz/payform/payment-api.js"
    STATUS_URL = "https://epay-api.homebank.kz/check-status/payment/transaction/{invoice_id}"

CURRENCY = "KZT"
# CHARGE — деньги списаны; AUTH — заблокированы на карте (двухстадийная оплата). Если банк
# настроит терминал как двухстадийный, AUTH нужно будет ещё подтвердить (charge) — уточнить у банка.
PAID_STATUSES = {"CHARGE", "AUTH"}
_STATUS_SCOPE = "webapi usermanagement email_send verification statement statistics payment"
_TIMEOUT = aiohttp.ClientTimeout(total=20)


class HalykError(Exception):
    pass


def new_invoice_id() -> str:
    """12 цифр из текущего времени в миллисекундах. Банк требует 6–15 цифр и уникальность
    в последних 6 знаках; номер из id строки не подходит — SQLite на Render free стирается
    при каждом деплое, id начнутся с 1 и совпадут с уже отправленными в банк заказами."""
    return f"{int(time.time() * 1000) % 10**12:012d}"


def new_secret_hash() -> str:
    return secrets.token_hex(16)


async def _request_token(form: dict) -> dict:
    data = {
        "grant_type": "client_credentials",
        "client_id": HALYK_CLIENT_ID,
        "client_secret": HALYK_CLIENT_SECRET,
        "terminal": HALYK_TERMINAL_ID,
        **form,
    }
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        async with http.post(OAUTH_URL, data=data) as resp:
            body = await resp.text()
            if resp.status != 200:
                logger.warning("Halyk token request failed with %s: %s", resp.status, body)
                raise HalykError("Платёжный сервис временно недоступен")
            payload = await resp.json(content_type=None)
    if not payload.get("access_token"):
        logger.warning("Halyk token response without access_token: %s", body)
        raise HalykError("Платёжный сервис временно недоступен")
    return payload


async def payment_token(*, invoice_id: str, amount: int, secret_hash: str, post_link: str) -> dict:
    """Токен на один заказ — целиком (а не только access_token) уходит в поле auth для halyk.pay()."""
    return await _request_token(
        {
            "scope": "payment",
            "invoiceID": invoice_id,
            "amount": str(amount),
            "currency": CURRENCY,
            "secret_hash": secret_hash,
            "postLink": post_link,
            "failurePostLink": post_link,
        }
    )


_status_token: tuple[str, float] | None = None


async def _get_status_token() -> str:
    global _status_token
    if _status_token and _status_token[1] > time.monotonic():
        return _status_token[0]
    token = (await _request_token({"scope": _STATUS_SCOPE}))["access_token"]
    # Токен живёт 7200 с; берём с запасом.
    _status_token = (token, time.monotonic() + 6000)
    return token


async def fetch_transaction(invoice_id: str) -> dict | None:
    """Транзакция по номеру заказа или None, если банк её не знает (ученик ещё не дошёл до оплаты)."""
    token = await _get_status_token()
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as http:
        async with http.get(
            STATUS_URL.format(invoice_id=invoice_id), headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                logger.warning("Halyk check-status %s failed with %s: %s", invoice_id, resp.status, body)
                return None
            payload = await resp.json(content_type=None)
    if str(payload.get("resultCode")) != "100":
        return None
    return payload.get("transaction") or None
