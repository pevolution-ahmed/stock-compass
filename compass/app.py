"""Assemble the page and wire every module to the shared StockContext.

Adding a section = one module in ``modules/`` plus one ``nav_panel`` and one
server call below.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs

from htmltools import HTML, tags
from shiny import App, reactive, ui

from . import config
from .data.provider import default_provider
from .modules.hero import hero_server, hero_ui
from .modules.loader import loader_server, loader_ui
from .modules.overview import overview_server, overview_ui
from .modules.analysts import analysts_server, analysts_ui
from .modules.fundamentals import fundamentals_server, fundamentals_ui
from .modules.performance import performance_server, performance_ui
from .modules.search import search_server, search_ui
from .modules.technicals import technicals_server, technicals_ui
from .modules.valuation import valuation_server, valuation_ui
from .modules.watchlist import watchlist_server, watchlist_ui
from .state import Watchlist, create_context
from .ui import charts  # noqa: F401 — registers the Plotly template
from .ui.palette import ROLES, css_variables, logo_svg

WWW = Path(__file__).parent / "www"
FONT_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"

head = ui.head_content(
    tags.link(rel="preconnect", href="https://fonts.googleapis.com"),
    tags.link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
    # Load the web font without blocking first paint (the loader must appear immediately)
    tags.link(rel="preload", as_="style", href=FONT_URL, onload="this.onload=null;this.rel='stylesheet'"),
    tags.noscript(tags.link(rel="stylesheet", href=FONT_URL)),
    # Bootstrap's own components (inputs, date picker) switch with data-bs-theme
    # Pick light/dark before first paint: saved choice, else the operating system's preference
    tags.script("""(() => {
      let mode = null;
      try { mode = localStorage.getItem('compass.theme'); } catch (e) {}
      if (mode !== 'light' && mode !== 'dark') {
        mode = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      document.documentElement.setAttribute('data-theme', mode);
      document.documentElement.setAttribute('data-bs-theme', mode);
    })();"""),
    tags.style(css_variables()),
    tags.link(rel="stylesheet", href="css/tokens.css"),
    tags.link(rel="stylesheet", href="css/app.css"),
    tags.link(rel="icon", type="image/svg+xml",
              href="data:image/svg+xml;base64," + base64.b64encode(logo_svg(static=True).encode()).decode()),
    tags.meta(name="description", content=config.APP_TAGLINE),
    tags.script(src="js/app.js", defer=""),
)

brand = tags.span(
    tags.span(HTML(logo_svg()), class_="brand-mark"),
    tags.span(config.APP_NAME, class_="brand-name"),
    class_="brand",
)

theme_toggle = tags.button(
    tags.span("☾", class_="when-light", aria_hidden="true"), tags.span("☀", class_="when-dark", aria_hidden="true"),
    type="button", id="theme-toggle", class_="theme-toggle", title="Switch light / dark", aria_label="Switch light or dark theme",
)

footer = tags.footer(
    tags.div(tags.span(config.DISCLAIMER), tags.span(f"Benchmark: {config.BENCHMARK_LABEL} ({config.BENCHMARK_SYMBOL})"),
             class_="page"),
    class_="site-footer",
)

app_ui = ui.page_navbar(
    ui.nav_panel("Overview", overview_ui("overview")),
    ui.nav_panel("Performance & Risk", performance_ui("performance")),
    ui.nav_panel("Valuation", valuation_ui("valuation")),
    ui.nav_panel("Fundamentals", fundamentals_ui("fundamentals")),
    ui.nav_panel("Analysts", analysts_ui("analysts")),
    ui.nav_panel("Technicals", technicals_ui("technicals")),
    ui.nav_panel("Watchlist", watchlist_ui("watchlist")),
    title=brand,
    id="tabs",
    window_title=config.APP_NAME,
    lang="en",
    header=tags.div(head, ui.busy_indicators.options(spinner_color=ROLES["ink"], pulse_background=ROLES["accent"],
                                                       pulse_height="3px", fade_opacity=0.5),
                    loader_ui("loader"), theme_toggle, hero_ui("hero", search_ui("search"))),
    footer=footer,
    navbar_options=ui.navbar_options(bg=ROLES["paper"], theme="light", underline=False),
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

    watch = Watchlist()

    def open_symbol(symbol: str) -> None:
        ctx.select(symbol)
        ui.update_navs("tabs", selected="Overview", session=session)

    search_server("search", provider=provider, on_pick=ctx.select)
    loader_server("loader", ctx=ctx)
    hero_server("hero", ctx=ctx, watch=watch)
    overview_server("overview", ctx=ctx)
    performance_server("performance", ctx=ctx)
    valuation_server("valuation", ctx=ctx)
    fundamentals_server("fundamentals", ctx=ctx)
    analysts_server("analysts", ctx=ctx)
    technicals_server("technicals", ctx=ctx)
    watchlist_server("watchlist", provider=provider, watch=watch, ctx=ctx, on_open=open_symbol)

    @reactive.effect
    async def _sync_url():
        await session.send_custom_message("compass-url", {"symbol": ctx.symbol()})


def start_warmup() -> None:
    """Prefetch the default stock and the benchmark so the first visitor doesn't wait on Yahoo."""
    threading.Thread(target=default_provider().warm, args=([config.DEFAULT_SYMBOL, config.BENCHMARK_SYMBOL],),
                     daemon=True, name="compass-warmup").start()


class CompassApp(App):
    """Shiny App that starts the cache warm-up when the server starts, not when the module is imported."""

    @asynccontextmanager
    async def _lifespan(self, starlette_app):
        start_warmup()
        async with super()._lifespan(starlette_app):
            yield


if hasattr(App, "_lifespan"):
    app = CompassApp(app_ui, server, static_assets=WWW)
else:  # Shiny changed its internals; fall back to warming at import time
    app = App(app_ui, server, static_assets=WWW)
    start_warmup()
