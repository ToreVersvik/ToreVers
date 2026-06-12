"""
Daglig kjøring – terskel-/hendelsesvarsler.
Stille hvis ingenting krysser en grense.

Env som kreves:
  ANTHROPIC_API_KEY     (kreves ikke for daglig modus)
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
log = logging.getLogger("daily")

CONFIG_PATH = pathlib.Path("config.json")


def main() -> int:
    if not CONFIG_PATH.exists():
        log.error("Finner ikke config.json")
        return 1

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    from screener.data_sources.yahoo import YahooDataSource
    source = YahooDataSource()

    all_stocks_cfg = config.get("portfolio", []) + config.get("watchlist", [])
    log.info("Batch-henter kurs for %d aksjer…", len(all_stocks_cfg))
    stocks = source.fetch_prices_batch(all_stocks_cfg)

    from screener.screener import run_daily
    sent = run_daily(
        stocks=stocks,
        thresholds=config.get("thresholds", {}),
        cooldown_hours=config.get("cooldown_hours", 24.0),
        full_source=source,
        stocks_cfg=all_stocks_cfg,
    )
    log.info("Ferdig. %d varsel(er) sendt.", sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
