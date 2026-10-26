"""Technicals tab: candlesticks with moving averages, Bollinger Bands or Ichimoku, plus RSI and MACD."""

from __future__ import annotations

import pandas as pd
from htmltools import tags
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from ..analytics import technicals
from ..state import StockContext
from ..ui import charts
from ..ui import components as c

PERIODS = {"6": "6M", "12": "1Y", "24": "2Y", "60": "5Y"}
OVERLAYS = {"ma": "Moving averages", "bollinger": "Bollinger Bands", "ichimoku": "Ichimoku Cloud"}
EXPLAINERS = {
    "ma": "The 50- and 200-day averages smooth out daily noise. Price above a rising 200-day average is the "
          "classic sign of a long-term uptrend; the 50-day crossing above the 200-day is called a golden cross.",
    "bollinger": "Bands sit about two standard deviations either side of the 20-day average, so roughly 95% of "
                 "closes fall inside. Touching a band shows price is stretched; narrowing bands often precede a big move.",
    "ichimoku": "The cloud (between Span A and B, projected 26 days ahead) marks support and resistance: green when "
                "Span A is above Span B. Price above the cloud suggests an uptrend, below it a downtrend.",
}


@module.ui
def technicals_ui():
    controls = tags.div(
        tags.div(ui.input_radio_buttons("overlay", None, OVERLAYS, selected="ma", inline=True), class_="segmented"),
        tags.div(ui.input_radio_buttons("period", None, PERIODS, selected="12", inline=True), class_="segmented"),
        class_="controls",
    )
    return tags.div(
        c.section("Signals", ui.output_ui("signals"),
                  subtitle="What the indicators say right now. Technical signals describe price behavior; "
                           "they don't predict it."),
        c.section("Price", controls,
                  c.card(output_widget("price", height="460px"), ui.output_ui("explainer"), class_="mt-3")),
        tags.section(
            tags.div(
                c.card(output_widget("rsi", height="240px"), title="Relative strength index (14 days)",
                       subtitle="Above 70 = overbought, below 30 = oversold"),
                c.card(output_widget("macd", height="240px"), title="MACD (12, 26, 9)",
                       subtitle="Momentum: MACD crossing above its signal line is a bullish sign"),
                class_="grid grid-2",
            ),
            class_="section",
        ),
        class_="page",
    )


@module.server
def technicals_server(input, output, session, ctx: StockContext):
    @reactive.calc
    def data() -> pd.DataFrame:
        return technicals.indicators(ctx.history.value())

    @reactive.calc
    def window() -> pd.DataFrame:
        df = data()
        start = df.index[-1] - pd.DateOffset(months=int(input.period()))
        return df[df.index >= start]

    @render.ui
    def signals():
        items = technicals.signals(data())
        return tags.div(
            *[tags.div(tags.div(tags.span(class_=f"dot {tone}"), headline, class_="signal-head"),
                       tags.div(detail, class_="signal-detail"), class_="signal")
              for tone, headline, detail in items],
            class_="signals",
        )

    @render_plotly
    def price():
        return charts.price_chart(window(), input.overlay())

    @render.ui
    def explainer():
        return tags.p(EXPLAINERS[input.overlay()], class_="micro muted", style="margin:12px 0 0")

    @render_plotly
    def rsi():
        return charts.rsi_chart(window()["rsi"], height=240)

    @render_plotly
    def macd():
        return charts.macd_chart(window()[["macd", "signal", "histogram"]], height=240)
