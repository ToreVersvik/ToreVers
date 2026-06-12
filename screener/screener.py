"""
Daglig terskel-screener.
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


def _enrich_and_analyse(sd: StockData, full_source, stock_cfg: dict) -> Optional[dict]:
    """Hent fullstendig data og be Claude om vurdering for én aksje."""
    try:
        full_sd = full_source.fetch(
            ticker=stock_cfg["ticker"],
            exchange=stock_cfg.get("exchange", ""),
            currency=stock_cfg.get("currency", ""),
            name=stock_cfg.get("name", stock_cfg["ticker"]),
            ask_eligible=stock_cfg.get("ask_eligible", True),
        )
        if full_sd.price is None:
            full_sd.price = sd.price
            full_sd.prev_close = sd.prev_close

        from . import claude_analyst
        result = claude_analyst._analyse_stock(full_sd, mode="portfolio")
        return result
    except Exception as exc:
        log.warning("Kunne ikke analysere %s: %s", sd.ticker, exc)
        return None


_REC_EMOJI = {
    "behold":    "🟢",
    "følg nøye": "🟡",
    "reduser":   "🟠",
    "selg":      "🔴",
}


def check_thresholds(sd: StockData, thresholds: dict) -> list[Alert]:
    alerts: list[Alert] = []

    if sd.price is None or sd.prev_close is None or sd.prev_close == 0:
        return alerts

    change_pct = (sd.price - sd.prev_close) / sd.prev_close * 100
    drop_limit = thresholds.get("price_drop_pct", 5.0)
    rise_limit = thresholds.get("price_rise_pct", 8.0)
    ask_note = "" if sd.ask_eligible else " *(kun utenfor ASK)*"

    if change_pct <= -drop_limit:
        alerts.append(Alert(
            ticker=sd.ticker, name=sd.name, event_type="price_drop",
            message=(
                f"📉 *{sd.name}* ({sd.ticker}){ask_note}\n"
                f"Kursfall: {change_pct:.1f}%  |  "
                f"Nå: {sd.price:.2f} {sd.currency}  |  "
                f"Forrige stengedag: {sd.prev_close:.2f} {sd.currency}"
            ),
        ))

    if change_pct >= rise_limit:
        alerts.append(Alert(
            ticker=sd.ticker, name=sd.name, event_type="price_rise",
            message=(
                f"📈 *{sd.name}* ({sd.ticker}){ask_note}\n"
                f"Kursoppgang: +{change_pct:.1f}%  |  "
                f"Nå: {sd.price:.2f} {sd.currency}  |  "
                f"Forrige stengedag: {sd.prev_close:.2f} {sd.currency}"
            ),
        ))

    return alerts


def run_daily(stocks: list[StockData], thresholds: dict, cooldown_hours: float,
              full_source=None, stocks_cfg: Optional[list[dict]] = None) -> int:
    from .notifier import send_alert

    cfg_by_ticker = {s["ticker"]: s for s in (stocks_cfg or [])}
    total_sent = 0

    for sd in stocks:
        if sd.fetch_error:
            log.warning("Henting feilet for %s: %s", sd.ticker, sd.fetch_error)
            continue

        for alert in check_thresholds(sd, thresholds):
            # Berik med full analyse hvis mulig
            analysis = None
            if full_source and sd.ticker in cfg_by_ticker:
                log.info("Henter full analyse for %s…", sd.ticker)
                analysis = _enrich_and_analyse(sd, full_source, cfg_by_ticker[sd.ticker])

            if analysis:
                rec     = analysis.get("rec", "")
                rec_key = rec.lower()
                emoji   = _REC_EMOJI.get(rec_key, "⚪")
                score   = analysis.get("score")
                grunn   = analysis.get("grunn", "")
                tiltak  = analysis.get("tiltak", "")

                analyse_lines = [f"\n{emoji} *Vurdering:* {rec}"]
                if score is not None:
                    analyse_lines.append(f"Score: {score}/100")
                if grunn:
                    analyse_lines.append(grunn)
                if tiltak and tiltak != "null":
                    analyse_lines.append(f"Tiltak: {tiltak}")
                alert.message += "\n".join(analyse_lines)

            alert.message += "\n_Til informasjon/læring, ikke finansiell rådgivning._"

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
