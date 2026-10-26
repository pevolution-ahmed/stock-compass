"""Performance & Risk tab: ROI calculator, period returns, risk metrics and return history."""

from __future__ import annotations

from datetime import date

import pandas as pd
from htmltools import tags
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from .. import config
from ..analytics import performance, risk
from ..state import StockContext
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt

RISK_WINDOWS = {"1": "1Y", "3": "3Y", "5": "5Y", "10": "10Y", "max": "Max"}
PERIOD_LABELS = {"1M": "1 month", "3M": "3 months", "6M": "6 months", "YTD": "Year to date",
                 "1Y": "1 year", "3Y": "3 years", "5Y": "5 years", "10Y": "10 years", "Max": "Since listing"}
ANNUALIZE_FROM = {"3Y": 3, "5Y": 5, "10Y": 10}


def five_years_ago() -> date:
    today = date.today()
    return today.replace(year=today.year - 5)


@module.ui
def performance_ui():
    calculator = c.card(
        tags.div(
            ui.input_numeric("amount", "Amount invested", 10_000, min=1, step=500),
            ui.input_date("start", "Invested on", value=five_years_ago(), max=date.today()),
            ui.input_switch("reinvest", "Reinvest dividends", True),
            class_="calc-inputs",
        ),
        ui.output_ui("calc_result"),
        output_widget("calc_chart", height="300px"),
        title="If you had invested…",
        subtitle=f"What a past investment is worth today, compared with the same amount in the {config.BENCHMARK_LABEL}.",
    )
    return tags.div(
        c.section("Return on investment",
                  tags.div(calculator, c.card(ui.output_ui("period_table"), title="Total return by period",
                                              subtitle="Dividends reinvested; 3Y+ also shown per year"),
                           class_="grid grid-2")),
        c.section("Risk", ui.output_ui("risk_kpis"),
                  c.card(output_widget("drawdown", height="260px"), title="Drawdown from previous peak",
                         subtitle="How far below its last high the stock was at each point", class_="mt-3"),
                  subtitle="How bumpy the ride has been, and whether the return paid for it.",
                  actions=tags.div(ui.input_radio_buttons("window", None, RISK_WINDOWS, selected="5",
                                                          inline=True), class_="segmented")),
        c.section("Return history",
                  tags.div(
                      c.card(output_widget("calendar", height="300px"), title="Calendar-year returns",
                             subtitle=f"Bars: stock · dashes: {config.BENCHMARK_LABEL}"),
                      c.card(ui.output_ui("extremes"), title="Best and worst"),
                      class_="grid grid-3-1",
                  ),
                  c.card(output_widget("heatmap"), title="Monthly returns (%)", subtitle="Last 10 years",
                         class_="mt-3")),
        class_="page",
    )


@module.server
def performance_server(input, output, session, ctx: StockContext):
    @reactive.effect
    def _limit_dates():
        history = ctx.history.value()
        first = history.index[0].date()
        start = max(five_years_ago(), first)
        ui.update_date("start", value=start, min=first, max=history.index[-1].date())

    @reactive.calc
    def investment():
        amount = input.amount()
        start = input.start()
        if not amount or amount <= 0 or start is None:
            return None, None
        history = ctx.history.value()
        result = performance.investment_growth(history, float(amount), pd.Timestamp(start), input.reinvest())
        bench = ctx.benchmark.value_or_none()
        bench_result = (performance.investment_growth(bench, float(amount), result.start, input.reinvest())
                        if bench is not None and result is not None else None)
        return result, bench_result

    @render.ui
    def calc_result():
        snap = ctx.snapshot.value()
        result, bench = investment()
        if result is None:
            return c.empty_state("Enter an amount and a start date")
        symbol = snap.major_symbol
        tiles = [
            c.kpi("Worth today", fmt.amount(result.final_value, symbol),
                  f"from {fmt.amount(result.invested, symbol)} on {fmt.day(result.start.date())}"),
            c.kpi("Gain / loss", c.delta(result.gain, lambda v: fmt.amount(v, symbol)),
                  fmt.pct(result.gain_pct, sign=True)),
            c.kpi("Per year", fmt.pct(result.cagr), "compound annual growth", tone=fmt.tone(result.cagr)),
        ]
        if bench is not None:
            tiles.append(c.kpi(f"Same in {config.BENCHMARK_LABEL}", fmt.amount(bench.final_value, symbol),
                               c.delta(result.final_value - bench.final_value, lambda v: fmt.amount(v, symbol),
                                       suffix=" vs index")))
        if not input.reinvest() and result.dividends:
            tiles.append(c.kpi("Dividends received", fmt.amount(result.dividends, symbol), "kept as cash"))
        return tags.div(*tiles, class_="calc-result")

    @render_plotly
    def calc_chart():
        result, bench = investment()
        if result is None:
            return charts.empty_figure("No data for this date range")
        lines = {ctx.symbol(): result.value}
        if bench is not None:
            lines[config.BENCHMARK_LABEL] = bench.value
        return charts.growth_chart(lines, prefix=ctx.snapshot.value().major_symbol, height=300)

    @render.ui
    def period_table():
        stock = performance.period_returns(ctx.prices())
        bench_prices = ctx.benchmark_prices()
        bench = performance.period_returns(bench_prices) if bench_prices is not None else {}
        rows = []
        for key, label in PERIOD_LABELS.items():
            value, base = stock.get(key), bench.get(key)
            years = ANNUALIZE_FROM.get(key)
            per_year = (tags.div(fmt.pct(performance.annualize(value, years * 365.25)) + " /yr",
                                 class_="micro muted") if years and value is not None else None)
            rows.append([
                label,
                tags.div(c.delta(value), per_year),
                c.delta(base) if key != "Max" else tags.span("—", class_="muted"),
                c.delta(value - base) if value is not None and base is not None and key != "Max" else "—",
            ])
        return c.table(["Period", ctx.symbol(), config.BENCHMARK_LABEL, "Difference"], rows)

    @reactive.calc
    def window_years():
        return None if input.window() == "max" else float(input.window())

    @reactive.calc
    def risk_window():
        rf = ctx.risk_free.value_or_none() or config.RISK_FREE_FALLBACK
        return risk.risk_report(ctx.prices(), ctx.benchmark_prices(), rf, years=window_years())

    @render.ui
    def risk_kpis():
        report = risk_window()
        rf = ctx.risk_free.value_or_none() or config.RISK_FREE_FALLBACK
        drawdown = report.max_drawdown
        recovery = ("not yet recovered" if drawdown and drawdown.recovery is None
                    else f"recovered in {drawdown.days_to_recover} days" if drawdown else None)
        label = f"over {report.years:.1f} years"
        bench = config.BENCHMARK_LABEL
        tiles = [
            c.kpi("Volatility", fmt.pct(report.volatility), f"annualized, {label}",
                  help="Standard deviation of daily returns, scaled to a year. The S&P 500 is typically ~15–20%."),
            c.kpi("Max drawdown", fmt.pct(drawdown.depth if drawdown else None), recovery,
                  tone="down" if drawdown else None, help="Largest fall from a peak to a later low."),
            c.kpi("Sharpe ratio", fmt.num(report.sharpe), f"risk-free {fmt.pct(rf, 2)}",
                  help="Excess return per unit of volatility. Above 1 is strong; below 0 means cash did better."),
            c.kpi("Sortino ratio", fmt.num(report.sortino), "penalizes only downside moves",
                  help="Like Sharpe, but only counts downside volatility."),
            c.kpi("Calmar ratio", fmt.num(report.calmar), "CAGR ÷ max drawdown",
                  help="Return earned per unit of worst-case loss. Above 1 is good."),
            c.kpi("Beta", fmt.num(report.beta), f"vs {bench}, monthly",
                  help="Sensitivity to market moves: 1.2 means ~12% when the market moves 10%."),
            c.kpi("Value at risk (95%)", fmt.pct(report.var_95), "1-day loss exceeded 1 day in 20",
                  help="Historical daily loss that was exceeded on only 5% of days."),
            c.kpi("Up / down capture", f"{fmt.pct(report.up_capture, 0)} / {fmt.pct(report.down_capture, 0)}",
                  f"of {bench}'s up and down months",
                  help="Average share of the index's monthly gains (and losses) the stock delivered."),
        ]
        return tags.div(*tiles, class_="grid grid-kpi")

    @render_plotly
    def drawdown():
        prices = performance.trailing(ctx.prices(), window_years())
        lines = {ctx.symbol(): risk.drawdown_series(prices)}
        bench = ctx.benchmark_prices()
        if bench is not None:
            lines[config.BENCHMARK_LABEL] = risk.drawdown_series(bench[bench.index >= prices.index[0]])
        return charts.drawdown_chart(lines)

    @render_plotly
    def calendar():
        stock = performance.calendar_year_returns(ctx.prices()).tail(15)
        bench_prices = ctx.benchmark_prices()
        bench = performance.calendar_year_returns(bench_prices) if bench_prices is not None else None
        return charts.calendar_bars(stock, bench, ctx.symbol(), config.BENCHMARK_LABEL)

    @render_plotly
    def heatmap():
        prices = ctx.prices()
        table = performance.monthly_returns(prices[prices.index.year > prices.index[-1].year - 10])
        return charts.monthly_heatmap(table)

    @render.ui
    def extremes():
        prices = performance.trailing(ctx.prices(), 10)
        stats = performance.return_stats(prices)
        if stats is None:
            return c.empty_state("Not enough history")
        when = lambda ts, monthly=False: f"{ts:%b %Y}" if monthly else fmt.day(ts.date())
        rows = [
            ["Best day", c.delta(stats.best_day[1]), when(stats.best_day[0])],
            ["Worst day", c.delta(stats.worst_day[1]), when(stats.worst_day[0])],
            ["Best month", c.delta(stats.best_month[1]), when(stats.best_month[0], True)],
            ["Worst month", c.delta(stats.worst_month[1]), when(stats.worst_month[0], True)],
            ["Up days", fmt.pct(stats.positive_days, 0), ""],
            ["Up months", fmt.pct(stats.positive_months, 0), ""],
        ]
        return tags.div(c.table(["Last 10 years", "Return", "When"], rows))
