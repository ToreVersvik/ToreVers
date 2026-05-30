"""
Telegram-varsling med konsoll-fallback.
Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os
import logging

import requests

from .journal import log_entry, read_recent

log = logging.getLogger(__name__)

_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> bool:
    if not (_TOKEN and _CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": _CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=10)
        r.raise_for_status()
        return True
    except Exception as exc:
        log.error("Telegram-feil: %s", exc)
        return False


def send_alert(ticker: str, event_type: str, message: str, cooldown_hours: float = 24.0) -> None:
    recent = read_recent(event_type=event_type, ticker=ticker, hours=cooldown_hours)
    if recent:
        log.info("Cooldown aktiv for %s/%s – hopper over", ticker, event_type)
        return

    sent = _send_telegram(message)
    if not sent:
        print(f"[VARSEL] {message}")

    log_entry(event_type=event_type, ticker=ticker, payload={"message": message, "sent_telegram": sent})


def send_report(title: str, body: str) -> None:
    full = f"*{title}*\n\n{body}"
    chunks = _chunk(full, 4000)
    for chunk in chunks:
        sent = _send_telegram(chunk)
        if not sent:
            print(chunk)
    log_entry(event_type="weekly_report", ticker="ALL", payload={"title": title, "chars": len(body)})


def _chunk(text: str, size: int) -> list[str]:
    lines = text.split("\n")
    chunks, current = [], []
    length = 0
    for line in lines:
        if length + len(line) + 1 > size and current:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks
