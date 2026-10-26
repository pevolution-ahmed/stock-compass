"""Valuation tab: multiples vs their own history, analyst targets, and an adjustable DCF."""

from __future__ import annotations

from dataclasses import replace

from htmltools import tags
from shiny import module, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

from ..analytics import dcf, valuation
from ..analytics import metrics as metric_set
from ..state import StockContext
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt

HISTORY_CHOICES = {
    "trailing_pe": "P/E", "forward_pe": "Forward P/E", "ev_ebitda": "EV/EBITDA",
    "price_to_sales": "P/S", "price_to_book": "P/B",
}
COLUMN_FOR = {key: column for column, (_, key) in valuation.HISTORY_COLUMNS.items()}
DISCOUNTS = [-0.02, -0.01, 0.0, 0.01, 0.02]
TERMINALS = [0.015, 0.02, 0.025, 0.03, 0.035]
RECOMMENDATION = [(1.5, "Strong buy"), (2.5, "Buy"), (3.5, "Hold"), (4.5, "Underperform"), (9, "Sell")]


@module.ui
def valuation_ui():
    sliders = c.card(
        ui.input_slider("growth", "Free cash flow growth, years 1–5", min=-10, max=40, value=8, step=0.5, post="%",
                        width="100%"),
        ui.input_slider("discount", "Discount rate (required return)", min=6, max=16, value=9, step=0.25, post="%",
                        width="100%"),
        ui.input_slider("terminal", "Long-run growth after year 10", min=0, max=4, value=2.5, step=0.25, post="%",
                        width="100%"),
        tags.div(ui.input_action_button("reset", "Reset to defaults", class_="btn-pill-outline"),
                 ui.output_ui("dcf_defaults_note")),
        title="Your assumptions", subtitle="Drag to see how sensitive the value is.",
    )
    dcf_block = ui.panel_conditional(
        "output.dcf_available === 'yes'",
        tags.div(c.card(ui.output_ui("dcf_result"), class_="dcf-result"), sliders, class_="grid grid-2"),
        tags.div(
            c.card(output_widget("dcf_chart", height="280px"), title="Projected cash flows",
                   subtitle="Faded bars: projected free cash flow · solid bars: what each is worth today"),
            c.card(ui.output_ui("sensitivity"), title="Sensitivity",
                   subtitle="Value per share by discount rate (rows) and long-run growth g (columns); green = above today's price"),
            class_="grid grid-2 mt-3",
        ),
    )
    return tags.div(
        c.section("Multiples", ui.output_ui("multiples"),
                  subtitle="Today's price multiples compared with their own median over Yahoo's ~4-year history."),
        tags.section(
            tags.div(
                c.card(output_widget("history", height="300px"), title="Valuation history",
                       subtitle="Quarterly readings; dashed line = median, shaded band = full range",
                       actions=ui.output_ui("history_picker")),
                c.card(ui.output_ui("targets"), title="Analyst price targets"),
                class_="grid grid-3-1",
            ),
            class_="section",
        ),
        c.section("Intrinsic value (DCF)", ui.output_ui("dcf_unavailable"), dcf_block,
                  subtitle="What the business could be worth from the cash it may generate. "
                           "A model, not a forecast — try your own assumptions."),
        class_="page",
    )


