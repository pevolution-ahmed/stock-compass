"""Assemble the page and wire every module to the shared StockContext.

Adding a section = one module in ``modules/`` plus one ``nav_panel`` and one
server call below.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs

from htmltools import tags
from shiny import App, reactive, ui

from . import config
from .data.provider import default_provider
from .modules.hero import hero_server, hero_ui
from .modules.overview import overview_server, overview_ui
from .modules.performance import performance_server, performance_ui
from .modules.search import search_server, search_ui
from .state import create_context
from .ui import charts  # noqa: F401 — registers the Plotly template

WWW = Path(__file__).parent / "www"

head = ui.head_content(
    tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
    tags.link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
    tags.link(rel="stylesheet",
              href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"),
    tags.link(rel="stylesheet", href="css/tokens.css"),
    tags.link(rel="stylesheet", href="css/app.css"),
    tags.link(rel="icon", type="image/svg+xml", href="img/logo.svg"),
    tags.meta(name="description", content=config.APP_TAGLINE),
    tags.script(src="js/app.js", defer=""),
)

brand = tags.span(
    tags.img(src="img/logo.svg", class_="brand-mark", alt=""),
    tags.span(config.APP_NAME, class_="brand-name"),
)

footer = tags.footer(
    tags.div(tags.span(config.DISCLAIMER), tags.span(f"Benchmark: {config.BENCHMARK_LABEL} ({config.BENCHMARK_SYMBOL})"),
             class_="page"),
    class_="site-footer",
)

app_ui = ui.page_navbar(
    ui.nav_panel("Overview", overview_ui("overview")),
    ui.nav_panel("Performance & Risk", performance_ui("performance")),
    title=brand,
    id="tabs",
    window_title=config.APP_NAME,
    lang="en",
    header=tags.div(head, ui.busy_indicators.options(spinner_color="#163300", pulse_background="#9fe870",
                                                       pulse_height="3px", fade_opacity=0.5),
                    hero_ui("hero", search_ui("search"))),
    footer=footer,
    navbar_options=ui.navbar_options(bg="#ffffff", theme="light", underline=False),
)


SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.^=\-]{1,15}$")


def symbol_from_query(search: str) -> str:
    """``?symbol=JPM`` opens that ticker, so any view can be shared as a link."""
    symbol = parse_qs((search or "").lstrip("?")).get("symbol", [""])[0].strip()
    return symbol.upper() if SYMBOL_PATTERN.match(symbol) else config.DEFAULT_SYMBOL


def server(input, output, session):
    provider = default_provider()
    with reactive.isolate():
        initial = symbol_from_query(input[".clientdata_url_search"]())
    ctx = create_context(provider, initial)

    search_server("search", provider=provider, on_pick=ctx.select)
    hero_server("hero", ctx=ctx)
    overview_server("overview", ctx=ctx)
    performance_server("performance", ctx=ctx)

    @reactive.effect
    async def _sync_url():
        await session.send_custom_message("compass-url", {"symbol": ctx.symbol()})


app = App(app_ui, server, static_assets=WWW)
