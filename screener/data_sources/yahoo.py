"""
Yahoo Finance-datakilde – ingen API-nøkkel nødvendig.
Fungerer fra GitHub Actions (i motsetning til Finnhub gratisnivå).
"""
import logging
import time
from typing import Optional

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
            sd.ev_ebitda    = _nn(info.get("enterpriseToEbitda"))
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

            # Nyheter
            sd.news = [
                {"headline": n.get("title", ""), "url": n.get("link", ""),
                 "datetime": n.get("providerPublishTime", 0), "summary": ""}
                for n in (t.news or [])[:10]
            ]
        except Exception as exc:
            log.warning("Yahoo-feil for %s: %s", sym, exc)
            sd.fetch_error = str(exc)

        time.sleep(_RATE_SLEEP)
        return sd


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f == f and f != 0.0 else None  # fanger NaN
    except (TypeError, ValueError):
        return None
