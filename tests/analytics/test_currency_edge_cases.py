import numpy as np
import pandas as pd
import pytest

from compass.analytics import dcf, metrics, risk
from compass.data import normalize
from compass.data.schemas import Snapshot, Statements, major_currency


def payload(currency="USD", financial="USD", quote_type="EQUITY"):
    return {
        "price": {"regularMarketPrice": 100.0, "currency": currency, "marketCap": 1e9, "quoteType": quote_type},
        "financialData": {"financialCurrency": financial},
    }


def test_minor_unit_quotes_and_statement_currency():
    assert major_currency("GBp") == ("GBP", 0.01)
    assert major_currency("EUR") == ("EUR", 1.0)
    shell = normalize.snapshot("SHEL.L", payload(currency="GBp", financial="USD"))
    assert shell.price_unit == 0.01 and shell.currency_symbol == ""
    assert shell.major_symbol == "£" and shell.statement_symbol == "$"
    tsm = normalize.snapshot("TSM", payload(financial="TWD"))
    assert tsm.statement_symbol == "NT$" and tsm.major_symbol == "$"


def test_non_company_kinds():
    crypto = normalize.snapshot("BTC-USD", payload(quote_type="CRYPTOCURRENCY"))
    assert crypto.is_fund and crypto.kind_phrase == "a cryptocurrency" and crypto.kind_label == "Crypto"
    assert not normalize.snapshot("MSFT", payload()).is_fund


def test_dcf_unit_converts_statement_currency_to_quoted_price_unit():
    base = dcf.Assumptions(fcf=100.0, shares=10.0, net_cash=0.0, growth=0.03, discount=0.08, terminal_growth=0.03)
    # Statements in USD, price in pence at 0.75 GBP/USD: value per share ×0.75 then ×100
    converted = dcf.value(dcf.Assumptions(**{**base.__dict__, "unit": 0.75 / 0.01}))
    assert converted.per_share == pytest.approx(dcf.value(base).per_share * 75)


def test_cross_currency_metrics_convert_or_skip():
    index = pd.to_datetime(["2024-12-31", "2025-12-31"])
    statements = Statements(pd.DataFrame(index=index), pd.DataFrame(index=index),
                            pd.DataFrame({"FreeCashFlow": [50.0, 100.0]}, index=index))
    snap = Snapshot("TSM", "TSMC", market_cap=1000.0, price=10.0, financial_currency="TWD", fx=0.03)
    m = metrics.snapshot_metrics(snap, statements)
    assert m["fcf_yield"] == pytest.approx(100 * 0.03 / 1000)
    snap.fx = None  # rate unavailable → don't mix currencies
    assert metrics.snapshot_metrics(snap, statements)["fcf_yield"] is None
    assert metrics.dcf_inputs(snap, statements, {"fcf": 100.0}, 0.04) is None


def test_annualization_follows_trading_calendar():
    business = pd.Series(np.linspace(100, 110, 600), index=pd.bdate_range("2023-01-02", periods=600))
    every_day = pd.Series(np.linspace(100, 110, 800), index=pd.date_range("2023-01-01", periods=800))
    assert 245 <= risk.periods_per_year(business) <= 262
    assert risk.periods_per_year(every_day) in (365, 366)
