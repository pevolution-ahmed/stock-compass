"""Business quality, financial health, growth and shareholder returns from annual statements.

Pure pandas. Statement frames are indexed by fiscal year-end date (oldest
first) with Yahoo's field names as columns; any field may be missing, so every
function returns None (or an empty result) rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.schemas import Statements

DEFAULT_TAX_RATE = 0.21


def col(frame: pd.DataFrame, name: str) -> pd.Series:
    """A statement line as floats indexed by fiscal year-end (empty if Yahoo didn't report it)."""
    if frame is None or frame.empty or name not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").dropna()


def latest(frame: pd.DataFrame, name: str, back: int = 0) -> float | None:
    series = col(frame, name)
    return float(series.iloc[-1 - back]) if len(series) > back else None


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0 or not np.isfinite(a) or not np.isfinite(b):
        return None
    return a / b


def ttm_or_latest(ttm: pd.Series | None, frame: pd.DataFrame, name: str) -> float | None:
    if ttm is not None and name in ttm and pd.notna(ttm[name]):
        return float(ttm[name])
    return latest(frame, name)


# ---------- Trends ----------

def fiscal_label(index: pd.Index) -> list[str]:
    return [f"FY{d.year}" for d in index]


def income_and_cash(st: Statements) -> pd.DataFrame:
    """Revenue, net income and free cash flow per fiscal year."""
    frame = pd.DataFrame({
        "Revenue": col(st.income, "TotalRevenue"),
        "Net income": col(st.income, "NetIncome"),
        "Free cash flow": col(st.cashflow, "FreeCashFlow"),
    })
    return frame.dropna(how="all")


def margins(st: Statements) -> pd.DataFrame:
    revenue = col(st.income, "TotalRevenue")
    frame = pd.DataFrame({
        "Gross": col(st.income, "GrossProfit") / revenue,
        "Operating": col(st.income, "OperatingIncome") / revenue,
        "Net": col(st.income, "NetIncome") / revenue,
        "Free cash flow": col(st.cashflow, "FreeCashFlow") / revenue,
    })
    return frame.dropna(how="all").dropna(axis=1, how="all")


def cagr(series: pd.Series, years: int = 3) -> float | None:
    """Annual growth over the last ``years`` fiscal years (needs a positive start and end)."""
    series = series.dropna()
    if len(series) < 2:
        return None
    span = min(years, len(series) - 1)
    start, end = float(series.iloc[-1 - span]), float(series.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / span) - 1


# ---------- Returns on capital ----------

def tax_rate(st: Statements) -> float:
    rate = div(latest(st.income, "TaxProvision"), latest(st.income, "PretaxIncome"))
    return DEFAULT_TAX_RATE if rate is None or not 0 <= rate <= 0.5 else rate


def invested_capital(st: Statements, back: int = 0) -> float | None:
    reported = latest(st.balance, "InvestedCapital", back)
    if reported:
        return reported
    debt, equity = latest(st.balance, "TotalDebt", back), latest(st.balance, "StockholdersEquity", back)
    cash = latest(st.balance, "CashAndCashEquivalents", back) or 0
    return None if debt is None or equity is None else debt + equity - cash


def average(current: float | None, prior: float | None) -> float | None:
    if current is None:
        return None
    return current if prior is None else (current + prior) / 2


def roic(st: Statements) -> float | None:
    """After-tax operating profit ÷ average invested capital (debt + equity)."""
    ebit = latest(st.income, "EBIT") or latest(st.income, "OperatingIncome")
    capital = average(invested_capital(st), invested_capital(st, 1))
    if ebit is None or not capital or capital <= 0:
        return None
    return ebit * (1 - tax_rate(st)) / capital


def roic_history(st: Statements) -> pd.Series:
    ebit = col(st.income, "EBIT")
    if ebit.empty:
        ebit = col(st.income, "OperatingIncome")
    capital = col(st.balance, "InvestedCapital")
    if capital.empty:
        capital = col(st.balance, "TotalDebt") + col(st.balance, "StockholdersEquity") - col(st.balance, "CashAndCashEquivalents")
    capital = capital.rolling(2, min_periods=1).mean()
    result = (ebit * (1 - tax_rate(st)) / capital.reindex(ebit.index)).dropna()
    return result[np.isfinite(result)]


# ---------- Health ----------

def interest_coverage(st: Statements) -> float | None:
    ebit = latest(st.income, "EBIT") or latest(st.income, "OperatingIncome")
    interest = latest(st.income, "InterestExpense")
    if ebit is None:
        return None
    if not interest:
        return None if interest is None else 99.0  # no interest to pay
    return ebit / abs(interest)


# ---------- Piotroski F-score ----------

@dataclass
class Check:
    name: str
    passed: bool | None
    detail: str


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _x(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def piotroski(st: Statements) -> list[Check]:
    """Piotroski's nine pass/fail tests comparing the latest fiscal year with the one before."""
    inc, bal, cf = st.income, st.balance, st.cashflow

    def ratio(numerator: str, denominator: str, back: int = 0, frame_n=inc, frame_d=bal):
        return div(latest(frame_n, numerator, back), latest(frame_d, denominator, back))

    roa, roa_prev = ratio("NetIncome", "TotalAssets"), ratio("NetIncome", "TotalAssets", 1)
    cfo = latest(cf, "OperatingCashFlow")
    cfo_assets = div(cfo, latest(bal, "TotalAssets"))
    leverage, leverage_prev = (div(latest(bal, "LongTermDebt"), latest(bal, "TotalAssets")),
                               div(latest(bal, "LongTermDebt", 1), latest(bal, "TotalAssets", 1)))
    current, current_prev = (div(latest(bal, "CurrentAssets"), latest(bal, "CurrentLiabilities")),
                             div(latest(bal, "CurrentAssets", 1), latest(bal, "CurrentLiabilities", 1)))
    shares, shares_prev = latest(bal, "OrdinarySharesNumber"), latest(bal, "OrdinarySharesNumber", 1)
    if shares is None:
        shares, shares_prev = latest(inc, "DilutedAverageShares"), latest(inc, "DilutedAverageShares", 1)
    gross, gross_prev = (div(latest(inc, "GrossProfit"), latest(inc, "TotalRevenue")),
                         div(latest(inc, "GrossProfit", 1), latest(inc, "TotalRevenue", 1)))
    turnover, turnover_prev = ratio("TotalRevenue", "TotalAssets"), ratio("TotalRevenue", "TotalAssets", 1)

    def compare(a, b, better="higher"):
        if a is None or b is None:
            return None
        return a > b if better == "higher" else a < b

    return [
        Check("Profitable", None if roa is None else roa > 0, f"Return on assets {_pct(roa)}"),
        Check("Positive operating cash flow", None if cfo is None else cfo > 0,
              "Operating cash flow " + ("—" if cfo is None else f"${cfo / 1e9:,.1f}B")),
        Check("Return on assets improved", compare(roa, roa_prev), f"{_pct(roa_prev)} → {_pct(roa)}"),
        Check("Cash earnings exceed accounting earnings", compare(cfo_assets, roa),
              f"Cash flow / assets {_pct(cfo_assets)} vs ROA {_pct(roa)}"),
        Check("Less long-term debt", compare(leverage, leverage_prev, "lower"),
              f"Debt / assets {_pct(leverage_prev)} → {_pct(leverage)}"),
        Check("Better liquidity", compare(current, current_prev), f"Current ratio {_x(current_prev)} → {_x(current)}"),
        Check("No new shares issued", None if shares is None or shares_prev is None else shares <= shares_prev * 1.005,
              "Shares " + ("—" if shares is None or shares_prev is None
                           else f"{shares_prev / 1e9:,.2f}B → {shares / 1e9:,.2f}B")),
        Check("Gross margin improved", compare(gross, gross_prev), f"{_pct(gross_prev)} → {_pct(gross)}"),
        Check("Asset turnover improved", compare(turnover, turnover_prev),
              f"Revenue / assets {_x(turnover_prev)} → {_x(turnover)}"),
    ]


def piotroski_score(checks: list[Check]) -> tuple[int, int] | None:
    """(passed, available); None when too few tests can be evaluated to be meaningful."""
    available = [c for c in checks if c.passed is not None]
    if len(available) < 6:
        return None
    return sum(c.passed for c in available), len(available)


# ---------- Altman Z-score ----------

@dataclass
class AltmanZ:
    score: float
    zone: str  # distress | grey | safe
    parts: dict[str, float]


def altman_z(st: Statements, market_cap: float | None) -> AltmanZ | None:
    """Original public-manufacturer model: < 1.81 distress, 1.81–2.99 grey, > 2.99 safe."""
    bal, inc = st.balance, st.income
    assets = latest(bal, "TotalAssets")
    liabilities = latest(bal, "TotalLiabilitiesNetMinorityInterest")
    working_capital = latest(bal, "WorkingCapital")
    if working_capital is None and latest(bal, "CurrentAssets") is not None:
        working_capital = latest(bal, "CurrentAssets") - (latest(bal, "CurrentLiabilities") or 0)
    inputs = {
        "Working capital / assets": div(working_capital, assets),
        "Retained earnings / assets": div(latest(bal, "RetainedEarnings"), assets),
        "EBIT / assets": div(latest(inc, "EBIT") or latest(inc, "OperatingIncome"), assets),
        "Market value / liabilities": div(market_cap, liabilities),
        "Sales / assets": div(latest(inc, "TotalRevenue"), assets),
    }
    if any(v is None for v in inputs.values()):
        return None
    weights = [1.2, 1.4, 3.3, 0.6, 1.0]
    parts = {name: weight * value for (name, value), weight in zip(inputs.items(), weights)}
    score = sum(parts.values())
    zone = "distress" if score < 1.81 else "grey" if score <= 2.99 else "safe"
    return AltmanZ(score, zone, parts)


# ---------- Shareholder returns ----------

def annual_dividends(history: pd.DataFrame, years: int = 10) -> pd.Series:
    """Dividends per share by calendar year (complete years only)."""
    dividends = history["dividends"]
    by_year = dividends[dividends > 0].groupby(dividends[dividends > 0].index.year).sum()
    current = history.index[-1].year
    return by_year[(by_year.index < current) & (by_year.index >= current - years)]


def dividend_cagr(history: pd.DataFrame, years: int = 5) -> float | None:
    by_year = annual_dividends(history, years + 1)
    return cagr(by_year, years) if len(by_year) > years else None


def shareholder_payouts(st: Statements) -> pd.DataFrame:
    """Cash returned per fiscal year: dividends and net buybacks (positive = returned)."""
    dividends = -col(st.cashflow, "CashDividendsPaid")
    buybacks = -col(st.cashflow, "RepurchaseOfCapitalStock")
    issuance = col(st.cashflow, "CommonStockIssuance")
    net_buybacks = buybacks.sub(issuance, fill_value=0) if not buybacks.empty else buybacks
    return pd.DataFrame({"Dividends": dividends, "Net buybacks": net_buybacks}).dropna(how="all").fillna(0)


def buyback_yield(st: Statements, market_cap: float | None) -> float | None:
    """Net buybacks over the last twelve months ÷ market cap."""
    repurchased = ttm_or_latest(st.cashflow_ttm, st.cashflow, "RepurchaseOfCapitalStock")
    if repurchased is None:
        return None
    issued = ttm_or_latest(st.cashflow_ttm, st.cashflow, "CommonStockIssuance") or 0
    return div(-repurchased - issued, market_cap)
