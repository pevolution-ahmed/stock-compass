"""Record live Yahoo payloads into tests/fixtures for offline tests and development.

Usage: python scripts/record_fixtures.py MSFT JPM SPY ^IRX
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compass.data.clients import SNAPSHOT_MODULES, STATEMENT_KINDS, YahooClient  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
SEARCH_QUERIES = ["micro", "nvid"]


def record(symbol: str, client: YahooClient) -> None:
    out = FIXTURES / symbol.upper().replace("^", "_")
    out.mkdir(parents=True, exist_ok=True)

    modules = client.modules([symbol], SNAPSHOT_MODULES).get(symbol)
    (out / "modules.json").write_text(json.dumps(modules, indent=1, default=str))

    history = client.history([symbol], "max")
    if hasattr(history, "reset_index"):
        frame = history.reset_index().drop(columns="symbol")
        frame["date"] = [str(d)[:10] for d in frame["date"]]
        frame.to_csv(out / "history.csv", index=False)

    if symbol.startswith("^"):
        return
    statements = client.statements(symbol)
    for kind in STATEMENT_KINDS:
        frame = statements.get(kind)
        if hasattr(frame, "to_csv") and not frame.empty:
            frame.reset_index(drop=True).to_csv(out / f"{kind}.csv", index=False)
    print("recorded", symbol)


def main(symbols: list[str]) -> None:
    client = YahooClient()
    for symbol in symbols:
        record(symbol, client)
    (FIXTURES / "search").mkdir(parents=True, exist_ok=True)
    for query in SEARCH_QUERIES:
        (FIXTURES / "search" / f"{query}.json").write_text(
            json.dumps(client.search(query), indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:] or ["MSFT", "JPM", "SPY", "^IRX"])
