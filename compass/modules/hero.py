"""Persistent quote header: identity, big price, day change, ranges and key facts."""

from __future__ import annotations

from datetime import date

from htmltools import TagChild, tags
from shiny import module, render, ui

from .. import config
from ..state import StockContext
from ..ui import components as c
from ..ui import formatting as fmt


@module.ui
def hero_ui(search: TagChild):
    return tags.header(
        tags.div(
            tags.div(
                tags.div(ui.output_ui("quote"), class_="hero-main"),
                tags.div(search, ui.output_ui("ranges"), class_="hero-side"),
                class_="hero-top",
            ),
            class_="page hero",
        ),
    )


@module.server
def hero_server(input, output, session, ctx: StockContext):
    @render.ui
    def quote():
        result = ctx.snapshot.result()
        if result is None:
            return tags.div(c.skeleton(lines=2), c.skeleton(height=90))
        if result.error:
            return c.empty_state(
                f"We couldn't find “{ctx.symbol()}”",
                "Check the ticker, or try one of these:",
                tags.div(*[c.pick_pill(s) for s in config.QUICK_PICKS], class_="quick-picks",
                         style="justify-content:center;margin-top:12px"),
            )
        snap = result.value
        meta = [
            c.pill("Market cap ", fmt.money(snap.market_cap, snap.currency_symbol), variant="soft")
            if snap.market_cap else None,
            c.pill(snap.sector, variant="fog") if snap.sector else None,
            c.pill(snap.industry, variant="fog") if snap.industry else None,
            c.pill("Fund · ", snap.quote_type.title(), variant="fog") if snap.is_fund else None,
        ]
        if snap.next_earnings and snap.next_earnings >= date.today():
            meta.append(c.pill("Earnings ", fmt.day(snap.next_earnings), variant="outline"))
        return tags.div(
            tags.div(
                tags.h1(snap.name, class_="hero-name"),
                c.pill(snap.symbol, variant="forest"),
                c.pill(snap.exchange, variant="fog") if snap.exchange else None,
                class_="hero-id",
            ),
            tags.div(tags.span(snap.currency_symbol, class_="currency"), fmt.num(snap.price),
                     class_="display-price", aria_label=f"Price {fmt.price(snap.price, snap.currency_symbol)}"),
            tags.div(
                c.delta(snap.change_pct, chip=True),
                c.delta(snap.change, lambda v: ("+" if v > 0 else "") + fmt.money(v, snap.currency_symbol, compact=False),
                        arrow=False),
                tags.span(f"today · {snap.currency}", class_="muted micro"),
                class_="hero-quote",
            ),
            tags.div(*meta, class_="hero-meta"),
        )

    @render.ui
    def ranges():
        snap = ctx.snapshot.value_or_none()
        if snap is None:
            return None
        symbol = snap.currency_symbol
        low, high = snap.get("fiftyTwoWeekLow"), snap.get("fiftyTwoWeekHigh")
        day_low, day_high = snap.get("regularMarketDayLow"), snap.get("regularMarketDayHigh")
        return tags.div(
            c.range_bar(low, high, snap.price, fmt.price(low, symbol), fmt.price(high, symbol),
                        caption="52-week range"),
            c.range_bar(day_low, day_high, snap.price, fmt.price(day_low, symbol),
                        fmt.price(day_high, symbol), caption="Day range"),
            class_="hero-range",
        )
