"""Watchlist tab: compare saved tickers side by side and open any of them in the deep dive.

The list lives in the browser (localStorage) via a small JS bridge in www/js/app.js,
so it survives reloads without a server database.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd
from htmltools import tags
from shiny import module, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

from .. import config
from ..analytics import metrics as metric_set
from ..analytics import performance, scoring
from ..data.provider import MarketDataProvider
from ..state import Resource, StockContext, Watchlist
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt
from .search import search_server, search_ui

PERIODS = {"3": "3M", "6": "6M", "12": "1Y", "24": "2Y"}
PILLAR_LETTERS = {"Value": "V", "Quality": "Q", "Growth": "G", "Health": "H", "Momentum": "M"}


@module.ui
def watchlist_ui():
    return tags.div(
        c.section(
            "Watchlist", ui.output_ui("table"),
            subtitle="Saved in this browser. Click a name to open its full analysis.",
            actions=tags.div(search_ui("add", placeholder="Add a ticker to compare"), class_="watch-add"),
        ),
        c.section(
            "Side by side", c.card(output_widget("compare", height="380px")),
            subtitle=f"Total return rebased to 0% at the start of the period, with the {config.BENCHMARK_LABEL} for reference.",
            actions=tags.div(ui.input_radio_buttons("period", None, PERIODS, selected="12", inline=True),
                             class_="segmented"),
        ),
        class_="page",
    )


def score_badges(pillars: list[scoring.PillarScore]):
    badges = []
    for pillar in pillars:
        score = pillar.score
        tone = "na" if score is None else "up" if score >= 67 else "down" if score <= 33 else "flat"
        badges.append(tags.span(
            tags.span(PILLAR_LETTERS[pillar.name], class_="letter"), "–" if score is None else f"{score:.0f}",
            class_=f"mini-score {tone}", title=f"{pillar.name}: {'n/a' if score is None else f'{score:.0f}/100'}",
        ))
    return tags.div(*badges, class_="mini-scores")


@module.server
def watchlist_server(input, output, session, provider: MarketDataProvider, watch: Watchlist,
                     ctx: StockContext, on_open: Callable[[str], None]):
    restored = reactive.value(False)
    quotes = Resource(provider.snapshots)
    histories = Resource(provider.histories)
    # Last loaded data per symbol, shown while a changed list refetches so the table never blanks
    known_quotes = reactive.value({})
    known_prices = reactive.value({})

    @reactive.effect
    def _remember():
        for resource, store in ((quotes, known_quotes), (histories, known_prices)):
            fresh = resource.value_or_none()
            if fresh:
                with reactive.isolate():
                    store.set({**store(), **fresh})

    search_server("add", provider=provider, on_pick=watch.add)

    @reactive.effect
    @reactive.event(input.saved, ignore_none=False)
    def _restore():
        saved = input.saved()
        if isinstance(saved, (list, tuple)) and saved:
            watch.replace([str(s) for s in saved])
        restored.set(True)

    @reactive.effect
    async def _persist():
        symbols = watch.symbols()
        if restored():  # never overwrite a saved list with the defaults before it has been read
            await session.send_custom_message("compass-watchlist", symbols)

    @reactive.effect
    def _load():
        symbols = tuple(watch.symbols())
        if symbols:
            quotes.load(symbols)
            histories.load(symbols, "2y")

    @reactive.effect
    @reactive.event(input.open)
    def _open():
        on_open(input.open())

    @reactive.effect
    @reactive.event(input.remove)
    def _remove():
        watch.remove(input.remove())

    @render.ui
    def table():
        symbols = watch.symbols()
        if not symbols:
            return c.empty_state("Your watchlist is empty", "Add tickers with the search box, or use ☆ Watch on any stock.")
        snaps, prices = known_quotes(), known_prices()
        if not snaps and quotes.result() is None:
            return c.skeleton(height=260)
        loading = quotes.loading()
        bench = ctx.benchmark_prices()

        rows = []
        for symbol in symbols:
            snap = snaps.get(symbol)
            remove = tags.button("✕", type="button", class_="icon-btn", title=f"Remove {symbol}",
                                 aria_label=f"Remove {symbol}", data_shiny_event=session.ns("remove"),
                                 data_value=symbol)
            if snap is None:
                note = "Loading…" if loading else "Not found on Yahoo"
                rows.append(tags.tr(tags.td(tags.strong(symbol), tags.div(note, class_="micro muted")),
                                    *[tags.td("—") for _ in range(7)], tags.td(remove)))
                continue
            history = prices.get(symbol)
            close = history["adjclose"] if history is not None else None
            m = metric_set.snapshot_metrics(snap)
            returns = {}
            if close is not None and len(close) > 1:
                m.update(metric_set.price_metrics(close, bench))
                returns = performance.period_returns(close)
            pillars = scoring.score_pillars(m, is_financial=snap.is_financial, is_fund=snap.is_fund)
            current = symbol == ctx.symbol()
            rows.append(tags.tr(
                tags.td(tags.button(tags.span(symbol, class_="sym"), tags.span(snap.name, class_="name"),
                                    type="button", class_="watch-open", data_shiny_event=session.ns("open"),
                                    data_value=symbol, title=f"Open {snap.name}")),
                tags.td(fmt.price(snap.price, snap.currency_symbol)),
                tags.td(c.delta(snap.change_pct)),
                tags.td(c.delta(returns.get("YTD"))),
                tags.td(c.delta(returns.get("1Y"))),
                tags.td(fmt.mult(m.get("forward_pe"))),
                tags.td(c.delta(m.get("analyst_upside")) if m.get("analyst_upside") is not None else "—"),
                tags.td(score_badges(pillars)),
                tags.td(remove),
                class_="current" if current else None,
            ))
        head = ["Company", "Price", "Today", "YTD", "1 year", "Fwd P/E", "Analyst upside", "Quick scores", ""]
        return tags.div(
            tags.div(tags.table(tags.thead(tags.tr(*[tags.th(h) for h in head])), tags.tbody(*rows),
                                class_="c-table watch-table"), class_="table-scroll"),
            tags.p("Quick scores use quote and price data only (no financial statements), so they can differ "
                   "slightly from the full scorecard. V Value · Q Quality · G Growth · H Health · M Momentum.",
                   class_="micro muted", style="margin:12px 0 0"),
            class_="c-card",
        )

    @render_plotly
    def compare():
        prices = known_prices()
        req(prices)
        months = int(input.period())
        start = pd.Timestamp.today().normalize() - pd.DateOffset(months=months)
        lines = {}
        for symbol in watch.symbols():
            history = prices.get(symbol)
            if history is None:
                continue
            series = history["adjclose"][history.index >= start]
            if len(series) > 1:
                lines[symbol] = performance.rebase(series)
        bench = ctx.benchmark_prices()
        if bench is not None:
            series = bench[bench.index >= start]
            if len(series) > 1:
                lines[config.BENCHMARK_LABEL] = performance.rebase(series)
        if not lines:
            return charts.empty_figure("Add tickers to compare")
        return charts.comparison_chart(lines)
