"""Typed records passed from the data layer to analytics and UI.

Only the fields the app reasons about get a typed attribute; the full flattened
Yahoo payload stays available through ``Snapshot.get`` so new metrics can be
added without changing the schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

FUND_TYPES = {"ETF", "MUTUALFUND", "INDEX"}

# Industries whose statements make EV multiples, current ratio and Altman Z meaningless
FINANCIAL_INDUSTRY_KEYWORDS = (
    "bank", "insurance", "capital markets", "mortgage", "financial conglomerates",
    "shell companies",
)


@dataclass(frozen=True)
class SearchResult:
    symbol: str
    name: str
    quote_type: str
    exchange: str


@dataclass
class Snapshot:
    symbol: str
    name: str
    quote_type: str = "EQUITY"
    currency: str = "USD"
    currency_symbol: str = "$"
    exchange: str = ""
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    summary: str | None = None
    employees: int | None = None
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    market_cap: float | None = None
    market_state: str | None = None
    next_earnings: date | None = None
    ex_dividend: date | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.stats.get(key, default)
        return default if value is None else value

    @property
    def is_fund(self) -> bool:
        return self.quote_type.upper() in FUND_TYPES

    @property
    def is_financial(self) -> bool:
        industry = (self.industry or "").lower()
        return any(word in industry for word in FINANCIAL_INDUSTRY_KEYWORDS)


@dataclass
class Statements:
    """Annual statements (one row per fiscal year, oldest first) plus the latest TTM row."""

    income: pd.DataFrame
    balance: pd.DataFrame
    cashflow: pd.DataFrame
    income_ttm: pd.Series | None = None
    cashflow_ttm: pd.Series | None = None
    valuation: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def empty(self) -> bool:
        return self.income.empty and self.balance.empty and self.cashflow.empty


ESTIMATE_PERIODS = {"0q": "This quarter", "+1q": "Next quarter", "0y": "This fiscal year", "+1y": "Next fiscal year"}


@dataclass
class Insights:
    """Analyst estimates, earnings surprises, ratings and ownership for one company."""

    estimates: pd.DataFrame = field(default_factory=pd.DataFrame)      # one row per ESTIMATE_PERIODS key
    surprises: pd.DataFrame = field(default_factory=pd.DataFrame)      # quarterly actual vs estimate EPS
    recommendations: pd.DataFrame = field(default_factory=pd.DataFrame)  # rating counts per month (0m, -1m, …)
    grades: pd.DataFrame = field(default_factory=pd.DataFrame)         # rating / target changes, newest first
    insider_trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    institutions: pd.DataFrame = field(default_factory=pd.DataFrame)
    insider_summary: dict = field(default_factory=dict)
    holders: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return all(frame.empty for frame in (self.estimates, self.surprises, self.recommendations, self.grades))
