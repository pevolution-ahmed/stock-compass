"""Transparent 0–100 pillar scores built from the flat metric set.

Each metric maps to 0–100 by a straight line between a ``bad`` and a ``good``
threshold (clipped at both ends), so the direction comes from which threshold is
larger. A pillar is the average of its available metrics; missing metrics are
left out rather than counted as zero. Thresholds are absolute rules of thumb,
not sector-relative.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .metrics import Metrics

MIN_METRICS = 2


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    bad: float
    good: float
    fmt: str = "pct"  # pct | x | ratio
    negative_is_worst: bool = False  # e.g. a negative P/E means losses, not a bargain
    financials: str = "include"  # include | exclude | only
    help: str = ""

    def applies(self, is_financial: bool) -> bool:
        if self.financials == "exclude":
            return not is_financial
        if self.financials == "only":
            return is_financial
        return True

    def score(self, value: float | None) -> float | None:
        if value is None:
            return None
        if self.negative_is_worst and value < 0:
            return 0.0
        position = (value - self.bad) / (self.good - self.bad)
        return round(min(max(position, 0.0), 1.0) * 100, 1)


@dataclass
class MetricScore:
    rule: Rule
    value: float | None
    score: float | None


@dataclass
class PillarScore:
    name: str
    question: str
    metrics: list[MetricScore] = field(default_factory=list)
    applicable: bool = True

    @property
    def available(self) -> list[MetricScore]:
        return [m for m in self.metrics if m.score is not None]

    @property
    def score(self) -> float | None:
        if not self.applicable or len(self.available) < min(MIN_METRICS, len(self.metrics)):
            return None
        return round(sum(m.score for m in self.available) / len(self.available))

    @property
    def coverage(self) -> str:
        return f"{len(self.available)} of {len(self.metrics)} metrics"


PILLARS: dict[str, tuple[str, list[Rule]]] = {
    "Value": ("Is the price reasonable for what you get?", [
        Rule("forward_pe", "Forward P/E", 35, 12, "x", negative_is_worst=True,
             help="Price ÷ next-12-month expected earnings."),
        Rule("ev_ebitda", "EV / EBITDA", 25, 8, "x", negative_is_worst=True, financials="exclude",
             help="Enterprise value ÷ EBITDA; capital-structure neutral."),
        Rule("fcf_yield", "Free cash flow yield", 0.01, 0.07, "pct", financials="exclude",
             help="Trailing free cash flow ÷ market cap."),
        Rule("peg", "PEG ratio", 3, 1, "ratio", negative_is_worst=True,
             help="P/E ÷ expected earnings growth."),
        Rule("price_to_book", "Price / book", 2.5, 1.0, "x", financials="only",
             help="Banks and insurers are usually valued on book value."),
    ]),
    "Quality": ("Is this a high-return, profitable business?", [
        Rule("roe", "Return on equity", 0.05, 0.25, help="Net income ÷ shareholders' equity."),
        Rule("gross_margin", "Gross margin", 0.20, 0.60, financials="exclude"),
        Rule("operating_margin", "Operating margin", 0.05, 0.30, financials="exclude"),
        Rule("net_margin", "Net margin", 0.03, 0.20),
        Rule("roa", "Return on assets", 0.005, 0.015, financials="only",
             help="For banks, ~1% ROA is considered solid."),
    ]),
    "Growth": ("Is the business getting bigger?", [
        Rule("revenue_growth", "Revenue growth (YoY)", 0.0, 0.20),
        Rule("earnings_growth", "Earnings growth (YoY)", 0.0, 0.25),
    ]),
    "Health": ("Can the balance sheet take a hit?", [
        Rule("debt_to_equity", "Debt / equity", 2.0, 0.3, "x", financials="exclude"),
        Rule("net_debt_ebitda", "Net debt / EBITDA", 4.0, 0.0, "x", financials="exclude",
             help="Years of EBITDA needed to repay net debt; negative means net cash."),
        Rule("current_ratio", "Current ratio", 0.8, 2.0, "x", financials="exclude",
             help="Current assets ÷ current liabilities."),
    ]),
    "Momentum": ("Is the market rewarding it lately?", [
        Rule("momentum_12_1", "12-1 month return", -0.20, 0.30,
             help="Return from 12 months ago to 1 month ago."),
        Rule("vs_sma200", "Price vs 200-day average", -0.10, 0.15),
        Rule("sma50_vs_sma200", "50-day vs 200-day average", -0.05, 0.05),
        Rule("relative_1y", "1Y return vs S&P 500", -0.20, 0.20),
    ]),
}

FUND_PILLARS = {"Momentum"}


def score_pillars(metrics: Metrics, *, is_financial: bool = False, is_fund: bool = False) -> list[PillarScore]:
    pillars = []
    for name, (question, rules) in PILLARS.items():
        applicable_rules = [rule for rule in rules if rule.applies(is_financial)]
        pillar = PillarScore(
            name=name,
            question=question,
            metrics=[MetricScore(rule, metrics.get(rule.key), rule.score(metrics.get(rule.key)))
                     for rule in applicable_rules],
            applicable=(not is_fund or name in FUND_PILLARS) and bool(applicable_rules),
        )
        pillars.append(pillar)
    return pillars
