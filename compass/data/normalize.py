"""Turn raw yahooquery payloads into the typed records in ``schemas``.

Yahoo answers per symbol with either a dict or an error string, omits fields
freely and mixes date formats, so every accessor here tolerates missing data.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .schemas import SearchResult, Snapshot, Statements

PRICE_COLUMNS = ["open", "high", "low", "close", "adjclose", "volume", "dividends"]

# Later modules win when the same key appears in several
STAT_MODULES = ["price", "summaryDetail", "defaultKeyStatistics", "financialData"]


class DataUnavailable(Exception):
    """Yahoo returned nothing usable for the request."""


class SymbolNotFound(DataUnavailable):
    pass


def module(payload: Any, name: str) -> dict:
    value = payload.get(name) if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else {}


def to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return to_date(value[0]) if value else None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not np.isnan(value):
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if isinstance(value, dict):  # formatted payloads wrap numbers as {"raw": ...}
        value = value.get("raw")
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(number) or np.isinf(number) else number


def snapshot(symbol: str, payload: Any) -> Snapshot:
    if not isinstance(payload, dict) or not module(payload, "price"):
        raise SymbolNotFound(payload if isinstance(payload, str) else f"No quote for {symbol}")

    price = module(payload, "price")
    profile = module(payload, "assetProfile") or module(payload, "summaryProfile")
    quote_type = module(payload, "quoteType")
    calendar = module(payload, "calendarEvents")

    stats: dict[str, Any] = {}
    for name in STAT_MODULES:
        stats.update({k: v for k, v in module(payload, name).items() if v is not None})
    # Yahoo reports these as percentages (32.7 == 0.327x, 0.78 == 0.78%) unlike its other ratios
    for key in ("debtToEquity", "fiveYearAvgDividendYield"):
        if to_float(stats.get(key)) is not None:
            stats[key] = to_float(stats[key]) / 100

    return Snapshot(
        symbol=symbol.upper(),
        name=price.get("longName") or price.get("shortName") or symbol.upper(),
        quote_type=str(quote_type.get("quoteType") or price.get("quoteType") or "EQUITY"),
        currency=price.get("currency") or "USD",
        currency_symbol=price.get("currencySymbol") or "$",
        exchange=price.get("exchangeName") or price.get("exchange") or "",
        sector=profile.get("sectorDisp") or profile.get("sector"),
        industry=profile.get("industryDisp") or profile.get("industry"),
        website=profile.get("website"),
        summary=profile.get("longBusinessSummary"),
        employees=profile.get("fullTimeEmployees"),
        price=to_float(price.get("regularMarketPrice")),
        change=to_float(price.get("regularMarketChange")),
        change_pct=to_float(price.get("regularMarketChangePercent")),
        market_cap=to_float(price.get("marketCap")) or to_float(stats.get("marketCap")),
        market_state=price.get("marketState"),
        next_earnings=to_date(module(calendar, "earnings").get("earningsDate")),
        ex_dividend=to_date(calendar.get("exDividendDate")),
        stats=stats,
    )


def history(raw: Any, symbol: str) -> pd.DataFrame:
    """Daily prices for one symbol, indexed by tz-naive date, oldest first."""
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise DataUnavailable(f"No price history for {symbol}")
    frame = raw.reset_index()
    if "symbol" in frame:
        frame = frame[frame["symbol"] == symbol.upper()]
    if frame.empty:
        raise DataUnavailable(f"No price history for {symbol}")

    # Daily rows are dates; the live row may be a tz-aware timestamp, so parse the date part only
    frame["date"] = pd.to_datetime([str(d)[:10] for d in frame["date"]])
    frame = frame.set_index("date").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for column in PRICE_COLUMNS:
        if column not in frame:
            frame[column] = 0.0 if column == "dividends" else np.nan
    frame["adjclose"] = frame["adjclose"].fillna(frame["close"])
    frame["dividends"] = frame["dividends"].fillna(0.0)
    return frame[PRICE_COLUMNS].dropna(subset=["close"])


def _annual(raw: Any) -> tuple[pd.DataFrame, pd.Series | None]:
    if not isinstance(raw, pd.DataFrame) or raw.empty or "asOfDate" not in raw:
        return pd.DataFrame(), None
    frame = raw.reset_index(drop=True).copy()
    frame["asOfDate"] = pd.to_datetime(frame["asOfDate"])
    frame = frame.sort_values("asOfDate")
    numeric = lambda df: df.drop(columns=["periodType", "currencyCode"], errors="ignore").set_index("asOfDate")
    annual = numeric(frame[frame["periodType"] == "12M"])
    ttm_rows = frame[frame["periodType"] == "TTM"]
    ttm = numeric(ttm_rows).iloc[-1] if not ttm_rows.empty else None
    return annual, ttm


def statements(raw: dict[str, Any]) -> Statements:
    income, income_ttm = _annual(raw.get("income"))
    balance, _ = _annual(raw.get("balance"))
    cashflow, cashflow_ttm = _annual(raw.get("cashflow"))

    valuation = raw.get("valuation")
    if isinstance(valuation, pd.DataFrame) and not valuation.empty and "asOfDate" in valuation:
        valuation = valuation.reset_index(drop=True).copy()
        valuation["asOfDate"] = pd.to_datetime(valuation["asOfDate"])
        valuation = (valuation.drop(columns=["periodType"], errors="ignore")
                     .set_index("asOfDate").sort_index())
        valuation = valuation[~valuation.index.duplicated(keep="last")]
    else:
        valuation = pd.DataFrame()

    return Statements(income, balance, cashflow, income_ttm, cashflow_ttm, valuation)


def search_results(raw: Any, limit: int) -> list[SearchResult]:
    quotes = raw.get("quotes", []) if isinstance(raw, dict) else []
    results = []
    for quote in quotes:
        symbol = quote.get("symbol")
        if not symbol or quote.get("quoteType") not in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}:
            continue
        results.append(SearchResult(
            symbol=symbol,
            name=quote.get("longname") or quote.get("shortname") or symbol,
            quote_type=quote.get("quoteType", ""),
            exchange=quote.get("exchDisp") or quote.get("exchange", ""),
        ))
    return results[:limit]
