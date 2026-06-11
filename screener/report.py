"""
Ukentlig rapport – de tre seksjonene som beskrevet i CLAUDE.md.
"""
import datetime
import logging

from .data_sources.base import StockData
from . import claude_analyst
from .notifier import send_report

log = logging.getLogger(__name__)


def run_weekly(portfolio: list[StockData], watchlist: list[StockData], thresholds: dict) -> None:
    today = datetime.date.today().strftime("%d.%m.%Y")
    log.info("Starter ukentlig rapport (%s)…", today)

    log.info("Analyserer portefølje (%d aksjer)…", len(portfolio))
    s1 = claude_analyst.analyse_portfolio(portfolio, thresholds)

    # Ekskluder aksjer man allerede eier fra kjøpsideer
    owned_tickers = {s.ticker for s in portfolio}
    ideas_candidates = [s for s in watchlist if s.ticker not in owned_tickers]

    top_watchlist = ideas_candidates[:15]
    log.info("Søker etter kjøpsideer (%d av %d kandidater, %d ekskludert som allerede eid)…",
             len(top_watchlist), len(watchlist), len(watchlist) - len(ideas_candidates))
    s2 = claude_analyst.find_undervalued_ideas(top_watchlist, thresholds)

    log.info("Henter nyhetsdigest…")
    s3 = claude_analyst.news_digest(portfolio + top_watchlist)

    body = (
        f"\U0001f4c5 *Ukentlig rapport {today}*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f4ca *PORTEFØLJE*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{s1}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f4a1 *KJØPSIDEER* (Oslo Børs 5–200 NOK)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{s2}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\U0001f4f0 *NYHETSDIGEST*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{s3}\n\n"
        f"_Til informasjon/læring, ikke finansiell rådgivning._"
    )

    send_report(title=f"Ukentlig Aksjerapport {today}", body=body)
    log.info("Ukentlig rapport sendt.")
