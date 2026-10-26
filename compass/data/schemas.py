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

# Quote types that aren't operating companies (no statements, estimates or company valuation)
NON_COMPANY_TYPES = {"ETF", "MUTUALFUND", "INDEX", "CRYPTOCURRENCY", "CURRENCY", "FUTURE"}
KIND_PHRASES = {"ETF": "an ETF", "MUTUALFUND": "a mutual fund", "INDEX": "an index",
                "CRYPTOCURRENCY": "a cryptocurrency", "CURRENCY": "a currency", "FUTURE": "a futures contract"}
KIND_LABELS = {"ETF": "ETF", "MUTUALFUND": "Mutual fund", "INDEX": "Index", "CRYPTOCURRENCY": "Crypto",
               "CURRENCY": "Currency", "FUTURE": "Futures"}

# Some exchanges quote prices in a minor unit (London in pence): code → (major currency, major per unit)
MINOR_UNITS = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "TWD": "NT$", "KRW": "₩", "INR": "₹",
    "CAD": "C$", "AUD": "A$", "NZD": "NZ$", "HKD": "HK$", "SGD": "S$", "CHF": "CHF ", "SEK": "kr ",
    "NOK": "kr ", "DKK": "kr ", "BRL": "R$", "MXN": "MX$", "ZAR": "R ", "ILS": "₪", "RUB": "₽", "TRY": "₺",
}


def currency_symbol(code: str | None) -> str:
    return CURRENCY_SYMBOLS.get(code or "", f"{code} " if code else "")


def major_currency(code: str) -> tuple[str, float]:
    """(major currency, major units per quoted unit): GBp → (GBP, 0.01)."""
    return MINOR_UNITS.get(code, (code, 1.0))

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
    financial_currency: str | None = None  # currency of the financial statements (TSM reports in TWD)
    fx: float | None = 1.0                 # financial currency → quote's major currency; None if unknown
    price_unit: float = 1.0                # major units per quoted price unit (0.01 for prices in pence)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.stats.get(key, default)
        return default if value is None else value

    @property
    def is_fund(self) -> bool:
        """True for anything that isn't an operating company (ETFs, indices, crypto, …)."""
        return self.quote_type.upper() in NON_COMPANY_TYPES

    @property
    def kind_phrase(self) -> str:
        return KIND_PHRASES.get(self.quote_type.upper(), "this kind of asset")

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.quote_type.upper(), self.quote_type.title())

    @property
    def major_currency(self) -> str:
        return major_currency(self.currency)[0]

    @property
    def major_symbol(self) -> str:
        """Symbol for amounts in the quote's major unit (market cap, invested amounts)."""
        return currency_symbol(self.major_currency)

    @property
    def statement_symbol(self) -> str:
        """Symbol for amounts taken from the financial statements."""
        return currency_symbol(self.financial_currency or self.major_currency)

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
