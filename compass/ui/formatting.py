"""Number and date formatting. Every formatter returns "—" for missing values."""

from __future__ import annotations

import math
from datetime import date

MISSING = "—"


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and not math.isfinite(value))


def money(value, symbol: str = "$", compact: bool = True, decimals: int = 2) -> str:
    if is_missing(value):
        return MISSING
    sign = "-" if value < 0 else ""
    value = abs(value)
    if compact:
        for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if value >= limit:
                return f"{sign}{symbol}{value / limit:,.{decimals}f}{suffix}"
    return f"{sign}{symbol}{value:,.{decimals}f}"


def amount(value, symbol: str = "$") -> str:
    """Whole currency amounts, compact only from a million up ($17,620 · $1.25M)."""
    if is_missing(value):
        return MISSING
    return money(value, symbol, compact=abs(value) >= 1e6, decimals=2 if abs(value) >= 1e6 else 0)


def price(value, symbol: str = "$") -> str:
    return money(value, symbol, compact=False, decimals=2)


def pct(value, decimals: int = 1, sign: bool = False) -> str:
    if is_missing(value):
        return MISSING
    return f"{value * 100:+,.{decimals}f}%" if sign else f"{value * 100:,.{decimals}f}%"


def mult(value, decimals: int = 1) -> str:
    return MISSING if is_missing(value) else f"{value:,.{decimals}f}x"


def num(value, decimals: int = 2) -> str:
    return MISSING if is_missing(value) else f"{value:,.{decimals}f}"


def integer(value) -> str:
    return MISSING if is_missing(value) else f"{value:,.0f}"


def by_kind(value, kind: str) -> str:
    """Format by a short kind name, as used by scoring rules."""
    return {"pct": pct, "x": mult, "ratio": num}.get(kind, num)(value)


def day(value: date | None) -> str:
    return MISSING if value is None else f"{value:%b} {value.day}, {value:%Y}"


def tone(value, neutral: float = 0.0) -> str:
    if is_missing(value) or value == neutral:
        return "flat"
    return "up" if value > neutral else "down"
