"""Проверка Telegram WebApp initData (подпись HMAC-SHA256 по секрету из BOT_TOKEN).

См. https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
Используется мягко: если initData не пришёл или невалиден, запрос не падает,
а считается анонимным (удобно для локальной разработки без реального Telegram-клиента).
"""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from backend.config import BOT_TOKEN


def parse_init_data(init_data: str | None) -> dict | None:
    if not init_data or not BOT_TOKEN:
        return None

    pairs = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None
    return json.loads(user_raw)
