"""Technical indicators (pure pandas, no Shiny).

``add_bollinger_bands`` and ``add_ichimoku`` are carried over from the v1 app.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .performance import price_on_or_before, safe


def sma(prices: pd.Series, window: int) -> pd.Series:
    return prices.rolling(window=window).mean()


def rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's relative strength index."""
    delta = prices.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).where(loss != 0, 100.0)


def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = prices.ewm(span=fast, adjust=False).mean() - prices.ewm(span=slow, adjust=False).mean()
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "histogram": line - signal_line})


def momentum_12_1(prices: pd.Series) -> float | None:
    """Return from 12 months ago to 1 month ago — the classic momentum factor (skips the reversal month)."""
    end = prices.index[-1]
    start_price = price_on_or_before(prices, end - pd.DateOffset(months=12))
    end_price = price_on_or_before(prices, end - pd.DateOffset(months=1))
    if start_price is None or end_price is None or prices.index[0] > end - pd.DateOffset(months=12):
        return None
    return safe(end_price / start_price - 1)


def distance_from_sma(prices: pd.Series, window: int) -> float | None:
    if len(prices) < window:
        return None
    return safe(prices.iloc[-1] / sma(prices, window).iloc[-1] - 1)


def add_bollinger_bands(df: pd.DataFrame, window: int = 20, width: float = 1.96) -> pd.DataFrame:
    df = df.copy()
    rolling = df["close"].rolling(window=window)
    df["middle_band"] = rolling.mean()
    df["upper_band"] = df["middle_band"] + width * rolling.std()
    df["lower_band"] = df["middle_band"] - width * rolling.std()
    return df


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    midpoint = lambda window: (df["high"].rolling(window).max() + df["low"].rolling(window).min()) / 2
    df["Conversion"] = midpoint(9)
    df["Baseline"] = midpoint(26)
    df["SpanA"] = ((df["Conversion"] + df["Baseline"]) / 2).shift(26)
    df["SpanB"] = midpoint(52).shift(26)
    df["Lagging"] = df["close"].shift(-26)
    return df
