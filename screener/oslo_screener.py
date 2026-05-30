"""
Dynamisk screener for hele Oslo Børs.
"""
import logging
import time
from typing import Optional

import requests

from .data_sources.base import StockData

log = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_RATE_SLEEP = 0.22


class OsloScreener:
    def __init__(self, api_key: str):
        self._key = api_key

    def _get(self, path: str, params: dict):
        params["token"] = self._key
        try:
            r = requests.get(f"{_BASE}{path}", params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Finnhub-feil (%s): %s", path, exc)
            return None

    def fetch_all_symbols(self) -> list[dict]:
        log.info("Henter symboler fra Oslo Børs…")
        data = self._get("/stock/symbol", {"exchange": "OS"})
        time.sleep(_RATE_SLEEP)
        if not data or not isinstance(data, list):
            log.error("Fikk ingen symboler fra Finnhub for Oslo Børs.")
            return []
        log.info("Fant %d symboler totalt.", len(data))
        return data

    def fetch_quotes(self, symbols: list[dict], min_price: float, max_price: float) -> list[dict]:
        log.info("Henter kurs for %d symboler (filter %.0f–%.0f NOK)…",
                 len(symbols), min_price, max_price)
        candidates = []
        for i, sym in enumerate(symbols):
            ticker = sym.get("symbol", "")
            if not ticker:
                continue
            quote = self._get("/quote", {"symbol": ticker})
            time.sleep(_RATE_SLEEP)
            if not quote or not quote.get("c"):
                continue
            price = quote["c"]
            if min_price <= price <= max_price:
                candidates.append({
                    "symbol": ticker,
                    "display": sym.get("displaySymbol", ticker),
                    "name": sym.get("description", ticker),
                    "price": price,
                    "prev_close": quote.get("pc"),
                })
            if (i + 1) % 50 == 0:
                log.info("  … %d/%d sjekket, %d kandidater så langt",
                         i + 1, len(symbols), len(candidates))
        log.info("Prisfilteret (%.0f–%.0f NOK) ga %d kandidater.",
                 min_price, max_price, len(candidates))
        return candidates

    def fetch_fundamentals(self, candidates: list[dict]) -> list[StockData]:
        log.info("Henter nøkkeltall for %d kandidater…", len(candidates))
        results = []
        for c in candidates:
            ticker = c["symbol"]
            sd = StockData(
                ticker=ticker, name=c["name"], exchange="OSL",
                currency="NOK", ask_eligible=True, source="finnhub",
                price=c["price"], prev_close=c.get("prev_close"),
            )
            metrics_resp = self._get("/stock/metric", {"symbol": ticker, "metric": "all"})
            time.sleep(_RATE_SLEEP)
            if metrics_resp:
                m = metrics_resp.get("metric", {})
                sd.pe_ratio = _nn(m.get("peNormalizedAnnual") or m.get("peBasicExclExtraTTM"))
                sd.pb_ratio = _nn(m.get("pbAnnual") or m.get("pbQuarterly"))
                sd.ps_ratio = _nn(m.get("psAnnual"))
                sd.ev_ebitda = _nn(m.get("evEbitdaAnnual") or m.get("evEbitdaTTM"))
                sd.free_cash_flow = _nn(m.get("freeCashFlowAnnual") or m.get("freeCashFlowTTM"))
                sd.dividend_yield = _nn(m.get("dividendYieldIndicatedAnnual"))
                sd.roe = _nn(m.get("roeRfy") or m.get("roeTTM"))
                sd.debt_to_equity = _nn(m.get("totalDebt/totalEquityAnnual"))
                sd.market_cap = _nn(m.get("marketCapitalization"))
            results.append(sd)
        return results

    def apply_value_filter(self, stocks: list[StockData], thresholds: dict) -> list[StockData]:
        pe_max = thresholds.get("pe_ratio_max", 20.0)
        pb_max = thresholds.get("pb_ratio_max", 1.5)
        passed = []
        for sd in stocks:
            hits, tests = 0, 0
            if sd.pe_ratio is not None:
                tests += 1
                if 0 < sd.pe_ratio <= pe_max:
                    hits += 1
            if sd.pb_ratio is not None:
                tests += 1
                if 0 < sd.pb_ratio <= pb_max:
                    hits += 1
            if sd.ev_ebitda is not None:
                tests += 1
                if 0 < sd.ev_ebitda <= 12:
                    hits += 1
            if sd.free_cash_flow is not None:
                tests += 1
                if sd.free_cash_flow > 0:
                    hits += 1
            if tests == 0:
                continue
            if hits >= min(2, tests):
                passed.append(sd)
        log.info("Verdiscreening: %d av %d kandidater passerte.", len(passed), len(stocks))
        return passed

    def run(self, thresholds: dict, min_price: float = 5.0, max_price: float = 200.0) -> list[StockData]:
        symbols = self.fetch_all_symbols()
        if not symbols:
            return []
        price_candidates = self.fetch_quotes(symbols, min_price, max_price)
        if not price_candidates:
            return []
        stocks = self.fetch_fundamentals(price_candidates)
        return self.apply_value_filter(stocks, thresholds)


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None
