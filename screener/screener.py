"""
Daglig terskel-screener.
Regler:
  - kurs faller > price_drop_pct% siden forrige stengedag → varsel
  - kurs stiger > price_rise_pct% siden forrige stengedag → varsel
  - ingen varsel hvis ingenting krysser grense (stille kjøring)
"""
import logging
from dataclasses import dataclass
from typing import Optional

from .data_sources.base import StockData

log = logging.getLogger(__name__)


@dataclass
class Alert:
    ticker: str
    name: str
    event_type: str
    message: str


def check_thresholds(sd: StockData, thresholds: dict) -> list[Alert]:
    """Returner liste med Alert for alle kryssede terskler. Tom = stille."""
    alerts: list[Alert] = []

    if sd.price is None or sd.prev_close is None or sd.prev_close == 0:
        return alerts

    change_pct = (sd.price - sd.prev_close) / sd.prev_close * 100

    drop_limit = thresholds.get("price_drop_pct", 5.0)
    rise_limit = thresholds.get("price_rise_pct", 8.0)
    ask_note = "" if sd.ask_eligible else " *(kun utenfor ASK)*"

    if change_pct <= -drop_limit:
        alerts.append(Alert(
            ticker=sd.ticker,
            name=sd.name,
            event_type="price_drop",
            message=(
                f"📉 *{sd.name}* ({sd.ticker}){ask_note}\n"
                f"Kursfall: {change_pct:.1f}%  |  "
                f"Nå: {sd.price:.2f} {sd.currency}  |  "
                f"Forrige stengedag: {sd.prev_close:.2f} {sd.currency}\n"
                f"_Dette er informasjon, ikke finansiell rådgivning._"
            ),
        ))

    if change_pct >= rise_limit:
        alerts.append(Alert(
            ticker=sd.ticker,
            name=sd.name,
            event_type="price_rise",
            message=(
                f"📈 *{sd.name}* ({sd.ticker}){ask_note}\n"
                f"Kursoppgang: +{change_pct:.1f}%  |  "
                f"Nå: {sd.price:.2f} {sd.currency}  |  "
                f"Forrige stengedag: {sd.prev_close:.2f} {sd.currency}\n"
                f"_Dette er informasjon, ikke finansiell rådgivning._"
            ),
        ))

    return alerts


def run_daily(stocks: list[StockData], thresholds: dict, cooldown_hours: float) -> int:
    """
    Kjør daglig screening. Returner antall varsler sendt.
    Import av notifier skjer her for å unngå sirkulær avhengighet.
    """
    from .notifier import send_alert

    total_sent = 0
    for sd in stocks:
        if sd.fetch_error:
            log.warning("Henting feilet for %s: %s", sd.ticker, sd.fetch_error)
            continue
        for alert in check_thresholds(sd, thresholds):
            send_alert(
                ticker=alert.ticker,
                event_type=alert.event_type,
                message=alert.message,
                cooldown_hours=cooldown_hours,
            )
            total_sent += 1

    if total_sent == 0:
        log.info("Daglig screening: ingen terskler krysset – stille kjøring.")
    return total_sent
