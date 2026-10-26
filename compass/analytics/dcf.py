"""Two-stage free-cash-flow DCF, reverse DCF and sensitivity grid (pure Python).

Stage 1 grows FCF at ``growth`` for ``high_years``; stage 2 fades the growth
rate linearly to ``terminal_growth`` over ``fade_years``; a Gordon-growth
terminal value captures everything after. Equity value = enterprise value +
cash − debt, divided by shares outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

# Close to recent implied US equity risk premium estimates (~4–5%)
EQUITY_RISK_PREMIUM = 0.045


@dataclass(frozen=True)
class Assumptions:
    fcf: float               # starting (trailing) free cash flow
    shares: float
    net_cash: float          # cash − debt
    growth: float = 0.08     # stage-1 annual growth
    discount: float = 0.09
    terminal_growth: float = 0.025
    high_years: int = 5
    fade_years: int = 5


@dataclass
class Valuation:
    per_share: float
    enterprise_value: float
    equity_value: float
    terminal_share: float              # share of EV that comes from the terminal value
    years: list[int] = field(default_factory=list)
    cash_flows: list[float] = field(default_factory=list)
    present_values: list[float] = field(default_factory=list)


def growth_path(a: Assumptions) -> list[float]:
    fade = [a.growth + (a.terminal_growth - a.growth) * (i + 1) / (a.fade_years + 1) for i in range(a.fade_years)]
    return [a.growth] * a.high_years + fade


def value(a: Assumptions) -> Valuation | None:
    if a.fcf <= 0 or a.shares <= 0 or a.discount <= a.terminal_growth:
        return None
    flows, pvs = [], []
    cash = a.fcf
    for year, g in enumerate(growth_path(a), start=1):
        cash *= 1 + g
        flows.append(cash)
        pvs.append(cash / (1 + a.discount) ** year)
    horizon = len(flows)
    terminal = flows[-1] * (1 + a.terminal_growth) / (a.discount - a.terminal_growth)
    terminal_pv = terminal / (1 + a.discount) ** horizon
    enterprise = sum(pvs) + terminal_pv
    equity = enterprise + a.net_cash
    return Valuation(
        per_share=equity / a.shares,
        enterprise_value=enterprise,
        equity_value=equity,
        terminal_share=terminal_pv / enterprise if enterprise else float("nan"),
        years=list(range(1, horizon + 1)),
        cash_flows=flows,
        present_values=pvs,
    )


def implied_growth(a: Assumptions, price: float, low: float = -0.5, high: float = 1.0) -> float | None:
    """Stage-1 growth at which the DCF equals ``price`` (bisection; value rises with growth)."""
    if price <= 0:
        return None
    at = lambda g: (value(replace(a, growth=g)) or Valuation(-np.inf, 0, 0, 0)).per_share - price
    if at(low) > 0 or at(high) < 0:
        return None  # price is outside what any growth rate in range can justify
    for _ in range(80):
        mid = (low + high) / 2
        if at(mid) > 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def sensitivity(a: Assumptions, discounts: list[float], terminals: list[float]) -> list[list[float | None]]:
    """Fair value per share for each discount rate (rows) × terminal growth (columns)."""
    grid = []
    for r in discounts:
        row = []
        for g in terminals:
            result = value(replace(a, discount=r, terminal_growth=g))
            row.append(None if result is None else result.per_share)
        grid.append(row)
    return grid


def capm_discount(risk_free: float, beta: float | None, premium: float = EQUITY_RISK_PREMIUM) -> float:
    """Cost of equity = risk-free + beta × equity risk premium, kept to a sane 7–14% band."""
    beta = 1.0 if beta is None or not np.isfinite(beta) else min(max(beta, 0.5), 2.0)
    return float(min(max(risk_free + beta * premium, 0.07), 0.14))


def default_growth(fcf_cagr: float | None, revenue_cagr: float | None) -> float:
    """Starting stage-1 growth: recent revenue growth (FCF growth is noisier — capex cycles
    swing it), falling back to FCF growth, capped at 0–20%."""
    growth = revenue_cagr if revenue_cagr is not None else fcf_cagr
    return float(min(max(growth if growth is not None else 0.05, 0.0), 0.20))
