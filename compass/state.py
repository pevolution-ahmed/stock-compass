"""Per-session state shared by every module.

Data is fetched in background threads through Shiny ExtendedTasks, so one slow
Yahoo call never blocks other sessions, and each card fills in as soon as the
data it needs arrives. Modules read only from ``StockContext``; they never call
the provider directly.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

import pandas as pd
from shiny import reactive, req

from . import config
from .analytics import metrics as metric_set
from .analytics import scoring
from .data.provider import DataUnavailable, MarketDataProvider
from .data.schemas import Insights, Snapshot, Statements

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class Loaded(Generic[T]):
    value: T | None = None
    error: str | None = None


class Resource(Generic[T]):
    """A background fetch for the current symbol: ``value()`` waits silently, ``error()`` explains failures."""

    def __init__(self, fetch: Callable[..., T]):
        async def run(*args) -> Loaded[T]:
            try:
                return Loaded(await asyncio.to_thread(fetch, *args))
            except DataUnavailable as exc:
                return Loaded(error=str(exc))
            except Exception as exc:  # network hiccups etc. — keep the page alive
                log.exception("Fetch failed: %s%s", getattr(fetch, "__name__", fetch), args)
                return Loaded(error=f"Couldn't load data ({type(exc).__name__}). Try again shortly.")

        self.task = reactive.extended_task(run)

    def load(self, *args) -> None:
        self.task.cancel()
        self.task.invoke(*args)

    def loading(self) -> bool:
        return self.task.status() in ("initial", "running")

    def result(self) -> Loaded[T] | None:
        return None if self.loading() else self.task.result()

    def value(self) -> T:
        result = self.result()
        req(result is not None and result.value is not None)
        return result.value

    def value_or_none(self) -> T | None:
        result = self.result()
        return result.value if result is not None else None

    def error(self) -> str | None:
        result = self.result()
        return result.error if result is not None else None


@dataclass
class StockContext:
    provider: MarketDataProvider
    symbol: reactive.Value[str]
    snapshot: Resource[Snapshot]
    history: Resource[pd.DataFrame]
    statements: Resource[Statements]
    insights: Resource[Insights]
    benchmark: Resource[pd.DataFrame]
    risk_free: Resource[float]
    treasury: Resource[float]
    prices: Callable[[], pd.Series]
    benchmark_prices: Callable[[], pd.Series | None]
    metrics: Callable[[], dict[str, Any]]
    pillars: Callable[[], list[scoring.PillarScore]]

    def select(self, symbol: str) -> None:
        symbol = (symbol or "").strip().upper()
        if symbol:
            self.symbol.set(symbol)


def create_context(provider: MarketDataProvider, initial_symbol: str = config.DEFAULT_SYMBOL) -> StockContext:
    """Build the session's context; must be called inside a Shiny server function."""
    symbol = reactive.value(initial_symbol)
    snapshot = Resource(provider.snapshot)
    history = Resource(provider.history)
    statements = Resource(provider.statements)
    insights = Resource(provider.insights)
    benchmark = Resource(provider.history)
    risk_free = Resource(provider.risk_free_rate)
    treasury = Resource(provider.treasury_10y)

    @reactive.effect
    def _load_shared():
        benchmark.load(config.BENCHMARK_SYMBOL)
        risk_free.load()
        treasury.load()

    @reactive.effect
    @reactive.event(symbol)
    def _load_symbol():
        current = symbol()
        snapshot.load(current)
        history.load(current)
        statements.load(current)
        insights.load(current)

    @reactive.calc
    def prices() -> pd.Series:
        return history.value()["adjclose"]

    @reactive.calc
    def benchmark_prices() -> pd.Series | None:
        frame = benchmark.value_or_none()
        return None if frame is None else frame["adjclose"]

    @reactive.calc
    def metrics() -> dict[str, Any]:
        snap = snapshot.value()
        st = statements.value_or_none()
        result = metric_set.snapshot_metrics(snap, st)
        if history.value_or_none() is not None:
            result.update(metric_set.price_metrics(prices(), benchmark_prices()))
        if st is not None:
            result.update(metric_set.statement_metrics(snap, st))
            result.update(metric_set.valuation_metrics(snap, st, result, rate()))
        result.update(metric_set.insight_metrics(insights.value_or_none()))
        return result

    def rate() -> float:
        return risk_free.value_or_none() or config.RISK_FREE_FALLBACK

    @reactive.calc
    def pillars() -> list[scoring.PillarScore]:
        snap = snapshot.value()
        return scoring.score_pillars(metrics(), is_financial=snap.is_financial, is_fund=snap.is_fund)

    return StockContext(provider, symbol, snapshot, history, statements, insights, benchmark, risk_free, treasury,
                        prices, benchmark_prices, metrics, pillars)


class Watchlist:
    """The visitor's saved tickers, shared by the header's Watch button and the Watchlist tab."""

    MAX = 12

    def __init__(self, initial: list[str] = config.DEFAULT_WATCHLIST):
        self.symbols: reactive.Value[list[str]] = reactive.value(list(initial))

    def _current(self) -> list[str]:
        with reactive.isolate():
            return list(self.symbols())

    def replace(self, symbols: list[str]) -> None:
        cleaned = []
        for symbol in symbols:
            symbol = symbol.strip().upper()
            if symbol and symbol not in cleaned:
                cleaned.append(symbol)
        self.symbols.set(cleaned[: self.MAX])

    def add(self, symbol: str) -> None:
        current = self._current()
        symbol = (symbol or "").strip().upper()
        if symbol and symbol not in current and len(current) < self.MAX:
            self.symbols.set(current + [symbol])

    def remove(self, symbol: str) -> None:
        self.symbols.set([s for s in self._current() if s != (symbol or "").upper()])

    def toggle(self, symbol: str) -> None:
        (self.remove if (symbol or "").upper() in self._current() else self.add)(symbol)

    def contains(self, symbol: str) -> bool:
        return (symbol or "").upper() in self.symbols()
