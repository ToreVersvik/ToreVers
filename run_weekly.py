"""
Ukentlig kjøring – full rapport med 3 seksjoner.

Env som kreves:
  FINNHUB_API_KEY
  ANTHROPIC_API_KEY
  TELEGRAM_BOT_TOKEN    (valgfri – konsoll-fallback)
  TELEGRAM_CHAT_ID      (valgfri)
"""
import json
import logging
import pathlib
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("weekly")

CONFIG_PATH = pathlib.Path("config.json")


def load_data_source(config: dict):
    from screener.data_sources.finnhub import FinnhubDataSource
    from screener.data_sources.manual import ManualDataSource, FallbackDataSource

    manual_map = {
        s["ticker"]: s.get("manual_data", {})
        for s in config.get("portfolio", []) + config.get("watchlist", [])
    }
    try:
        primary = FinnhubDataSource()
    except EnvironmentError as e:
        log.warning("%s – faller tilbake til kun manuell data.", e)
        return ManualDataSource(manual_map)

    return FallbackDataSource(primary=primary, secondary=ManualDataSource(manual_map))


def main() -> int:
    if not CONFIG_PATH.exists():
        log.error("Finner ikke config.json")
        return 1

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source = load_data_source(config)

    portfolio_cfg = config.get("portfolio", [])
    watchlist_cfg = config.get("watchlist", [])

    log.info("Henter data for portefølje (%d) og watchlist (%d)…",
             len(portfolio_cfg), len(watchlist_cfg))

    portfolio_stocks = source.fetch_many(portfolio_cfg)
    watchlist_stocks = source.fetch_many(watchlist_cfg)

    from screener.report import run_weekly
    run_weekly(
        portfolio=portfolio_stocks,
        watchlist=watchlist_stocks,
        thresholds=config.get("thresholds", {}),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
