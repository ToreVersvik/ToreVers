"""
Yahoo Finance-datakilde – ingen API-nøkkel nødvendig.
Fungerer fra GitHub Actions (i motsetning til Finnhub gratisnivå).
"""
import logging
import time
from typing import Optional

import pandas as pd
import yfinance as yf

from .base import DataSource, StockData

log = logging.getLogger(__name__)

_EXCHANGE_SUFFIX = {
    "OSL": ".OL",
    "STO": ".ST",
    "CPH": ".CO",
    "HEL": ".HE",
    "US":  "",
}
_RATE_SLEEP = 0.5


class YahooDataSource(DataSource):

    def _yf_sym(self, ticker: str, exchange: str) -> str:
        return f"{ticker}{_EXCHANGE_SUFFIX.get(exchange, '')}"

    def fetch(self, ticker: str, exchange: str, currency: str,
              name: str = "", ask_eligible: bool = True) -> StockData:
        sym = self._yf_sym(ticker, exchange)
        sd = StockData(ticker=ticker, name=name or ticker, exchange=exchange,
                       currency=currency, ask_eligible=ask_eligible, source="yahoo")
        try:
            t = yf.Ticker(sym)

            # Kurs
            fi = t.fast_info
            sd.price = _nn(fi.last_price)
            sd.prev_close = _nn(fi.previous_close)
            sd.market_cap = _nn(getattr(fi, "market_cap", None))

            # Nøkkeltall
            info = t.info
            sd.pe_ratio     = _nn(info.get("trailingPE") or info.get("forwardPE"))
            sd.pb_ratio     = _nn(info.get("priceToBook"))
            sd.ps_ratio     = _nn(info.get("priceToSalesTrailing12Months"))
            ev = _nn(info.get("enterpriseToEbitda"))
            sd.ev_ebitda    = ev if (ev is not None and 0 < ev <= 50) else None
            dy = _nn(info.get("dividendYield"))
            sd.dividend_yield = dy if (dy is not None and dy <= 1.0) else None
            sd.roe          = _nn(info.get("returnOnEquity"))
            fcf = info.get("freeCashflow")
            if fcf:
                sd.free_cash_flow = float(fcf) / 1e6
            dte = info.get("debtToEquity")
            if dte:
                sd.debt_to_equity = float(dte) / 100
            sd.analyst_target_price = _nn(info.get("targetMeanPrice"))
            rec = (info.get("recommendationKey") or "").lower()
            if "buy" in rec:
                sd.analyst_rating = "Kjøp"
            elif "sell" in rec:
                sd.analyst_rating = "Selg"
            elif rec == "hold":
                sd.analyst_rating = "Hold"

            sd.news = _parse_news_items(t.news)
        except Exception as exc:
            log.warning("Yahoo-feil for %s: %s", sym, exc)
            sd.fetch_error = str(exc)

        time.sleep(_RATE_SLEEP)
        return sd

    def fetch_prices_batch(self, stocks_cfg: list[dict]) -> list[StockData]:
        """Rask batch-prisfetch med yf.download – ingen nøkkeltall, kun kurs/forrige kurs."""
        syms = [self._yf_sym(c["ticker"], c.get("exchange", "")) for c in stocks_cfg]
        try:
            raw = yf.download(syms, period="2d", auto_adjust=True, progress=False, threads=True)
            close = raw["Close"] if "Close" in raw else pd.DataFrame()
        except Exception as exc:
            log.error("Batch-prisfeil: %s", exc)
            close = pd.DataFrame()

        results = []
        for c, sym in zip(stocks_cfg, syms):
            sd = StockData(
                ticker=c["ticker"], name=c.get("name", c["ticker"]),
                exchange=c.get("exchange", ""), currency=c.get("currency", ""),
                ask_eligible=c.get("ask_eligible", True), source="yahoo",
            )
            try:
                col = (close[sym] if sym in close.columns else pd.Series()).dropna()
                if not col.empty:
                    sd.price = float(col.iloc[-1])
                    if len(col) >= 2:
                        sd.prev_close = float(col.iloc[-2])
            except Exception:
                pass
            results.append(sd)
        return results


def _parse_news_items(news_list) -> list[dict]:
    """Parser yfinance-nyheter – støtter gammelt og nytt format."""
    result = []
    for n in (news_list or []):
        # Nytt format (yfinance ≥ 0.2.50): nyheten er pakket i et "content"-objekt
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
            # Gammelt format
            title = n.get("title", "")
            url = n.get("link", "")
            ts = n.get("providerPublishTime", 0)

        if title:
            result.append({"headline": title, "url": url, "datetime": ts, "summary": ""})
        if len(result) == 10:
            break
    return result


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f and f != 0.0 else None  # fanger NaN
    except (TypeError, ValueError):
        return None
