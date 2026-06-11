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
    "SHELF","SHF","SHIP","SHLF","SPAR","SRBANK","STRO",
    "BWE","CADLR","CLOUD","COMROD","FKRAFT","KIT","KROHN","MEDIC",
    "NAK","NORDIC","NYKD","OTEC","PEN","PNOR","SAGA","SBO","SCH",
    "SGR","SKUE","SMART","SNSA","SOFTOX","SWA","TNOR","TOTG","TRQ",
    "TWOL","ULTI","VOSS","WILS","HMONY","FLYR","AUTOSTORE",
    "OTELLO","SPSB",
]


class YahooOsloScreener:

    def fetch_prices(self, tickers_ol: list[str],
                     min_price: float, max_price: float) -> list[dict]:
        """Batch-hent kurs i bolker à 30 for å unngå rate limiting."""
        log.info("Batch-henter kurs for %d Oslo Børs-tickers…", len(tickers_ol))
        _BATCH = 30
        _BATCH_SLEEP = 5.0

        all_close: dict[str, pd.Series] = {}
        for i in range(0, len(tickers_ol), _BATCH):
            batch = tickers_ol[i:i + _BATCH]
            try:
                raw = yf.download(
                    batch,
                    period="2d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                close = raw["Close"] if "Close" in raw else raw.get("close", pd.DataFrame())
                if not close.empty:
                    for sym in close.columns:
                        all_close[sym] = close[sym]
            except Exception as exc:
                log.warning("Batch %d/%d feilet: %s",
                            i // _BATCH + 1, -(-len(tickers_ol) // _BATCH), exc)
            if i + _BATCH < len(tickers_ol):
                time.sleep(_BATCH_SLEEP)

        candidates = []
        for sym in tickers_ol:
            try:
                col = all_close.get(sym, pd.Series()).dropna()
                if col.empty:
                    continue
                price = float(col.iloc[-1])
                prev  = float(col.iloc[-2]) if len(col) >= 2 else None
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
                ev = _nn(info.get("enterpriseToEbitda"))
                sd.ev_ebitda    = ev if (ev is not None and 0 < ev <= 50) else None
                dy = _nn(info.get("dividendYield"))
                sd.dividend_yield = dy if (dy is not None and dy <= 1.0) else None
                sd.roe          = _nn(info.get("returnOnEquity"))
                fcf = info.get("freeCashflow")
                if fcf:
                    sd.free_cash_flow = float(fcf) / 1e6
            except Exception as exc:
                log.debug("info-feil %s: %s", sym, exc)
            results.append(sd)
            time.sleep(1.5)
        return results

    def apply_value_filter(self, stocks: list[StockData], thresholds: dict) -> list[StockData]:
        pe_max = thresholds.get("pe_ratio_max", 20.0)
        pb_max = thresholds.get("pb_ratio_max", 1.5)
        scored = []
        for sd in stocks:
            hits, tests = 0, 0
            if sd.pe_ratio is not None:
                tests += 1
                if 0 < sd.pe_ratio <= pe_max:
                    hits += 1
            if sd.pb_ratio is not None and sd.pb_ratio > 0:
                tests += 1
                if sd.pb_ratio <= pb_max:
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
                scored.append((hits, sd.pe_ratio or 999.0, sd))

        # Sortering: flest kriterier → størst daglig kursfall (nytt kjøpsmulighet) → lavest P/E
        def _day_drop(sd: StockData) -> float:
            if sd.price and sd.prev_close and sd.prev_close > 0:
                return (sd.price - sd.prev_close) / sd.prev_close  # negativt = kursfall
            return 0.0

        scored.sort(key=lambda x: (-x[0], _day_drop(x[2]), x[1]))
        passed = [sd for _, _, sd in scored]
        log.info("Verdiscreening: %d av %d kandidater passerte.", len(passed), len(stocks))
        return passed

    def fetch_news(self, stocks: list[StockData]) -> list[StockData]:
        """Henter nyheter kun for aksjer som har passert verdifiltrering."""
        for sd in stocks:
            try:
                news_raw = yf.Ticker(f"{sd.ticker}.OL").news
                sd.news = _parse_news_items(news_raw)
            except Exception:
                pass
            time.sleep(1.0)
        return stocks

    def run(self, thresholds: dict, min_price: float = 5.0,
            max_price: float = 200.0,
            extra_tickers: list[str] | None = None) -> list[StockData]:
        tickers_base = list(dict.fromkeys(_OSLO_TICKERS + (extra_tickers or [])))
        tickers_ol   = [f"{t}.OL" for t in tickers_base]

        candidates = self.fetch_prices(tickers_ol, min_price, max_price)
        if not candidates:
            return []
        stocks = self.fetch_fundamentals(candidates)
        passed = self.apply_value_filter(stocks, thresholds)
        return self.fetch_news(passed)


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f and f != 0.0 else None
    except (TypeError, ValueError):
        return None


def _parse_news_items(news_list) -> list[dict]:
    """Parser yfinance-nyheter – støtter gammelt og nytt format."""
    result = []
    for n in (news_list or []):
        content = n.get("content") if isinstance(n.get("content"), dict) else None
        if content:
            title = content.get("title", "")
            canonical = content.get("canonicalUrl") or {}
            url = canonical.get("url", "") or content.get("url", "") or n.get("link", "")
            pub = content.get("pubDate", "")
            try:
                from datetime import datetime
                ts = int(datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts = 0
        else:
            title = n.get("title", "")
            url = n.get("link", "")
            ts = n.get("providerPublishTime", 0)
        if title:
            result.append({"headline": title, "url": url, "datetime": ts, "summary": ""})
        if len(result) == 10:
            break
    return result
