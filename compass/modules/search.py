"""Ticker search with Yahoo autocomplete and popular quick picks."""

from __future__ import annotations

from typing import Callable

from htmltools import tags
from shiny import module, reactive, render, ui

from .. import config
from ..data.provider import MarketDataProvider
from ..ui import components as c


@module.ui
def search_ui(placeholder: str = "Search a company or ticker"):
    return tags.div(
        ui.input_text("query", None, placeholder=placeholder, autocomplete="off", width="100%"),
        tags.div(ui.output_ui("results"), class_="c-search-panel", role="listbox"),
        class_="c-search",
        data_pick_input=module.resolve_id("pick"),
    )


@module.server
def search_server(input, output, session, provider: MarketDataProvider, on_pick: Callable[[str], None]):
    @reactive.calc
    def hits():
        query = input.query().strip()
        if not query:
            return None
        try:
            return provider.search(query)
        except Exception:
            return []

    @render.ui
    def results():
        found = hits()
        if found is None:
            return tags.div(
                tags.div("Popular", class_="c-search-label micro muted"),
                tags.div(*[c.pick_pill(symbol) for symbol in config.QUICK_PICKS], class_="quick-picks"),
            )
        if not found:
            typed = input.query().strip().upper()
            return tags.div(f"No matches. Press Enter to open “{typed}” as a ticker.",
                            class_="c-search-label micro muted")
        return [
            tags.button(
                tags.span(hit.symbol, class_="sym"),
                tags.span(hit.name, class_="name"),
                c.pill(hit.exchange or hit.quote_type, variant="fog"),
                type="button", class_="c-search-hit", data_symbol=hit.symbol, role="option",
            )
            for hit in found
        ]

    @reactive.effect
    @reactive.event(input.pick)
    def _pick():
        on_pick(input.pick())
