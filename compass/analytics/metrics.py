"""Flat metric set (name → value) that the scorecard, tiles and watchlist read from.

Each metric is a plain float (fractions for percentages) or None when it can't
be computed, so consumers never need to know where a number came from.
"""

from __future__ import annotations

import pandas as pd

from ..data.normalize import to_float
from ..data.schemas import Snapshot, Statements
from . import performance, technicals

Metrics = dict[str, float | None]


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def ttm_value(statements: Statements | None, kind: str, field: str) -> float | None:
    """Latest trailing-twelve-month value, falling back to the latest fiscal year."""
    if statements is None:
        return None
    ttm = statements.cashflow_ttm if kind == "cashflow" else statements.income_ttm
    annual = statements.cashflow if kind == "cashflow" else statements.income
    if ttm is not None and to_float(ttm.get(field)) is not None:
        return to_float(ttm.get(field))
    if field in annual and not annual[field].dropna().empty:
        return to_float(annual[field].dropna().iloc[-1])
    return None


def snapshot_metrics(snapshot: Snapshot, statements: Statements | None = None) -> Metrics:
    get = lambda key: to_float(snapshot.get(key))
    price, market_cap = snapshot.price, snapshot.market_cap
    revenue = get("totalRevenue") or ttm_value(statements, "income", "TotalRevenue")
    # Statement FCF (operating cash flow − capex); Yahoo's financialData figure is levered and often far off
    fcf = ttm_value(statements, "cashflow", "FreeCashFlow")
    ebitda, debt, cash = get("ebitda"), get("totalDebt"), get("totalCash")
    low, high = get("fiftyTwoWeekLow"), get("fiftyTwoWeekHigh")
    trailing_pe = get("trailingPE")

    return {
        "price": price,
        "market_cap": market_cap,
        "forward_pe": get("forwardPE"),
        "trailing_pe": trailing_pe,
        "peg": get("pegRatio") or get("trailingPegRatio"),
        "ev_ebitda": get("enterpriseToEbitda"),
        "ev_revenue": get("enterpriseToRevenue"),
        "price_to_sales": get("priceToSalesTrailing12Months"),
        "price_to_book": get("priceToBook"),
        "fcf": fcf,
        "fcf_yield": ratio(fcf, market_cap),
        "earnings_yield": ratio(1.0, trailing_pe),
        "dividend_yield": get("dividendYield") or get("yield") or get("trailingAnnualDividendYield"),
        "dividend_yield_5y": get("fiveYearAvgDividendYield"),
        "payout_ratio": get("payoutRatio"),
        "roe": get("returnOnEquity"),
        "roa": get("returnOnAssets"),
        "gross_margin": get("grossMargins"),
        "operating_margin": get("operatingMargins"),
        "net_margin": get("profitMargins"),
        "fcf_margin": ratio(fcf, revenue),
        "revenue_growth": get("revenueGrowth"),
        "earnings_growth": get("earningsGrowth"),
        "debt_to_equity": get("debtToEquity"),
        "current_ratio": get("currentRatio"),
        "quick_ratio": get("quickRatio"),
        "net_debt_ebitda": ratio((debt or 0) - (cash or 0), ebitda) if ebitda and ebitda > 0 else None,
        "analyst_target": get("targetMeanPrice"),
        "analyst_upside": ratio(get("targetMeanPrice"), price) - 1 if get("targetMeanPrice") and price else None,
        "recommendation_mean": get("recommendationMean"),
        "analyst_count": get("numberOfAnalystOpinions"),
        "short_float": get("shortPercentOfFloat"),
        "range_52w_position": ratio((price or 0) - low, high - low) if price and low and high and high > low else None,
    }


def price_metrics(prices: pd.Series, benchmark: pd.Series | None = None) -> Metrics:
    one_year = performance.period_returns(prices).get("1Y")
    bench_year = performance.period_returns(benchmark).get("1Y") if benchmark is not None else None
    sma50 = technicals.sma(prices, 50).iloc[-1] if len(prices) >= 50 else None
    sma200 = technicals.sma(prices, 200).iloc[-1] if len(prices) >= 200 else None
    rsi = technicals.rsi(prices).iloc[-1] if len(prices) > 15 else None
    return {
        "return_1y": one_year,
        "momentum_12_1": technicals.momentum_12_1(prices),
        "vs_sma200": technicals.distance_from_sma(prices, 200),
        "sma50_vs_sma200": ratio(sma50, sma200) - 1 if sma50 and sma200 else None,
        "relative_1y": one_year - bench_year if one_year is not None and bench_year is not None else None,
        "rsi14": performance.safe(rsi),
    }
