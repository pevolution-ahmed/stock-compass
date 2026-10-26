from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from compass.analytics import sentiment, technicals
from compass.data.clients import FixtureClient
from compass.data.provider import MarketDataProvider
from compass.data.schemas import Insights
from compass.state import Watchlist

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def estimates(**rows):
    return Insights(estimates=pd.DataFrame(rows).T)


def test_estimate_change_and_revision_score():
    data = estimates(**{"0y": {"trend_current": 10.5, "trend_90d": 10.0, "up_30d": 6, "down_30d": 2},
                        "+1y": {"trend_current": 12.0, "trend_90d": 12.0, "up_30d": 1, "down_30d": 1}})
    assert sentiment.estimate_change(data, "0y") == pytest.approx(0.05)
    assert sentiment.revision_breadth(data) == (7, 3)
    assert sentiment.revision_score(data) == pytest.approx(0.4)
    assert sentiment.revision_score(Insights()) is None


def test_surprise_stats_counts_beats():
    surprises = pd.DataFrame({"actual": [1.1, 0.9, 1.3, 1.0], "estimate": [1.0, 1.0, 1.2, 0.95],
                              "surprise": [0.10, -0.10, 0.083, 0.053]},
                             index=pd.date_range("2025-03-31", periods=4, freq="QE"))
    stats = sentiment.surprise_stats(Insights(surprises=surprises))
    assert (stats.quarters, stats.beats) == (4, 3)
    assert stats.beat_rate == 0.75


def test_fixture_insights_parse():
    data = MarketDataProvider(FixtureClient(FIXTURES)).insights("MSFT")
    assert {"0q", "+1q", "0y", "+1y"} <= set(data.estimates.index)
    assert not data.grades.empty and data.grades["date"].is_monotonic_decreasing
    assert sentiment.bullish_share(sentiment.current_ratings(data)) is not None


def test_last_cross_finds_most_recent_direction():
    index = pd.bdate_range("2024-01-01", periods=6)
    fast = pd.Series([1, 3, 3, 1, 1, 3], index=index, dtype=float)
    slow = pd.Series([2, 2, 2, 2, 2, 2], index=index, dtype=float)
    when, golden = technicals.last_cross(fast, slow)
    assert when == index[5] and golden


def test_signals_flag_overbought_and_uptrend():
    index = pd.bdate_range("2022-01-03", periods=400)
    close = pd.Series(100 * 1.003 ** np.arange(400), index=index)  # steady climb → high RSI
    history = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                            "adjclose": close, "volume": 1e6, "dividends": 0.0})
    headlines = [headline for _, headline, _ in technicals.signals(technicals.indicators(history))]
    assert "Long-term trend up" in headlines
    assert "Overbought" in headlines
    assert "Above the Ichimoku cloud" in headlines


def test_watchlist_dedupes_caps_and_toggles():
    watch = Watchlist(["aapl"])
    watch.replace(["msft", "MSFT", " nvda "])
    assert watch._current() == ["MSFT", "NVDA"]
    watch.toggle("MSFT")
    assert watch._current() == ["NVDA"]
    for i in range(20):
        watch.add(f"T{i}")
    assert len(watch._current()) == Watchlist.MAX