@module.server
def valuation_server(input, output, session, ctx: StockContext):
    @reactive.calc
    def multiples_context() -> dict[str, valuation.MultipleContext]:
        st = ctx.statements.value()
        return valuation.context(st.valuation, ctx.metrics())

    @render.ui
    def multiples():
        snap = ctx.snapshot.value()
        if snap.is_fund:
            return c.empty_state(f"Company valuation multiples don't apply to {snap.kind_phrase}",
                                 "See Performance & Risk for how it has done.")
        m = ctx.metrics()
        context = multiples_context()
        treasury = ctx.treasury.value_or_none()

        def multiple_tile(key, label, help=None):
            mc = context.get(key)
            sub = None
            if mc is not None and mc.premium is not None and abs(mc.premium) < 0.02:
                sub = f"median {fmt.mult(mc.median)} · in line"
            elif mc is not None and mc.premium is not None:
                cheaper = mc.premium < 0
                sub = tags.span(f"median {fmt.mult(mc.median)} · ",
                                tags.span(f"{fmt.pct(abs(mc.premium), 0)} {'below' if cheaper else 'above'}",
                                          class_=f"delta {'up' if cheaper else 'down'}"))
            elif mc is not None and mc.median is not None:
                sub = f"median {fmt.mult(mc.median)}"
            return c.kpi(label, fmt.mult(m.get(key)), sub, help=help)

        tiles = [
            multiple_tile("trailing_pe", "P/E (trailing)", "Price ÷ last 12 months' earnings per share."),
            multiple_tile("forward_pe", "P/E (forward)", "Price ÷ expected earnings over the next 12 months."),
            c.kpi("PEG ratio", fmt.num(m.get("peg")), "P/E ÷ expected growth; ~1 is often seen as fair"),
        ]
        if snap.is_financial:
            tiles += [
                multiple_tile("price_to_book", "Price / book", "Banks are typically valued against book value."),
                c.kpi("Return on equity", fmt.pct(m.get("roe")), "what the book value earns"),
            ]
        else:
            tiles += [
                multiple_tile("ev_ebitda", "EV / EBITDA", "Enterprise value ÷ EBITDA; ignores capital structure."),
                multiple_tile("price_to_sales", "Price / sales"),
                multiple_tile("price_to_book", "Price / book"),
                c.kpi("Free cash flow yield", fmt.pct(m.get("fcf_yield")), f"FCF {fmt.money(m.get('fcf'), snap.statement_symbol)} (TTM)",
                      help="Free cash flow ÷ market cap."),
            ]
        earnings_yield = m.get("earnings_yield")
        tiles.append(c.kpi(
            "Earnings yield", fmt.pct(earnings_yield),
            tags.span(f"10-yr Treasury {fmt.pct(treasury, 2)} · ",
                      c.delta(earnings_yield - treasury if earnings_yield is not None and treasury else None,
                              lambda v: f"{v * 100:+.1f} pts")),
            help="Earnings ÷ price (inverse of P/E), compared with what a risk-free bond pays.",
        ))
        return tags.div(*tiles, class_="grid grid-kpi")

    @reactive.calc
    def available_history() -> dict[str, str]:
        st = ctx.statements.value()
        return {key: label for key, label in HISTORY_CHOICES.items()
                if len(valuation.history_series(st.valuation, COLUMN_FOR[key])) >= 4}

    @render.ui
    def history_picker():
        choices = available_history()
        if not choices:
            return None
        return tags.div(ui.input_radio_buttons("history_metric", None, choices, selected=next(iter(choices)),
                                               inline=True), class_="segmented")

    @render_plotly
    def history():
        choices = available_history()
        if not choices:
            return charts.empty_figure("No valuation history available")
        # The picker renders after the chart, so the input may not exist yet
        picked = input.history_metric() if "history_metric" in input else None
        key = picked if picked in choices else next(iter(choices))
        series = valuation.history_series(ctx.statements.value().valuation, COLUMN_FOR[key])
        return charts.multiple_history(series, choices[key], multiples_context()[key].median)

    @render.ui
    def targets():
        snap = ctx.snapshot.value()
        m = ctx.metrics()
        low, high, mean = snap.get("targetLowPrice"), snap.get("targetHighPrice"), snap.get("targetMeanPrice")
        if not mean:
            return c.empty_state("No analyst coverage", "Yahoo has no price targets for this symbol.")
        rec = m.get("recommendation_mean")
        label = next((name for limit, name in RECOMMENDATION if rec is not None and rec < limit), None)
        return tags.div(
            c.target_range(low, mean, high, snap.price, snap.currency_symbol),
            tags.div(
                c.kpi("Upside to mean target", c.delta(m.get("analyst_upside")),
                      f"{fmt.integer(m.get('analyst_count'))} analysts"),
                c.kpi("Consensus", label or "—", f"mean rating {fmt.num(rec)} (1 = strong buy, 5 = sell)"),
                class_="grid", style="grid-template-columns:1fr;margin-top:20px",
            ),
        )

    # ---------- DCF ----------

    @reactive.calc
    def defaults() -> dcf.Assumptions | None:
        snap = ctx.snapshot.value()
        st = ctx.statements.value()
        rf = ctx.risk_free.value_or_none() or 0.04
        return metric_set.dcf_inputs(snap, st, ctx.metrics(), rf)

    def apply_defaults(a: dcf.Assumptions) -> None:
        ui.update_slider("growth", value=round(a.growth * 200) / 2)
        ui.update_slider("discount", value=round(a.discount * 400) / 4)
        ui.update_slider("terminal", value=round(a.terminal_growth * 400) / 4)

    @reactive.effect
    @reactive.event(ctx.symbol, ctx.statements.task.status)
    def _seed_sliders():
        a = defaults()
        if a is not None:
            apply_defaults(a)

    @reactive.effect
    @reactive.event(input.reset)
    def _reset():
        a = defaults()
        if a is not None:
            apply_defaults(a)

    @reactive.calc
    def assumptions() -> dcf.Assumptions | None:
        a = defaults()
        if a is None:
            return None
        return replace(a, growth=input.growth() / 100, discount=input.discount() / 100,
                       terminal_growth=input.terminal() / 100)

    @output(suspend_when_hidden=False)
    @render.text
    def dcf_available():
        return "yes" if ctx.statements.result() is not None and defaults() is not None else "no"

    @render.ui
    def dcf_unavailable():
        snap = ctx.snapshot.value()
        if ctx.statements.result() is None:
            return c.skeleton(height=200)
        if defaults() is not None:
            return None
        if snap.is_fund:
            reason = (f"There are no company cash flows to discount for {snap.kind_phrase}",
                      "Valuation models apply to individual companies.")
        elif snap.is_financial:
            reason = ("A cash-flow DCF doesn't suit banks and insurers",
                      "Their cash flows mix in deposits and loans. Price/book against return on equity is the usual yardstick.")
        elif not snap.fx:
            reason = (f"No exchange rate for {snap.financial_currency} → {snap.major_currency}",
                      "The financial statements and the share price use different currencies.")
        else:
            reason = ("Free cash flow is negative or unavailable",
                      "With no positive cash flow to project, a DCF would only reflect guesses about the future.")
        return c.empty_state(*reason)

    @render.ui
    def dcf_result():
        snap = ctx.snapshot.value()
        a = assumptions()
        req(a is not None)
        result = dcf.value(a)
        if result is None:
            return c.empty_state("Discount rate must be above long-run growth",
                                 "Raise the discount rate or lower the long-run growth.")
        symbol, price = snap.currency_symbol, snap.price
        margin = result.per_share / price - 1 if price else None
        implied = dcf.implied_growth(a, price) if price else None
        return tags.div(
            tags.div("Estimated value per share", class_="kpi-label"),
            tags.div(tags.span(symbol, class_="currency"), fmt.num(result.per_share), class_="fair-value"),
            tags.div(c.delta(margin, lambda v: f"{v * 100:+.0f}%", chip=True),
                     tags.span(f" vs price {fmt.price(price, symbol)} · ",
                               "price is below this value" if (margin or 0) > 0 else "price is above this value",
                               class_="muted micro")),
            tags.ul(
                tags.li(tags.strong("Priced in: "),
                        f"today's price implies {fmt.pct(implied)} a year free-cash-flow growth for 5 years"
                        if implied is not None else "the price is outside what any growth from −50% to +100% explains"),
                tags.li(tags.strong("Terminal weight: "),
                        f"{fmt.pct(result.terminal_share, 0)} of the value comes from after year 10"),
                tags.li(tags.strong("Starting point: "),
                        f"{fmt.money(a.fcf, snap.statement_symbol)} free cash flow (TTM), "
                        f"{fmt.money(a.net_cash, snap.statement_symbol)} net cash, {a.shares / 1e9:,.2f}B shares"
                        + (f" · converted at {snap.fx:.4g} {snap.major_currency} per {snap.financial_currency}"
                           if snap.financial_currency != snap.major_currency else "")),
                class_="dcf-facts",
            ),
        )

    @render.ui
    def sensitivity():
        snap = ctx.snapshot.value()
        a = assumptions()
        req(a is not None and a.discount > a.terminal_growth)
        symbol, price = snap.currency_symbol, snap.price
        discounts = [a.discount + d for d in DISCOUNTS]
        grid = dcf.sensitivity(a, discounts, TERMINALS)
        rows = []
        for d, rate, row in zip(DISCOUNTS, discounts, grid):
            cells = [tags.span(fmt.pct(rate, 2), class_="strong" if d == 0 else None)]
            for g, v in zip(TERMINALS, row):
                tone = "flat" if v is None or not price else ("up" if v >= price else "down")
                current = d == 0 and abs(g - a.terminal_growth) < 1e-9
                cells.append(tags.span(fmt.price(v, symbol) if v else "—",
                                       class_=f"cell {tone}" + (" current" if current else "")))
            rows.append(cells)
        return c.table(["Rate"] + [f"g {fmt.pct(g, 1)}" for g in TERMINALS], rows, class_="sensitivity")

    @render_plotly
    def dcf_chart():
        a = assumptions()
        req(a is not None)
        result = dcf.value(a)
        req(result is not None)
        return charts.dcf_bars(result.years, result.cash_flows, result.present_values,
                               prefix=ctx.snapshot.value().statement_symbol)

    @render.ui
    def dcf_defaults_note():
        a = defaults()
        if a is None:
            return None
        beta = ctx.snapshot.value().get("beta")
        rf = ctx.risk_free.value_or_none() or 0.04
        return tags.p(
            f"Defaults — growth = 3-year revenue growth capped at 0–20% ({fmt.pct(a.growth)}); "
            f"discount = {fmt.pct(rf, 2)} T-bill + beta {fmt.num(beta)} × {fmt.pct(dcf.EQUITY_RISK_PREMIUM)} "
            f"equity premium, kept within 7–14% ({fmt.pct(a.discount, 2)}); "
            "growth fades to the long-run rate over years 6–10.",
            class_="micro muted", style="margin-top:12px",
        )
