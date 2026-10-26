"""Valuation multiples now vs their own recent history (pure pandas)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Yahoo's quarterly valuation_measures column → (label, current-value metric key)
HISTORY_COLUMNS = {
    "PeRatio": ("P/E (trailing)", "trailing_pe"),
    "ForwardPeRatio": ("P/E (forward)", "forward_pe"),
    "EnterprisesValueEBITDARatio": ("EV / EBITDA", "ev_ebitda"),
    "PsRatio": ("Price / sales", "price_to_sales"),
    "PbRatio": ("Price / book", "price_to_book"),
    "EnterprisesValueRevenueRatio": ("EV / revenue", "ev_revenue"),
    "PegRatio": ("PEG", "peg"),
}


@dataclass
class MultipleContext:
    label: str
    current: float | None
    median: float | None
    low: float | None
    high: float | None
    points: int

    @property
    def premium(self) -> float | None:
        """Current vs median: +0.20 means 20% more expensive than usual."""
        if self.current is None or not self.median or self.median <= 0 or self.current <= 0:
            return None
        return self.current / self.median - 1


def history_series(valuation: pd.DataFrame, column: str) -> pd.Series:
    if valuation is None or valuation.empty or column not in valuation:
        return pd.Series(dtype=float)
    series = pd.to_numeric(valuation[column], errors="coerce").dropna()
    return series[series > 0]


def context(valuation: pd.DataFrame, metrics: dict) -> dict[str, MultipleContext]:
    result = {}
    for column, (label, key) in HISTORY_COLUMNS.items():
        series = history_series(valuation, column)
        current = metrics.get(key)
        result[key] = MultipleContext(
            label=label,
            current=current,
            median=float(series.median()) if len(series) >= 4 else None,
            low=float(series.min()) if len(series) >= 4 else None,
            high=float(series.max()) if len(series) >= 4 else None,
            points=len(series),
        )
    return result


def history_years(valuation: pd.DataFrame) -> float:
    if valuation is None or valuation.empty:
        return 0.0
    return (valuation.index[-1] - valuation.index[0]).days / 365.25
