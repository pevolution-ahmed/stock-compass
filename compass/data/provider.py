"""Cached, normalized market data. Modules and analytics only ever see this API."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .. import config
from . import normalize
from .cache import cached
from .clients import INSIGHT_MODULES, SNAPSHOT_MODULES, FixtureClient, RawClient, YahooClient
from .normalize import DataUnavailable, SymbolNotFound
from .schemas import Insights, SearchResult, Snapshot, Statements

__all__ = ["MarketDataProvider", "DataUnavailable", "SymbolNotFound", "default_provider"]

log = logging.getLogger(__name__)


class MarketDataProvider:
    def __init__(self, client: RawClient | None = None):
        self.client = client or YahooClient()

    @cached("search")
    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        query = query.strip()
        if len(query) < 1:
            return []
        return normalize.search_results(self.client.search(query), limit)

    @cached("quote")
    def snapshot(self, symbol: str) -> Snapshot:
        symbol = symbol.upper()
        payload = self.client.modules([symbol], SNAPSHOT_MODULES).get(symbol)
        return normalize.snapshot(symbol, payload)

    @cached("quote")
    def snapshots(self, symbols: tuple[str, ...]) -> dict[str, Snapshot]:
        """Batch quotes for the watchlist; symbols Yahoo can't find are left out."""
        payload = self.client.modules(list(symbols), SNAPSHOT_MODULES)
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = normalize.snapshot(symbol, payload.get(symbol))
            except DataUnavailable:
                log.info("No snapshot for %s", symbol)
        return result

    @cached("history")
    def history(self, symbol: str, period: str = "max") -> pd.DataFrame:
        symbol = symbol.upper()
        return normalize.history(self.client.history([symbol], period), symbol)

    @cached("history")
    def histories(self, symbols: tuple[str, ...], period: str = "5y") -> dict[str, pd.DataFrame]:
        raw = self.client.history(list(symbols), period)
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = normalize.history(raw, symbol)
            except DataUnavailable:
                log.info("No history for %s", symbol)
        return result

    @cached("fundamentals")
    def statements(self, symbol: str) -> Statements:
        return normalize.statements(self.client.statements(symbol.upper()))

    @cached("insights")
    def insights(self, symbol: str) -> Insights:
        symbol = symbol.upper()
        return normalize.insights(self.client.modules([symbol], INSIGHT_MODULES).get(symbol))

    def risk_free_rate(self) -> float:
        """Annualized risk-free rate (13-week T-bill) as a fraction."""
        return self.index_rate(config.RISK_FREE_SYMBOL, config.RISK_FREE_FALLBACK)

    def treasury_10y(self) -> float:
        """10-year Treasury yield as a fraction, for comparing earnings yields."""
        return self.index_rate(config.TREASURY_10Y_SYMBOL, config.TREASURY_10Y_FALLBACK)

    @cached("rates")
    def index_rate(self, symbol: str, fallback: float) -> float:
        """Yield indices like ^IRX are quoted in percent; fall back when unavailable."""
        try:
            payload = self.client.modules([symbol], ["price"]).get(symbol)
            # A single-module request comes back flat rather than nested under "price"
            price = normalize.module(payload, "price") or (payload if isinstance(payload, dict) else {})
            rate = normalize.to_float(price.get("regularMarketPrice"))
        except Exception:  # network trouble must never block the page
            log.exception("Rate lookup failed for %s", symbol)
            rate = None
        return rate / 100 if rate else fallback


_default: MarketDataProvider | None = None


def default_provider() -> MarketDataProvider:
    """Live Yahoo provider, or recorded fixtures when COMPASS_FIXTURES points at a directory."""
    global _default
    if _default is None:
        import os

        fixtures = os.environ.get("COMPASS_FIXTURES")
        _default = MarketDataProvider(FixtureClient(Path(fixtures)) if fixtures else None)
    return _default
