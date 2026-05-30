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

    log.info("Søker etter undervurderte ideer (%d kandidater)…", len(watchlist))
    s2 = claude_analyst.find_undervalued_ideas(watchlist, thresholds)

    all_stocks = portfolio + watchlist
    log.info("Henter nyhetsdigest…")
    s3 = claude_analyst.news_digest(all_stocks)

    body = (
        f"📅 Dato: {today}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*1. PORTEFØLJEGJENNOMGANG*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n{s1}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*2. UNDERVURDERTE IDEER*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n{s2}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"*3. NYHETSDIGEST*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n{s3}\n\n"
        f"_Dette er til informasjon/læring, ikke finansiell rådgivning._"
    )

    send_report(title=f"Ukentlig Aksjerapport {today}", body=body)
    log.info("Ukentlig rapport sendt.")
