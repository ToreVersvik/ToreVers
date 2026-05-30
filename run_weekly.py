"""
Ukentlig kjøring – full rapport med 3 seksjoner.

Env som kreves:
  ANTHROPIC_API_KEY
  TELEGRAM_BOT_TOKEN    (valgfri – konsoll-fallback)
  TELEGRAM_CHAT_ID      (valgfri)
"""
import json
import logging
import os
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
    from screener.data_sources.yahoo import YahooDataSource
    from screener.data_sources.manual import ManualDataSource, FallbackDataSource

    manual_map = {
        s["ticker"]: s.get("manual_data", {})
        for s in config.get("portfolio", [])
    }
    return FallbackDataSource(primary=YahooDataSource(), secondary=ManualDataSource(manual_map))


def load_watchlist(config: dict) -> list:
    """
    Dynamisk watchlist: screener hele Oslo Børs 5–200 NOK hvis aktivert.
    Bruker Yahoo Finance – ingen API-nøkkel nødvendig.
    """
    dyn = config.get("dynamic_watchlist", {})
    if not dyn.get("enabled", False):
        log.info("Dynamisk watchlist deaktivert – bruker fast watchlist.")
        return []

    from screener.oslo_screener import YahooOsloScreener
    screener = YahooOsloScreener()

    min_p = dyn.get("min_price_nok", 5.0)
    max_p = dyn.get("max_price_nok", 200.0)

    log.info("Kjører dynamisk Oslo Børs-screener (%.0f–%.0f NOK)…", min_p, max_p)
    candidates = screener.run(
        thresholds=config.get("thresholds", {}),
        min_price=min_p,
        max_price=max_p,
    )
    log.info("%d undervurderte kandidater funnet på Oslo Børs.", len(candidates))
    return candidates


def main() -> int:
    if not CONFIG_PATH.exists():
        log.error("Finner ikke config.json")
        return 1

    # Sjekk at nødvendige secrets er satt
    for key in ("ANTHROPIC_API_KEY",):
        val = os.environ.get(key, "")
        if val:
            log.info("%s: satt (%d tegn)", key, len(val))
        else:
            log.warning("%s: MANGLER – sjekk GitHub Secrets", key)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source = load_data_source(config)

    portfolio_cfg = config.get("portfolio", [])
    log.info("Henter data for portefølje (%d aksjer)…", len(portfolio_cfg))
    portfolio_stocks = source.fetch_many(portfolio_cfg)

    watchlist_stocks = load_watchlist(config)

    from screener.report import run_weekly
    run_weekly(
        portfolio=portfolio_stocks,
        watchlist=watchlist_stocks,
        thresholds=config.get("thresholds", {}),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
