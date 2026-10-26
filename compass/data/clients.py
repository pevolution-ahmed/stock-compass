"""Raw data clients. ``YahooClient`` is the only code that talks to the network.

``FixtureClient`` replays payloads recorded by ``scripts/record_fixtures.py`` so
tests and offline development use exactly what Yahoo returned.
"""

from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

SNAPSHOT_MODULES = [
    "price", "quoteType", "summaryDetail", "defaultKeyStatistics", "financialData",
    "assetProfile", "calendarEvents",
]
INSIGHT_MODULES = [
    "earningsTrend", "earningsHistory", "recommendationTrend", "upgradeDowngradeHistory",
    "insiderTransactions", "majorHoldersBreakdown", "institutionOwnership", "netSharePurchaseActivity",
]
STATEMENT_KINDS = ["income", "balance", "cashflow", "valuation"]


class RawClient(Protocol):
    def modules(self, symbols: list[str], names: list[str]) -> dict[str, Any]: ...
    def history(self, symbols: list[str], period: str) -> Any: ...
    def statements(self, symbol: str) -> dict[str, Any]: ...
    def search(self, query: str) -> Any: ...


class YahooClient:
    """Talks to Yahoo through yahooquery without repeating its slow session setup.

    A fresh yahooquery Ticker visits Yahoo's homepage for a cookie before its first
    request (~1–1.5s). Instead, one set of cookies is fetched per ``SESSION_TTL``
    and cloned into a session per worker thread (HTTP sessions aren't guaranteed
    thread-safe); after any failure the cookies are refreshed in case they went stale.
    """

    SESSION_TTL = 30 * 60

    def __init__(self):
        self._local = threading.local()
        self._lock = threading.Lock()
        self._template = None  # (browser, cookies, created)

    def _cookies(self, fresh: bool):
        from curl_cffi import requests as curl
        from yahooquery.constants import BROWSERS
        from yahooquery.session_management import setup_session

        with self._lock:
            if fresh or self._template is None or time.monotonic() - self._template[2] > self.SESSION_TTL:
                browser = random.choice(list(BROWSERS))
                session = setup_session(curl.Session(headers=BROWSERS[browser], impersonate=browser))
                self._template = (browser, list(session.cookies.jar), time.monotonic())
            return self._template

    def _session(self, fresh: bool = False):
        from curl_cffi import requests as curl
        from yahooquery.constants import BROWSERS

        browser, cookies, created = self._cookies(fresh)
        if fresh or getattr(self._local, "created", None) != created:
            session = curl.Session(headers=BROWSERS[browser], impersonate=browser)
            for cookie in cookies:
                session.cookies.jar.set_cookie(cookie)
            self._local.session, self._local.created = session, created
        return self._local.session

    def _ticker(self, symbols: list[str], fresh: bool = False):
        from requests_futures.sessions import FuturesSession
        from yahooquery import Ticker

        session = self._session(fresh)
        if len(symbols) > 1:  # batch requests fan out over a small thread pool, as yahooquery does itself
            session = FuturesSession(max_workers=8, session=session)
        return Ticker(symbols, session=session, asynchronous=len(symbols) > 1)

    def _call(self, symbols: list[str], fetch):
        try:
            return fetch(self._ticker(symbols))
        except Exception:  # stale cookie or dropped connection: retry once on a new session
            return fetch(self._ticker(symbols, fresh=True))

    def modules(self, symbols, names):
        return self._call(symbols, lambda t: t.get_modules(names))

    def history(self, symbols, period):
        return self._call(symbols, lambda t: t.history(period=period, interval="1d"))

    def statements(self, symbol):
        return self._call([symbol], lambda t: {
            "income": t.income_statement("a"),
            "balance": t.balance_sheet("a"),
            "cashflow": t.cash_flow("a"),
            "valuation": t.valuation_measures,
        })

    def search(self, query):
        from yahooquery import search

        return search(query, quotes_count=10, news_count=0)


class FixtureClient:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _dir(self, symbol: str) -> Path:
        return self.root / symbol.upper().replace("^", "_")

    def modules(self, symbols, names):
        """Recorded modules (snapshot + insights files merged), filtered to the ones asked for."""
        result = {}
        for symbol in symbols:
            recorded = {}
            for filename in ("modules.json", "insights.json"):
                path = self._dir(symbol) / filename
                if path.exists() and isinstance(loaded := json.loads(path.read_text()), dict):
                    recorded.update(loaded)
            if not recorded:
                result[symbol] = f"Quote not found for symbol: {symbol}"
            elif len(names) == 1 and names[0] in recorded:
                result[symbol] = recorded[names[0]]  # Yahoo returns a single module unwrapped
            else:
                result[symbol] = {name: recorded[name] for name in names if name in recorded}
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
