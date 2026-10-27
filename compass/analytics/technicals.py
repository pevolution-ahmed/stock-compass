"""Technical indicators (pure pandas, no Shiny).

``add_bollinger_bands`` and ``add_ichimoku`` add the band and cloud columns the price chart draws.
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


def indicators(history: pd.DataFrame) -> pd.DataFrame:
    """Price history plus every column the Technicals tab draws (computed on the full history)."""
    df = add_ichimoku(add_bollinger_bands(history))
    df["sma50"] = sma(df["close"], 50)
    df["sma200"] = sma(df["close"], 200)
    df["rsi"] = rsi(df["close"])
    return df.join(macd(df["close"]))


def last_cross(fast: pd.Series, slow: pd.Series) -> tuple[pd.Timestamp, bool] | None:
    """Date of the latest crossover and whether the fast line crossed above (True) or below."""
    above = (fast > slow).dropna()
    changes = above[above != above.shift()].iloc[1:]
    if changes.empty:
        return None
    return changes.index[-1], bool(changes.iloc[-1])


def signals(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Plain-language reading of the latest indicator values as (tone, headline, detail).

    Tone is "up" (supportive), "down" (cautionary) or "flat" (neutral).
    """
    last = df.iloc[-1]
    close = last["close"]
    out: list[tuple[str, str, str]] = []

    if pd.notna(last.get("sma200")):
        gap = close / last["sma200"] - 1
        out.append(("up" if gap > 0 else "down", "Long-term trend " + ("up" if gap > 0 else "down"),
                    f"Price is {abs(gap) * 100:.0f}% {'above' if gap > 0 else 'below'} its 200-day average."))
    cross = last_cross(df["sma50"], df["sma200"])
    if cross is not None:
        when, golden = cross
        out.append(("up" if golden else "down", "Golden cross" if golden else "Death cross",
                    f"50-day average crossed {'above' if golden else 'below'} the 200-day on {when:%b %d, %Y}."))
    if pd.notna(last.get("rsi")):
        value = last["rsi"]
        if value >= 70:
            out.append(("down", "Overbought", f"RSI {value:.0f}: strong recent gains; pullbacks are common from here."))
        elif value <= 30:
            out.append(("up", "Oversold", f"RSI {value:.0f}: heavy recent selling; rebounds are common from here."))
        else:
            out.append(("flat", "Momentum neutral", f"RSI {value:.0f} sits between oversold (30) and overbought (70)."))
    if pd.notna(last.get("macd")) and pd.notna(last.get("signal")):
        bullish = last["macd"] > last["signal"]
        out.append(("up" if bullish else "down", "MACD " + ("bullish" if bullish else "bearish"),
                    f"MACD is {'above' if bullish else 'below'} its signal line."))
    if pd.notna(last.get("upper_band")) and pd.notna(last.get("lower_band")):
        if close > last["upper_band"]:
            out.append(("down", "Above upper Bollinger band", "Price is stretched above its usual 20-day range."))
        elif close < last["lower_band"]:
            out.append(("up", "Below lower Bollinger band", "Price is stretched below its usual 20-day range."))
        else:
            width = (last["upper_band"] - last["lower_band"]) / last["middle_band"]
            out.append(("flat", "Inside Bollinger bands", f"Band width {width * 100:.0f}% of price."))
    if pd.notna(last.get("SpanA")) and pd.notna(last.get("SpanB")):
        top, bottom = max(last["SpanA"], last["SpanB"]), min(last["SpanA"], last["SpanB"])
        if close > top:
            out.append(("up", "Above the Ichimoku cloud", "The cloud acts as support below the price."))
        elif close < bottom:
            out.append(("down", "Below the Ichimoku cloud", "The cloud acts as resistance above the price."))
        else:
            out.append(("flat", "Inside the Ichimoku cloud", "Trend is undecided while price is in the cloud."))
    return out
