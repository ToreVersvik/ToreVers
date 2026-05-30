"""
Dynamisk screener for Oslo Børs via Yahoo Finance.
Ingen API-nøkkel nødvendig. Fungerer fra GitHub Actions.
"""
import logging
import time
from typing import Optional

import yfinance as yf
import pandas as pd

from .data_sources.base import StockData

log = logging.getLogger(__name__)

# Kjente Oslo Børs-tickers (kan utvides i config)
_OSLO_TICKERS = [
    "EQNR","DNB","MOWI","ORK","TEL","NHY","SALM","YARA","AKRBP","STB",
    "GJF","SRBNK","SCATC","NONG","BAKKA","SUBC","TOM","PGS","BOR","KOG",
    "HAUTO","FRO","GOGL","BULKERS","VAR","BNOR","SPNO","AKER","AKSO",
    "ARCHER","AMSC","BWO","ELKEM","ENTRA","EUROPRIS","MPCC","NEXT",
    "SATS","XXL","ZAL","MHG","REC","AGAS","BELSHIPS","FLNG","HOG",
    "IDEX","KAHOOT","NEL","NORBIT","NORCOD","OHT","PHO","PLCS",
    "REACH","SCR","SOLON","VEI","WILH","CRAYN","LINK","MAGNORA",
    "THIN","VISTIN","SVEG","PROTCT","ODL","SMARTC","JIN","HOEGH",
    "LUMI","SOFF","SIOFF","MPC","OKEA","PARB","QEC","RIVR","SDRL",
    "SHELF","SHF","SHIP","SHLF","SOFF","SPAR","SRBANK","STRO","SUBC",
    "BWE","CADLR","CLOUD","COMROD","FKRAFT","KIT","KROHN","MEDIC",
    "NAK","NORDIC","NYKD","OTEC","PEN","PNOR","SAGA","SBO","SCH",
    "SGR","SKUE","SMART","SNSA","SOFTOX","SWA","TNOR","TOTG","TRQ",
    "TWOL","ULTI","VOSS","WILS","HMONY","FLYR","AUTOSTORE",
]


class YahooOsloScreener:

    def fetch_prices(self, tickers_ol: list[str],
                     min_price: float, max_price: float) -> list[dict]:
        """Batch-hent kurs for alle tickers, returner de i prisintervallet."""
        log.info("Batch-henter kurs for %d Oslo Børs-tickers…", len(tickers_ol))
        try:
            raw = yf.download(
                tickers_ol,
                period="2d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            close = raw["Close"] if "Close" in raw else raw.get("close", pd.DataFrame())
        except Exception as exc:
            log.error("yf.download feilet: %s", exc)
            return []

        candidates = []
        for sym in tickers_ol:
            try:
                col = close[sym] if sym in close.columns else None
                if col is None or col.dropna().empty:
                    continue
                price = float(col.dropna().iloc[-1])
                prev  = float(col.dropna().iloc[-2]) if len(col.dropna()) >= 2 else None
                if min_price <= price <= max_price:
                    ticker = sym.replace(".OL", "")
                    candidates.append({"symbol": sym, "ticker": ticker,
                                       "price": price, "prev_close": prev})
            except Exception:
                continue

        log.info("Prisfilteret (%.0f–%.0f NOK) ga %d kandidater.", min_price, max_price, len(candidates))
        return candidates

    def fetch_fundamentals(self, candidates: list[dict]) -> list[StockData]:
        log.info("Henter nøkkeltall for %d kandidater…", len(candidates))
        results = []
        for c in candidates:
            sym = c["symbol"]
            sd = StockData(ticker=c["ticker"], name=c["ticker"], exchange="OSL",
                           currency="NOK", ask_eligible=True, source="yahoo",
                           price=c["price"], prev_close=c.get("prev_close"))
            try:
                info = yf.Ticker(sym).info
                sd.name         = info.get("longName") or info.get("shortName") or c["ticker"]
                sd.pe_ratio     = _nn(info.get("trailingPE") or info.get("forwardPE"))
                sd.pb_ratio     = _nn(info.get("priceToBook"))
                sd.ev_ebitda    = _nn(info.get("enterpriseToEbitda"))
                dy = _nn(info.get("dividendYield"))
                sd.dividend_yield = dy if (dy is not None and dy <= 1.0) else None
                sd.roe          = _nn(info.get("returnOnEquity"))
                fcf = info.get("freeCashflow")
                if fcf:
                    sd.free_cash_flow = float(fcf) / 1e6
            except Exception as exc:
                log.debug("info-feil %s: %s", sym, exc)
            results.append(sd)
            time.sleep(0.3)
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

    def run(self, thresholds: dict, min_price: float = 5.0,
            max_price: float = 200.0,
            extra_tickers: list[str] | None = None) -> list[StockData]:
        tickers_base = list(dict.fromkeys(_OSLO_TICKERS + (extra_tickers or [])))
        tickers_ol   = [f"{t}.OL" for t in tickers_base]

        candidates = self.fetch_prices(tickers_ol, min_price, max_price)
        if not candidates:
            return []
        stocks = self.fetch_fundamentals(candidates)
        return self.apply_value_filter(stocks, thresholds)


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f and f != 0.0 else None
    except (TypeError, ValueError):
        return None
