"""Risk and risk-adjusted return metrics (pure pandas, no Shiny)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import config
from .performance import align, cagr, safe, trailing

TRADING_DAYS = config.TRADING_DAYS


def daily_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def monthly_returns(prices: pd.Series) -> pd.Series:
    return prices.resample("ME").last().pct_change().dropna()


def periods_per_year(prices: pd.Series) -> int:
    """Observations per year: ~252 for stocks, ~365 for crypto that trades every day."""
    if len(prices) < 30:
        return TRADING_DAYS
    recent = prices[prices.index > prices.index[-1] - pd.Timedelta(days=365)]
    span = (prices.index[-1] - prices.index[0]).days
    count = len(recent) if span >= 365 else len(prices) * 365 / max(span, 1)
    return int(min(max(round(count), 200), 366))


def volatility(returns: pd.Series, per_year: int = TRADING_DAYS) -> float | None:
    return safe(returns.std() * np.sqrt(per_year)) if len(returns) > 1 else None


def drawdown_series(prices: pd.Series) -> pd.Series:
    return prices / prices.cummax() - 1


@dataclass
class Drawdown:
    depth: float
    peak: pd.Timestamp
    trough: pd.Timestamp
    recovery: pd.Timestamp | None

    @property
    def days_to_trough(self) -> int:
        return (self.trough - self.peak).days

    @property
    def days_to_recover(self) -> int | None:
        return None if self.recovery is None else (self.recovery - self.trough).days


def max_drawdown(prices: pd.Series) -> Drawdown | None:
    if len(prices) < 2:
        return None
    drawdown = drawdown_series(prices)
    trough = drawdown.idxmin()
    peak = prices[:trough].idxmax()
    after = prices[trough:]
    recovered = after[after >= prices[peak]]
    return Drawdown(
        depth=float(drawdown.min()),
        peak=peak,
        trough=trough,
        recovery=recovered.index[0] if not recovered.empty else None,
    )


def sharpe(returns: pd.Series, risk_free: float, per_year: int = TRADING_DAYS) -> float | None:
    vol = volatility(returns, per_year)
    if not vol:
        return None
    return safe((returns.mean() * per_year - risk_free) / vol)


def sortino(returns: pd.Series, risk_free: float, per_year: int = TRADING_DAYS) -> float | None:
    excess = returns - risk_free / per_year
    downside = np.sqrt((np.minimum(excess, 0) ** 2).mean()) * np.sqrt(per_year)
    if not downside:
        return None
    return safe(excess.mean() * per_year / downside)


def calmar(prices: pd.Series) -> float | None:
    growth, drawdown = cagr(prices), max_drawdown(prices)
    if growth is None or drawdown is None or drawdown.depth == 0:
        return None
    return safe(growth / abs(drawdown.depth))


def beta(stock: pd.Series, benchmark: pd.Series) -> float | None:
    """Beta from monthly returns, matching how most data vendors quote it."""
    stock_r, bench_r = align(monthly_returns(stock), monthly_returns(benchmark))
    if len(stock_r) < 12 or bench_r.var() == 0:
        return None
    return safe(stock_r.cov(bench_r) / bench_r.var())


def correlation(stock: pd.Series, benchmark: pd.Series) -> float | None:
    stock_r, bench_r = align(daily_returns(stock), daily_returns(benchmark))
    return safe(stock_r.corr(bench_r)) if len(stock_r) > 20 else None


def value_at_risk(returns: pd.Series, level: float = 0.95) -> float | None:
    """One-day historical VaR as a positive loss fraction."""
    return safe(-returns.quantile(1 - level)) if len(returns) > 20 else None


def capture_ratios(stock: pd.Series, benchmark: pd.Series) -> tuple[float | None, float | None]:
    """Upside / downside capture vs the benchmark on monthly returns."""
    stock_r, bench_r = align(monthly_returns(stock), monthly_returns(benchmark))
    up, down = bench_r > 0, bench_r < 0
    ratio = lambda mask: safe(stock_r[mask].mean() / bench_r[mask].mean()) if mask.sum() >= 3 else None
    return ratio(up), ratio(down)


@dataclass
class RiskReport:
    years: float
    volatility: float | None
    beta: float | None
    correlation: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: Drawdown | None
    var_95: float | None
    up_capture: float | None
    down_capture: float | None


def risk_report(prices: pd.Series, benchmark: pd.Series | None, risk_free: float,
                years: float | None = 5) -> RiskReport:
    window = trailing(prices, years)
    returns = daily_returns(window)
    per_year = periods_per_year(window)
    bench = trailing(benchmark, years) if benchmark is not None else None
    up, down = capture_ratios(window, bench) if bench is not None else (None, None)
    return RiskReport(
        years=(window.index[-1] - window.index[0]).days / 365.25,
        volatility=volatility(returns, per_year),
        beta=beta(window, bench) if bench is not None else None,
        correlation=correlation(window, bench) if bench is not None else None,
        sharpe=sharpe(returns, risk_free, per_year),
        sortino=sortino(returns, risk_free, per_year),
        calmar=calmar(window),
        max_drawdown=max_drawdown(window),
        var_95=value_at_risk(returns),
        up_capture=up,
        down_capture=down,
    )
