"""
Pluggbart datakilde-grensesnitt.
Ny datakilde: subklass DataSource og implementer fetch().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StockData:
    """Alle tall er None hvis kilden mangler dem – aldri gjetr."""
    ticker: str
    name: str
    exchange: str
    currency: str
    ask_eligible: bool

    price: Optional[float] = None
    prev_close: Optional[float] = None
    market_cap: Optional[float] = None

    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebit: Optional[float] = None
    ev_ebitda: Optional[float] = None
    free_cash_flow: Optional[float] = None
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None

    analyst_target_price: Optional[float] = None
    analyst_rating: Optional[str] = None

    news: list = field(default_factory=list)

    source: str = "unknown"
    fetch_error: Optional[str] = None


class DataSource(ABC):
    """Grensesnitt alle datakilder må implementere."""

    @abstractmethod
    def fetch(self, ticker: str, exchange: str, currency: str,
              name: str = "", ask_eligible: bool = True) -> StockData:
        ...

    def fetch_many(self, stocks: list[dict]) -> list[StockData]:
        results = []
        for s in stocks:
            results.append(self.fetch(
                ticker=s["ticker"],
                exchange=s.get("exchange", ""),
                currency=s.get("currency", ""),
                name=s.get("name", s["ticker"]),
                ask_eligible=s.get("ask_eligible", True),
            ))
        return results
