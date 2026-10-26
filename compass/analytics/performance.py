"""Returns and ROI from a daily price series (pure pandas, no Shiny).

``prices`` arguments are dividend-adjusted closes (``adjclose``) indexed by date
unless stated otherwise, so every return here is a total return.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PERIODS: dict[str, pd.DateOffset | None] = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "YTD": None,
    "1Y": pd.DateOffset(years=1),
    "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
    "10Y": pd.DateOffset(years=10),
    "Max": None,
}
DAYS_PER_YEAR = 365.25


def price_on_or_before(prices: pd.Series, when: pd.Timestamp) -> float | None:
    position = prices.index.searchsorted(pd.Timestamp(when), side="right") - 1
    return None if position < 0 else float(prices.iloc[position])


def period_start(prices: pd.Series, label: str) -> pd.Timestamp | None:
    """Date whose close the period return is measured from, or None if history is too short."""
    first, last = prices.index[0], prices.index[-1]
    if label == "Max":
        return first
    if label == "YTD":
        start = pd.Timestamp(last.year - 1, 12, 31)
        return start if start >= first else first
    start = last - PERIODS[label]
    return start if start >= first else None


def total_return(prices: pd.Series, start: pd.Timestamp) -> float | None:
    base = price_on_or_before(prices, start)
    if base is None:
        base = float(prices.iloc[0])
    return float(prices.iloc[-1]) / base - 1 if base else None


def annualize(total: float, days: float) -> float | None:
    if days <= 0 or total <= -1:
        return None
    return (1 + total) ** (DAYS_PER_YEAR / days) - 1


def cagr(prices: pd.Series, start: pd.Timestamp | None = None) -> float | None:
    start = prices.index[0] if start is None else max(pd.Timestamp(start), prices.index[0])
    total = total_return(prices, start)
    days = (prices.index[-1] - start).days
    return None if total is None else annualize(total, days)


def period_returns(prices: pd.Series) -> dict[str, float | None]:
    result = {}
    for label in PERIODS:
        start = period_start(prices, label)
        result[label] = None if start is None else total_return(prices, start)
    return result


def trailing(prices: pd.Series, years: float | None) -> pd.Series:
    """Last ``years`` of the series (all of it when None or when history is shorter)."""
    if years is None:
        return prices
    start = prices.index[-1] - pd.DateOffset(months=int(round(years * 12)))
    return prices[prices.index >= start]


def rebase(prices: pd.Series, base: float = 100.0) -> pd.Series:
    return prices / prices.iloc[0] * base


def calendar_year_returns(prices: pd.Series) -> pd.Series:
    """Return per calendar year; the first year is measured from the first price."""
    year_end = prices.resample("YE").last()
    returns = year_end.pct_change()
    returns.iloc[0] = year_end.iloc[0] / prices.iloc[0] - 1
    returns.index = returns.index.year
    return returns


def monthly_returns(prices: pd.Series) -> pd.DataFrame:
    """Year × month table of monthly returns."""
    month_end = prices.resample("ME").last()
    returns = month_end.pct_change()
    returns.iloc[0] = month_end.iloc[0] / prices.iloc[0] - 1
    table = pd.DataFrame({"year": returns.index.year, "month": returns.index.month, "r": returns.values})
    return table.pivot(index="year", columns="month", values="r").reindex(columns=range(1, 13))


@dataclass
class ReturnStats:
    best_day: tuple[pd.Timestamp, float]
    worst_day: tuple[pd.Timestamp, float]
    best_month: tuple[pd.Timestamp, float]
    worst_month: tuple[pd.Timestamp, float]
    positive_days: float
    positive_months: float


def return_stats(prices: pd.Series) -> ReturnStats | None:
    daily = prices.pct_change().dropna()
    monthly = prices.resample("ME").last().pct_change().dropna()
    if daily.empty or monthly.empty:
        return None
    extremes = lambda s: ((s.idxmax(), float(s.max())), (s.idxmin(), float(s.min())))
    (best_day, worst_day), (best_month, worst_month) = extremes(daily), extremes(monthly)
    return ReturnStats(best_day, worst_day, best_month, worst_month,
                       float((daily > 0).mean()), float((monthly > 0).mean()))


@dataclass
class InvestmentResult:
    start: pd.Timestamp
    invested: float
    value: pd.Series
    final_value: float
    gain: float
    gain_pct: float
    cagr: float | None
    dividends: float


def investment_growth(history: pd.DataFrame, amount: float, start: pd.Timestamp,
                      reinvest: bool = True) -> InvestmentResult | None:
    """Value of ``amount`` invested at the close on/after ``start``.

    With ``reinvest`` dividends buy more shares (adjusted closes); without, they
    accumulate as cash at their ex-date.
    """
    period = history[history.index >= pd.Timestamp(start)]
    if period.empty or amount <= 0:
        return None
    first = period.index[0]
    if reinvest:
        value = amount * period["adjclose"] / period["adjclose"].iloc[0]
        dividends = 0.0
    else:
        shares = amount / period["close"].iloc[0]
        cash = shares * period["dividends"].where(period.index > first, 0.0).cumsum()
        value = shares * period["close"] + cash
        dividends = float(cash.iloc[-1])
    final = float(value.iloc[-1])
    gain_pct = final / amount - 1
    return InvestmentResult(
        start=first, invested=amount, value=value, final_value=final,
        gain=final - amount, gain_pct=gain_pct,
        cagr=annualize(gain_pct, (period.index[-1] - first).days),
        dividends=dividends,
    )


def align(*series: pd.Series) -> list[pd.Series]:
    """Restrict several price series to their common dates."""
    frame = pd.concat(series, axis=1, join="inner").dropna()
    return [frame.iloc[:, i] for i in range(frame.shape[1])]


def safe(value: float | None) -> float | None:
    return None if value is None or not np.isfinite(value) else float(value)
