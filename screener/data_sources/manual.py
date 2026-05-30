"""
Manuell fallback-datakilde.
Bruker tall fra config.json → manual_data for aksjene.
Nyttig for Nordiske aksjer der Finnhub mangler data.
"""
import logging
from typing import Optional

from .base import DataSource, StockData

log = logging.getLogger(__name__)


class ManualDataSource(DataSource):
    """Wrapper: leser ferdig-lastede manual_data-dicts fra config."""

    def __init__(self, manual_map: dict[str, dict]):
        # manual_map: {ticker: manual_data_dict}
        self._map = manual_map

    def fetch(self, ticker: str, exchange: str, currency: str,
              name: str = "", ask_eligible: bool = True) -> StockData:
        md = self._map.get(ticker, {})
        sd = StockData(ticker=ticker, name=name or ticker, exchange=exchange,
                       currency=currency, ask_eligible=ask_eligible, source="manual")
        sd.price = _nn(md.get("price"))
        sd.pe_ratio = _nn(md.get("pe_ratio"))
        sd.pb_ratio = _nn(md.get("pb_ratio"))
        sd.ev_ebit = _nn(md.get("ev_ebit"))
        sd.ev_ebitda = _nn(md.get("ev_ebitda"))
        sd.free_cash_flow = _nn(md.get("free_cash_flow"))
        sd.dividend_yield = _nn(md.get("dividend_yield"))
        if sd.price is None:
            log.warning("ManualDataSource: ingen kurs for %s", ticker)
        return sd


def _nn(val) -> Optional[float]:
    try:
        f = float(val)
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


class FallbackDataSource(DataSource):
    """
    Kjeder to kilder: prøv primær først, fyll hull med sekundær.
    Brukes slik: FallbackDataSource(primary=FinnhubDataSource(), secondary=ManualDataSource(...))
    """

    def __init__(self, primary: DataSource, secondary: DataSource):
        self._primary = primary
        self._secondary = secondary

    def fetch(self, ticker: str, exchange: str, currency: str,
              name: str = "", ask_eligible: bool = True) -> StockData:
        result = self._primary.fetch(ticker, exchange, currency, name, ask_eligible)
        fallback = self._secondary.fetch(ticker, exchange, currency, name, ask_eligible)

        # Fyll None-felt fra sekundær
        for field_name in [
            "price", "prev_close", "pe_ratio", "pb_ratio", "ps_ratio",
            "ev_ebit", "ev_ebitda", "free_cash_flow", "dividend_yield",
            "roe", "debt_to_equity", "analyst_target_price",
        ]:
            if getattr(result, field_name) is None:
                val = getattr(fallback, field_name)
                if val is not None:
                    setattr(result, field_name, val)
                    log.debug("Bruker manuell verdi for %s.%s", ticker, field_name)

        return result
