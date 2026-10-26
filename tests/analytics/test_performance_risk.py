import numpy as np
import pandas as pd
import pytest

from compass.analytics import performance, risk, technicals
from compass.analytics.scoring import Rule, score_pillars


def daily_series(values, start="2020-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def compounding(total_growth, days, start="2020-01-01"):
    """Calendar-daily series growing smoothly by ``total_growth`` over ``days`` days."""
    index = pd.date_range(start, periods=days + 1, freq="D")
    return pd.Series((1 + total_growth) ** (np.arange(days + 1) / days), index=index)


def test_cagr_of_doubling_over_two_years():
    prices = compounding(1.0, int(2 * 365.25))
    assert performance.cagr(prices) == pytest.approx(2 ** 0.5 - 1, abs=1e-3)


def test_period_returns_skip_periods_longer_than_history():
    prices = compounding(0.10, 400)
    returns = performance.period_returns(prices)
    assert returns["1Y"] is not None
    assert returns["3Y"] is None and returns["10Y"] is None
    assert returns["Max"] == pytest.approx(0.10)


def test_ytd_measures_from_last_close_of_previous_year():
    index = pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02", "2024-03-01"])
    prices = pd.Series([90.0, 100.0, 101.0, 110.0], index=index)
    assert performance.period_returns(prices)["YTD"] == pytest.approx(0.10)


def test_max_drawdown_peak_trough_and_recovery():
    prices = daily_series([100, 120, 90, 60, 80, 125, 130])
    drawdown = risk.max_drawdown(prices)
    assert drawdown.depth == pytest.approx(-0.5)
    assert drawdown.peak == prices.index[1]
    assert drawdown.trough == prices.index[3]
    assert drawdown.recovery == prices.index[5]


def test_unrecovered_drawdown_has_no_recovery_date():
    drawdown = risk.max_drawdown(daily_series([100, 80, 70, 75]))
    assert drawdown.depth == pytest.approx(-0.3)
    assert drawdown.recovery is None and drawdown.days_to_recover is None


def test_beta_of_leveraged_copy_is_two():
    rng = np.random.default_rng(0)
    bench_returns = rng.normal(0.0004, 0.01, 1500)
    bench = daily_series(100 * np.cumprod(1 + bench_returns))
    stock = daily_series(100 * np.cumprod(1 + 2 * bench_returns))
    # Monthly compounding makes 2x daily slightly more than 2x monthly
    assert risk.beta(stock, bench) == pytest.approx(2.0, abs=0.1)


def test_sharpe_matches_definition():
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0.0005, 0.01, 1000))
    expected = (returns.mean() * 252 - 0.03) / (returns.std() * np.sqrt(252))
    assert risk.sharpe(returns, 0.03) == pytest.approx(expected)


def test_investment_growth_with_and_without_dividend_reinvestment():
    index = pd.bdate_range("2024-01-01", periods=3)
    history = pd.DataFrame({
        "close": [100.0, 100.0, 110.0],
        "adjclose": [95.0, 100.0, 110.0],  # one $5 dividend on day 2
        "dividends": [0.0, 5.0, 0.0],
    }, index=index)
    reinvested = performance.investment_growth(history, 1000, index[0], reinvest=True)
    cash = performance.investment_growth(history, 1000, index[0], reinvest=False)
    assert reinvested.final_value == pytest.approx(1000 * 110 / 95)
    assert cash.final_value == pytest.approx(10 * 110 + 10 * 5)
    assert cash.dividends == pytest.approx(50)


def test_calendar_and_monthly_returns_shapes():
    prices = compounding(0.5, 3 * 365)  # 2020-01-01 → 2022-12-31
    years = performance.calendar_year_returns(prices)
    assert list(years.index) == [2020, 2021, 2022]
    assert (1 + years).prod() == pytest.approx(1.5)
    assert performance.monthly_returns(prices).shape[1] == 12


def test_rsi_is_100_for_only_gains_and_bounded():
    assert technicals.rsi(daily_series(np.arange(1, 40))).iloc[-1] == pytest.approx(100)
    rng = np.random.default_rng(2)
    values = technicals.rsi(daily_series(100 + rng.normal(0, 1, 300).cumsum())).dropna()
    assert values.between(0, 100).all()


def test_rule_direction_and_negative_handling():
    lower_better = Rule("pe", "P/E", bad=35, good=12, negative_is_worst=True)
    assert lower_better.score(12) == 100 and lower_better.score(35) == 0
    assert lower_better.score(23.5) == pytest.approx(50)
    assert lower_better.score(-5) == 0
    assert lower_better.score(None) is None


def test_pillars_exclude_missing_metrics_and_respect_entity_type():
    pillars = {p.name: p for p in score_pillars({"roe": 0.25, "net_margin": 0.20})}
    assert pillars["Quality"].score == 100
    assert pillars["Quality"].coverage == "2 of 4 metrics"
    assert pillars["Value"].score is None

    funds = {p.name: p for p in score_pillars({}, is_fund=True)}
    assert not funds["Value"].applicable and funds["Momentum"].applicable

    banks = {p.name: p for p in score_pillars({}, is_financial=True)}
    assert "price_to_book" in [m.rule.key for m in banks["Value"].metrics]
    assert "ev_ebitda" not in [m.rule.key for m in banks["Value"].metrics]
