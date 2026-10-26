"""End-to-end smoke test: run the app on recorded fixtures and render every output.

Opens a real Shiny session over the websocket (no browser needed), marks every
output visible, then checks each one produced a value and none errored.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

websockets = pytest.importorskip("websockets")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT_ID = re.compile(r'id="([^"]+)"[^>]*class="[^"]*(?:shiny-html-output|shiny-ipywidget-output)')
OUTPUT_ID_ALT = re.compile(r'class="[^"]*(?:shiny-html-output|shiny-ipywidget-output)[^"]*"[^>]*id="([^"]+)"')


# What a browser sends for each input on connect (empty values would leave outputs blank)
INITIAL_INPUTS = {
    "tabs": "Overview",
    "search-query": "",
    "performance-amount": 10_000,
    "performance-start:shiny.date": "2021-10-26",
    "performance-reinvest": True,
    "performance-window": "5",
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = free_port()
    env = {**os.environ, "COMPASS_FIXTURES": str(FIXTURES)}
    # Log to a file: an unread pipe fills up and blocks the server
    log_path = tmp_path_factory.mktemp("server") / "server.log"
    log = log_path.open("wb")
    proc = subprocess.Popen([sys.executable, "-m", "shiny", "run", "app.py", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("server did not start:\n" + proc.stdout.read().decode(errors="replace"))
    yield port, urllib.request.urlopen(url).read().decode()
    proc.terminate()
    proc.wait(timeout=10)


async def render_all(port: int, output_ids: list[str], symbol: str | None,
                     timeout: float = 60, quiet: float = 4):
    """Open a session (optionally at ?symbol=...) and collect outputs until the server goes quiet."""
    inputs = {f".clientdata_output_{oid}_hidden": False for oid in output_ids}
    inputs.update(INITIAL_INPUTS)
    inputs[".clientdata_url_search"] = f"?symbol={symbol}" if symbol else ""
    values, errors = {}, {}
    async with websockets.connect(f"ws://127.0.0.1:{port}/websocket/", max_size=None) as ws:
        await ws.send(json.dumps({"method": "init", "data": inputs}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = json.loads(await asyncio.wait_for(ws.recv(), quiet))
            except asyncio.TimeoutError:
                break  # nothing new for `quiet` seconds: every output has settled
            except ValueError:
                continue
            values.update(message.get("values") or {})
            errors.update(message.get("errors") or {})
            for oid in message.get("values") or {}:
                errors.pop(oid, None)
    return values, errors


def page_outputs(html: str) -> list[str]:
    return sorted(set(OUTPUT_ID.findall(html)) | set(OUTPUT_ID_ALT.findall(html)))


def test_page_serves_assets(server):
    port, html = server
    for asset in ["css/tokens.css", "css/app.css", "js/app.js", "img/logo.svg"]:
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/{asset}").status == 200
    assert len(page_outputs(html)) >= 10


@pytest.mark.parametrize("symbol", [None, "JPM", "SPY", "ZZZZ"])
def test_every_output_renders(server, symbol):
    port, html = server
    outputs = page_outputs(html)
    values, errors = asyncio.run(render_all(port, outputs, symbol))
    assert not errors, f"outputs errored for {symbol}: {errors}"
    if symbol == "ZZZZ":
        assert "couldn" in json.dumps(values.get("hero-quote", "")), "invalid ticker should say it wasn't found"
        return
    missing = [oid for oid in outputs if values.get(oid) in (None, "", {})]
    assert not missing, f"outputs never rendered for {symbol or 'default'}: {missing}"
    expected = symbol or "MSFT"
    assert expected in json.dumps(values["hero-quote"]), f"hero should show {expected}"
