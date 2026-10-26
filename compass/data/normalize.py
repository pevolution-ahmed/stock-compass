"""Turn raw yahooquery payloads into the typed records in ``schemas``.

Yahoo answers per symbol with either a dict or an error string, omits fields
freely and mixes date formats, so every accessor here tolerates missing data.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .schemas import ESTIMATE_PERIODS, Insights, SearchResult, Snapshot, Statements, currency_symbol, major_currency

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

    currency = price.get("currency") or "USD"
    major, price_unit = major_currency(currency)
    return Snapshot(
        symbol=symbol.upper(),
        name=price.get("longName") or price.get("shortName") or symbol.upper(),
        quote_type=str(quote_type.get("quoteType") or price.get("quoteType") or "EQUITY"),
        currency=currency,
        # Prices quoted in a minor unit (pence) are shown as plain numbers next to the currency code
        currency_symbol="" if price_unit != 1.0 else (price.get("currencySymbol") or currency_symbol(currency)),
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
        financial_currency=stats.get("financialCurrency") or major,
        price_unit=price_unit,
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


def _lower_keys(payload: dict) -> dict:
    return {str(k).lower(): v for k, v in payload.items()} if isinstance(payload, dict) else {}


def _frame(rows: list[dict], columns: dict[str, str], date_column: str | None = None) -> pd.DataFrame:
    """Rows of Yahoo dicts → DataFrame with renamed columns (missing keys become NaN)."""
    if not rows:
        return pd.DataFrame(columns=list(columns.values()))
    frame = pd.DataFrame([{new: row.get(old) for old, new in columns.items()} for row in rows])
    if date_column and date_column in frame:
        frame[date_column] = pd.to_datetime([str(v)[:10] if v else None for v in frame[date_column]],
                                            errors="coerce")
    return frame


def insights(payload: Any) -> Insights:
    if not isinstance(payload, dict):
        return Insights()

    rows = []
    for trend in module(payload, "earningsTrend").get("trend", []) or []:
        if trend.get("period") not in ESTIMATE_PERIODS:
            continue
        eps, revenue = trend.get("earningsEstimate") or {}, trend.get("revenueEstimate") or {}
        eps_trend = trend.get("epsTrend") or {}
        revisions = _lower_keys(trend.get("epsRevisions") or {})
        rows.append({
            "period": trend.get("period"), "end": to_date(trend.get("endDate")),
            "eps_avg": to_float(eps.get("avg")), "eps_low": to_float(eps.get("low")),
            "eps_high": to_float(eps.get("high")), "eps_year_ago": to_float(eps.get("yearAgoEps")),
            "eps_growth": to_float(eps.get("growth")), "eps_analysts": to_float(eps.get("numberOfAnalysts")),
            "rev_avg": to_float(revenue.get("avg")), "rev_low": to_float(revenue.get("low")),
            "rev_high": to_float(revenue.get("high")), "rev_growth": to_float(revenue.get("growth")),
            "rev_analysts": to_float(revenue.get("numberOfAnalysts")),
            "trend_current": to_float(eps_trend.get("current")), "trend_7d": to_float(eps_trend.get("7daysAgo")),
            "trend_30d": to_float(eps_trend.get("30daysAgo")), "trend_60d": to_float(eps_trend.get("60daysAgo")),
            "trend_90d": to_float(eps_trend.get("90daysAgo")),
            "up_7d": to_float(revisions.get("uplast7days")), "up_30d": to_float(revisions.get("uplast30days")),
            "down_7d": to_float(revisions.get("downlast7days")), "down_30d": to_float(revisions.get("downlast30days")),
        })
    estimates = pd.DataFrame(rows).set_index("period") if rows else pd.DataFrame()

    surprises = _frame(module(payload, "earningsHistory").get("history", []) or [],
                       {"quarter": "quarter", "epsActual": "actual", "epsEstimate": "estimate",
                        "surprisePercent": "surprise"}, "quarter")
    surprises = surprises.dropna(subset=["quarter", "actual"]).sort_values("quarter").set_index("quarter") \
        if not surprises.empty else surprises

    recommendations = _frame(module(payload, "recommendationTrend").get("trend", []) or [],
                             {"period": "period", "strongBuy": "Strong buy", "buy": "Buy", "hold": "Hold",
                              "sell": "Sell", "strongSell": "Strong sell"})
    recommendations = recommendations.set_index("period") if not recommendations.empty else recommendations

    grades = _frame(module(payload, "upgradeDowngradeHistory").get("history", []) or [],
                    {"epochGradeDate": "date", "firm": "firm", "fromGrade": "from", "toGrade": "to",
                     "action": "action", "priceTargetAction": "target_action",
                     "currentPriceTarget": "target", "priorPriceTarget": "prior_target"}, "date")
    grades = grades.sort_values("date", ascending=False).reset_index(drop=True) if not grades.empty else grades

    insider_trades = _frame(module(payload, "insiderTransactions").get("transactions", []) or [],
                            {"startDate": "date", "filerName": "name", "filerRelation": "relation",
                             "transactionText": "text", "shares": "shares", "value": "value"}, "date")
    insider_trades = (insider_trades.sort_values("date", ascending=False).reset_index(drop=True)
                      if not insider_trades.empty else insider_trades)

    institutions = _frame(module(payload, "institutionOwnership").get("ownershipList", []) or [],
                          {"organization": "holder", "pctHeld": "pct_held", "position": "shares",
                           "value": "value", "pctChange": "pct_change", "reportDate": "reported"}, "reported")

    return Insights(
        estimates=estimates, surprises=surprises, recommendations=recommendations, grades=grades,
        insider_trades=insider_trades, institutions=institutions,
        insider_summary=module(payload, "netSharePurchaseActivity"),
        holders=module(payload, "majorHoldersBreakdown"),
    )
