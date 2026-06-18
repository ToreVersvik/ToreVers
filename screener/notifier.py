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


def _send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    if not (_TOKEN and _CHAT_ID):
        log.warning("Telegram ikke konfigurert (TELEGRAM_BOT_TOKEN/CHAT_ID mangler)")
        return False
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    payload: dict = {"chat_id": _CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 400 and parse_mode:
            log.warning("Telegram 400 (Markdown-feil) – prøver uten formatering. Svar: %s", r.text[:300])
            return _send_telegram(text, parse_mode="")
        r.raise_for_status()
        log.info("Telegram-melding sendt (%d tegn)", len(text))
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
        log.warning("Telegram ikke tilgjengelig – varsel kun til konsoll")
        print(f"[VARSEL] {message}")

    log_entry(event_type=event_type, ticker=ticker, payload={"message": message, "sent_telegram": sent})


def send_report(title: str, body: str) -> None:
    full = f"*{title}*\n\n{body}"
    chunks = _chunk(full, 4000)
    log.info("Sender rapport i %d del(er) til Telegram…", len(chunks))
    all_sent = True
    for i, chunk in enumerate(chunks, 1):
        sent = _send_telegram(chunk)
        if not sent:
            all_sent = False
            log.warning("Telegram-sending feilet for del %d/%d – skriver til konsoll", i, len(chunks))
            print(chunk)
    if all_sent:
        log.info("Rapport sendt til Telegram (%d del(er)).", len(chunks))
    log_entry(event_type="weekly_report", ticker="ALL", payload={"title": title, "chars": len(body), "telegram_ok": all_sent})


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
