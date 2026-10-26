"""What analysts and insiders are doing: estimate revisions, earnings surprises, ratings (pure pandas)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.schemas import Insights

RATINGS = ["Strong buy", "Buy", "Hold", "Sell", "Strong sell"]


def _value(frame: pd.DataFrame, period: str, column: str) -> float | None:
    if frame.empty or period not in frame.index or column not in frame:
        return None
    value = frame.at[period, column]
    return None if pd.isna(value) else float(value)


def estimate_change(insights: Insights, period: str = "0y", days: int = 90) -> float | None:
    """How much the consensus EPS estimate moved over the last ``days`` (e.g. +0.02 = raised 2%)."""
    now = _value(insights.estimates, period, "trend_current")
    before = _value(insights.estimates, period, f"trend_{days}d")
    if now is None or not before or before <= 0:
        return None
    return now / before - 1


def revision_breadth(insights: Insights, periods=("0y", "+1y")) -> tuple[int, int] | None:
    """(analysts raising, analysts cutting) EPS estimates over the last 30 days."""
    up = [_value(insights.estimates, p, "up_30d") for p in periods]
    down = [_value(insights.estimates, p, "down_30d") for p in periods]
    if all(v is None for v in up + down):
        return None
    return int(sum(v or 0 for v in up)), int(sum(v or 0 for v in down))


def revision_score(insights: Insights) -> float | None:
    """Net share of revisions that were upgrades: +1 all raised, −1 all cut."""
    breadth = revision_breadth(insights)
    if breadth is None or sum(breadth) == 0:
        return None
    up, down = breadth
    return (up - down) / (up + down)


@dataclass
class SurpriseStats:
    quarters: int
    beats: int
    average_surprise: float

    @property
    def beat_rate(self) -> float:
        return self.beats / self.quarters


def surprise_stats(insights: Insights) -> SurpriseStats | None:
    s = insights.surprises
    if s.empty or "actual" not in s:
        return None
    s = s.dropna(subset=["actual", "estimate"])
    if s.empty:
        return None
    surprise = s["surprise"] if "surprise" in s else (s["actual"] - s["estimate"]) / s["estimate"].abs()
    return SurpriseStats(len(s), int((s["actual"] > s["estimate"]).sum()), float(np.nanmean(surprise)))


def current_ratings(insights: Insights) -> pd.Series | None:
    r = insights.recommendations
    if r.empty or "0m" not in r.index:
        return None
    return r.loc["0m", [c for c in RATINGS if c in r]].astype(float)


def bullish_share(ratings: pd.Series | None) -> float | None:
    if ratings is None or not ratings.sum():
        return None
    return float((ratings.get("Strong buy", 0) + ratings.get("Buy", 0)) / ratings.sum())


def recent_target_changes(insights: Insights, days: int = 90) -> tuple[int, int]:
    """(raised, lowered) price targets in the last ``days``."""
    g = insights.grades
    if g.empty or "date" not in g:
        return 0, 0
    recent = g[g["date"] >= g["date"].max() - pd.Timedelta(days=days)]
    actions = recent["target_action"].fillna("").str.lower()
    return int((actions == "raises").sum()), int((actions == "lowers").sum())
