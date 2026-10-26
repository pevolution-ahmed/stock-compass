from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from compass.analytics import dcf, fundamentals as fa, metrics, valuation
from compass.data.clients import FixtureClient
from compass.data.provider import MarketDataProvider
from compass.data.schemas import Statements

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def frame(**columns):
    index = pd.to_datetime(["2023-12-31", "2024-12-31"])
    return pd.DataFrame(columns, index=index)


def improving_company() -> Statements:
    """Two fiscal years where every Piotroski test improves."""
    income = frame(TotalRevenue=[100.0, 130.0], GrossProfit=[40.0, 56.0], NetIncome=[8.0, 12.0],
                   EBIT=[12.0, 18.0], InterestExpense=[2.0, 2.0], DilutedEPS=[1.0, 1.5])
    balance = frame(TotalAssets=[100.0, 104.0], CurrentAssets=[40.0, 50.0], CurrentLiabilities=[30.0, 30.0],
                    LongTermDebt=[30.0, 25.0], OrdinarySharesNumber=[10.0, 10.0], StockholdersEquity=[50.0, 60.0],
                    RetainedEarnings=[20.0, 30.0], TotalLiabilitiesNetMinorityInterest=[50.0, 44.0],
                    WorkingCapital=[10.0, 20.0])
    cashflow = frame(OperatingCashFlow=[10.0, 16.0], FreeCashFlow=[6.0, 10.0])
    return Statements(income, balance, cashflow)


def test_piotroski_all_pass_and_missing_fields():
    checks = fa.piotroski(improving_company())
    assert [c.passed for c in checks] == [True] * 9
    assert fa.piotroski_score(checks) == (9, 9)

    sparse = Statements(frame(NetIncome=[1.0, 2.0]), frame(TotalAssets=[10.0, 10.0]), pd.DataFrame())
    assert fa.piotroski_score(fa.piotroski(sparse)) is None  # too few tests to be meaningful


def test_altman_z_matches_formula():
    z = fa.altman_z(improving_company(), market_cap=88.0)
    expected = 1.2 * 20 / 104 + 1.4 * 30 / 104 + 3.3 * 18 / 104 + 0.6 * 88 / 44 + 1.0 * 130 / 104
    assert z.score == pytest.approx(expected)
    assert z.score == pytest.approx(3.65, abs=0.01) and z.zone == "safe"


def test_cagr_and_margins():
    assert fa.cagr(pd.Series([100.0, 110.0, 121.0, 133.1])) == pytest.approx(0.10)
    assert fa.cagr(pd.Series([-5.0, 10.0])) is None
    m = fa.margins(improving_company())
    assert m["Gross"].iloc[-1] == pytest.approx(56 / 130)


def test_dcf_with_constant_growth_equals_gordon_model():
    a = dcf.Assumptions(fcf=100.0, shares=10.0, net_cash=0.0, growth=0.03, discount=0.08, terminal_growth=0.03)
    result = dcf.value(a)
    assert result.enterprise_value == pytest.approx(100 * 1.03 / (0.08 - 0.03))
    assert result.per_share == pytest.approx(result.enterprise_value / 10)


def test_reverse_dcf_round_trips():
    a = dcf.Assumptions(fcf=50.0, shares=5.0, net_cash=20.0, growth=0.12)
    price = dcf.value(a).per_share
    assert dcf.implied_growth(replace(a, growth=0.0), price) == pytest.approx(0.12, abs=1e-6)


def test_dcf_rejects_impossible_inputs_and_sensitivity_is_monotonic():
    base = dcf.Assumptions(fcf=100.0, shares=10.0, net_cash=0.0)
    assert dcf.value(replace(base, fcf=-1)) is None
    assert dcf.value(replace(base, discount=0.02, terminal_growth=0.03)) is None
    grid = dcf.sensitivity(base, [0.08, 0.10, 0.12], [0.02, 0.03])
    assert grid[0][0] > grid[1][0] > grid[2][0]  # higher discount → lower value
    assert grid[0][1] > grid[0][0]                # higher terminal growth → higher value


def test_capm_discount_is_bounded():
    assert dcf.capm_discount(0.04, 1.0) == pytest.approx(0.085)
    assert dcf.capm_discount(0.04, 5.0) == pytest.approx(0.13)  # beta capped at 2.0
    assert dcf.capm_discount(0.08, 2.0) == 0.14  # rate capped at 14%
    assert dcf.capm_discount(0.0, 0.1) == 0.07


def test_multiple_premium_vs_history():
    history = pd.DataFrame({"PeRatio": [20.0, 22.0, 24.0, 26.0, 28.0]},
                           index=pd.date_range("2022-01-01", periods=5, freq="QE"))
    ctx = valuation.context(history, {"trailing_pe": 30.0})["trailing_pe"]
    assert ctx.median == 24.0 and ctx.premium == pytest.approx(0.25)


def test_fixture_metrics_cover_regular_company_and_bank():
    provider = MarketDataProvider(FixtureClient(FIXTURES))
    msft, jpm = provider.snapshot("MSFT"), provider.snapshot("JPM")
    m = metrics.statement_metrics(msft, provider.statements("MSFT"))
    assert all(m[k] is not None for k in ["roic", "piotroski", "altman_z", "revenue_cagr_3y", "interest_coverage"])
    banks = metrics.statement_metrics(jpm, provider.statements("JPM"))
    assert banks["altman_z"] is None  # not meaningful for banks
    snapshot_m = metrics.snapshot_metrics(jpm, provider.statements("JPM"))
    assert metrics.dcf_inputs(jpm, provider.statements("JPM"), snapshot_m, 0.04) is None
