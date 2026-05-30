"""
Finnhub-datakilde.
Env: FINNHUB_API_KEY
Ticker-format for Oslo Børs: EQNR.OL, DNB.OL osv.
"""
import os
import time
import logging
from typing import Optional

import requests

from .base import DataSource, StockData

log = logging.getLogger(__name__)

_EXCHANGE_SUFFIX = {
    "OSL": ".OL",
    "STO": ".ST",
    "CPH": ".CO",
    "HEL": ".HE",
    "US": "",
}
_BASE = "https://finnhub.io/api/v1"
_RATE_SLEEP = 0.25


class FinnhubDataSource(DataSource):
    def __init__(self, api_key: Optional[str] = None):
        self._key = api_key or os.environ.get("FINNHUB_API_KEY", "")
        if not self._key:
            raise EnvironmentError("FINNHUB_API_KEY ikke satt")

    def _get(self, path: str, params: dict) -> Optional[dict]:
        params["token"] = self._key
        try:
            r = requests.get(f"{_BASE}{path}", params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning("Finnhub-feil (%s): %s", path, exc)
            return None

    def _finnhub_ticker(self, ticker: str, exchange: str) -> str:
        suffix = _EXCHANGE_SUFFIX.get(exchange, "")
        return f"{ticker}{suffix}"

    def fetch(self, ticker: str, exchange: str, currency: str,
              name: str = "", ask_eligible: bool = True) -> StockData:
        fh_ticker = self._finnhub_ticker(ticker, exchange)
        sd = StockData(ticker=ticker, name=name or ticker, exchange=exchange,
                       currency=currency, ask_eligible=ask_eligible, source="finnhub")

        quote = self._get("/quote", {"symbol": fh_ticker})
        time.sleep(_RATE_SLEEP)
        if quote and quote.get("c"):
            sd.price = quote["c"]
            sd.prev_close = quote.get("pc")

        metrics_resp = self._get("/stock/metric", {"symbol": fh_ticker, "metric": "all"})
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

        reco = self._get("/stock/recommendation", {"symbol": fh_ticker})
        time.sleep(_RATE_SLEEP)
        if reco and isinstance(reco, list) and reco:
            latest = reco[0]
            total = (latest.get("strongBuy", 0) + latest.get("buy", 0) +
                     latest.get("hold", 0) + latest.get("sell", 0) +
                     latest.get("strongSell", 0))
            if total > 0:
                buys = latest.get("strongBuy", 0) + latest.get("buy", 0)
                sells = latest.get("sell", 0) + latest.get("strongSell", 0)
                if buys / total > 0.6:
                    sd.analyst_rating = "Kjøp"
                elif sells / total > 0.6:
                    sd.analyst_rating = "Selg"
                else:
                    sd.analyst_rating = "Hold"

        price_target = self._get("/stock/price-target", {"symbol": fh_ticker})
        time.sleep(_RATE_SLEEP)
        if price_target and price_target.get("targetMean"):
            sd.analyst_target_price = _nn(price_target["targetMean"])

        import datetime
        today = datetime.date.today()
        week_ago = today - datetime.timedelta(days=7)
        news_resp = self._get("/company-news", {
            "symbol": fh_ticker,
            "from": str(week_ago),
            "to": str(today),
        })
        time.sleep(_RATE_SLEEP)
        if news_resp and isinstance(news_resp, list):
            sd.news = [
                {
                    "headline": n.get("headline", ""),
                    "url": n.get("url", ""),
                    "datetime": n.get("datetime", 0),
                    "summary": n.get("summary", ""),
                }
                for n in news_resp[:10]
            ]

        return sd


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None
