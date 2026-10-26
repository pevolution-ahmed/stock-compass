"""Raw data clients. ``YahooClient`` is the only code that talks to the network.

``FixtureClient`` replays payloads recorded by ``scripts/record_fixtures.py`` so
tests and offline development use exactly what Yahoo returned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

SNAPSHOT_MODULES = [
    "price", "quoteType", "summaryDetail", "defaultKeyStatistics", "financialData",
    "assetProfile", "calendarEvents",
]
STATEMENT_KINDS = ["income", "balance", "cashflow", "valuation"]


class RawClient(Protocol):
    def modules(self, symbols: list[str], names: list[str]) -> dict[str, Any]: ...
    def history(self, symbols: list[str], period: str) -> Any: ...
    def statements(self, symbol: str) -> dict[str, Any]: ...
    def search(self, query: str) -> Any: ...


class YahooClient:
    def _ticker(self, symbols: list[str]):
        from yahooquery import Ticker

        return Ticker(symbols, asynchronous=len(symbols) > 1)

    def modules(self, symbols, names):
        return self._ticker(symbols).get_modules(names)

    def history(self, symbols, period):
        return self._ticker(symbols).history(period=period, interval="1d")

    def statements(self, symbol):
        ticker = self._ticker([symbol])
        return {
            "income": ticker.income_statement("a"),
            "balance": ticker.balance_sheet("a"),
            "cashflow": ticker.cash_flow("a"),
            "valuation": ticker.valuation_measures,
        }

    def search(self, query):
        from yahooquery import search

        return search(query, quotes_count=10, news_count=0)


class FixtureClient:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _dir(self, symbol: str) -> Path:
        return self.root / symbol.upper().replace("^", "_")

    def modules(self, symbols, names):
        result = {}
        for symbol in symbols:
            path = self._dir(symbol) / "modules.json"
            result[symbol] = (json.loads(path.read_text()) if path.exists()
                              else f"Quote not found for symbol: {symbol}")
        return result

    def history(self, symbols, period):
        frames = []
        for symbol in symbols:
            path = self._dir(symbol) / "history.csv"
            if path.exists():
                frames.append(pd.read_csv(path).assign(symbol=symbol))
        return pd.concat(frames).set_index(["symbol", "date"]) if frames else {}

    def statements(self, symbol):
        result = {}
        for kind in STATEMENT_KINDS:
            path = self._dir(symbol) / f"{kind}.csv"
            result[kind] = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return result

    def search(self, query):
        path = self.root / "search" / f"{query.lower()}.json"
        return json.loads(path.read_text()) if path.exists() else {"quotes": []}
