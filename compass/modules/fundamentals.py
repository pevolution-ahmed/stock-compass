"""Fundamentals tab: growth and margins, returns on capital, health, Piotroski, shareholder returns."""

from __future__ import annotations

from htmltools import tags
from shiny import module, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

from ..analytics import fundamentals as fa
from ..state import StockContext
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt

Z_ZONES = [("Distress", 0, 1.81, "down"), ("Grey zone", 1.81, 2.99, "flat"), ("Safe", 2.99, 6, "up")]


@module.ui
def fundamentals_ui():
    return tags.div(
        ui.output_ui("not_applicable"),
        ui.panel_conditional(
            "output.applicable === 'yes'",
            c.section("Income & cash flow",
                      tags.div(
                          c.card(output_widget("income", height="320px"), title="Revenue, profit and free cash flow",
                                 subtitle=ui.output_text("growth_line", inline=True)),
                          c.card(output_widget("margins", height="320px"), title="Margins",
                                 subtitle="Share of revenue kept at each level"),
                          class_="grid grid-2",
                      )),
            c.section("Returns on capital", ui.output_ui("returns"),
                      subtitle="How much profit the business earns on the money invested in it."),
            c.section("Financial health",
                      tags.div(ui.output_ui("health"), c.card(ui.output_ui("altman"), title="Altman Z-score"),
                               class_="grid grid-3-1")),
            c.section("Piotroski F-score", c.card(ui.output_ui("piotroski")),
                      subtitle="Nine yes/no tests of profitability, balance-sheet strength and efficiency, "
                               "comparing the latest fiscal year with the one before. 8–9 is strong, 0–2 weak."),
            c.section("Shareholder returns", ui.output_ui("payout_kpis"),
                      tags.div(
                          c.card(output_widget("payouts", height="300px"), title="Cash returned to shareholders",
                                 subtitle="Dividends and buybacks net of shares issued, per fiscal year"),
                          c.card(output_widget("dividends", height="300px"), title="Dividends per share",
                                 subtitle="Calendar years"),
                          class_="grid grid-2 mt-3",
                      )),
        ),
        class_="page",
    )


@module.server
def fundamentals_server(input, output, session, ctx: StockContext):
    @reactive.calc
    def statements():
        st = ctx.statements.value()
        req(not st.empty)
        return st

    @output(suspend_when_hidden=False)
    @render.text
    def applicable():
        result = ctx.statements.result()
        snap = ctx.snapshot.value_or_none()
        ok = result is not None and result.value is not None and not result.value.empty
        return "yes" if ok and snap is not None and not snap.is_fund else "no"

    @render.ui
    def not_applicable():
        snap = ctx.snapshot.value()
        result = ctx.statements.result()
        if result is None:
            return tags.section(c.skeleton(height=320), class_="section")
        if snap.is_fund:
            return tags.section(c.empty_state("Funds don't publish company financials",
                                              "See Performance & Risk for how this fund has done."), class_="section")
        if result.value is None or result.value.empty:
            return tags.section(c.empty_state("No financial statements available",
                                              result.error or "Yahoo has no annual statements for this symbol."),
                                class_="section")
        return None

    @render.text
    def growth_line():
        m = ctx.metrics()
        line = (f"Annual growth over 3 years — revenue {fmt.pct(m.get('revenue_cagr_3y'))}, "
                f"EPS {fmt.pct(m.get('eps_cagr_3y'))}")
        return line if ctx.snapshot.value().is_financial else line + f", FCF {fmt.pct(m.get('fcf_cagr_3y'))}"

    @render_plotly
    def income():
        frame = fa.income_and_cash(statements())
        if ctx.snapshot.value().is_financial:
            frame = frame.drop(columns="Free cash flow", errors="ignore")  # meaningless for banks
        return charts.statement_bars(frame, ctx.snapshot.value().currency_symbol)

    @render_plotly
    def margins():
        frame = fa.margins(statements())
        if ctx.snapshot.value().is_financial:
            frame = frame.drop(columns=["Gross", "Free cash flow"], errors="ignore")
        return charts.margin_lines(frame) if not frame.empty else charts.empty_figure("No margin data")

    @render.ui
    def returns():
        snap, m = ctx.snapshot.value(), ctx.metrics()
        if snap.is_financial:
            tiles = [
                c.kpi("Return on equity", fmt.pct(m.get("roe")), "net income ÷ shareholders' equity"),
                c.kpi("Return on assets", fmt.pct(m.get("roa"), 2), "~1% is solid for a bank"),
                c.kpi("Net margin", fmt.pct(m.get("net_margin")), "profit kept from revenue"),
                c.kpi("Equity / assets", fmt.pct(m.get("equity_to_assets")), "capital cushion"),
            ]
        else:
            history = fa.roic_history(statements())
            trend = (f"{fmt.pct(history.iloc[0], 0)} in FY{history.index[0].year}" if len(history) > 1 else None)
            tiles = [
                c.kpi("Return on invested capital", fmt.pct(m.get("roic")), trend and f"vs {trend}",
                      help="After-tax operating profit ÷ debt + equity invested. Above ~15% suggests a durable edge."),
                c.kpi("Return on equity", fmt.pct(m.get("roe")), "net income ÷ shareholders' equity"),
                c.kpi("Return on assets", fmt.pct(m.get("roa")), "net income ÷ total assets"),
                c.kpi("Cash conversion", fmt.mult(m.get("fcf_conversion"), 2), "free cash flow ÷ net income",
                      help="Below 1 means part of the reported profit isn't arriving as cash (often heavy investment)."),
            ]
        return tags.div(*tiles, class_="grid grid-kpi")

    @render.ui
    def health():
        snap, m = ctx.snapshot.value(), ctx.metrics()
        symbol = snap.currency_symbol
        cash, debt = snap.get("totalCash"), snap.get("totalDebt")
        if snap.is_financial:
            tiles = [
                c.kpi("Equity / assets", fmt.pct(m.get("equity_to_assets")), "well-capitalized banks run ~8–10%"),
                c.kpi("Cash & equivalents", fmt.money(cash, symbol)),
                c.kpi("Total debt", fmt.money(debt, symbol)),
            ]
        else:
            net = m.get("net_debt_ebitda")
            tiles = [
                c.kpi("Net debt / EBITDA", fmt.mult(net), "net cash" if (net or 0) < 0 else "years of EBITDA to repay",
                      help="Debt minus cash, divided by a year's EBITDA."),
                c.kpi("Interest coverage", fmt.mult(m.get("interest_coverage")), "operating profit ÷ interest",
                      help="Below ~3x can get uncomfortable if profits fall."),
                c.kpi("Debt / equity", fmt.mult(m.get("debt_to_equity"), 2)),
                c.kpi("Current ratio", fmt.num(m.get("current_ratio")), f"quick ratio {fmt.num(m.get('quick_ratio'))}",
                      help="Short-term assets ÷ short-term liabilities."),
                c.kpi("Cash & investments", fmt.money(cash, symbol)),
                c.kpi("Total debt", fmt.money(debt, symbol)),
            ]
        return tags.div(*tiles, class_="grid grid-kpi grid-kpi-3")

    @render.ui
    def altman():
        snap = ctx.snapshot.value()
        if snap.is_financial:
            return c.empty_state("Not used for banks & insurers", "The model was built for industrial companies.")
        z = fa.altman_z(statements(), snap.market_cap)
        if z is None:
            return c.empty_state("Not enough balance-sheet data")
        verdict = {"safe": "Low bankruptcy risk", "grey": "Some caution warranted", "distress": "Elevated distress risk"}
        parts = [[name, fmt.num(value)] for name, value in z.parts.items()]
        return tags.div(
            tags.div(fmt.num(z.score), class_="z-score"),
            tags.div(verdict[z.zone], class_=f"delta {'up' if z.zone == 'safe' else 'down' if z.zone == 'distress' else 'flat'}"),
            c.zone_bar(z.score, Z_ZONES, 0, 6, f"Z-score {z.score:.2f}, {z.zone} zone"),
            tags.details(tags.summary("How it's built", class_="micro"), c.table(["Weighted part", ""], parts),
                         class_="z-parts"),
        )

    @render.ui
    def piotroski():
        snap = ctx.snapshot.value()
        if snap.is_financial:
            return c.empty_state("Not designed for banks & insurers",
                                 "Several tests (cash flow, liquidity, gross margin) don't apply to a bank's balance sheet.")
        checks = fa.piotroski(statements())
        score = fa.piotroski_score(checks)
        headline = (tags.div(tags.span(f"{score[0]}", class_="z-score"), tags.span(f" / {score[1]} tests passed",
                                                                                 class_="muted"))
                    if score else c.empty_state("Too few tests could be evaluated"))
        return tags.div(headline, c.checklist([(ch.passed, ch.name, ch.detail) for ch in checks]))

    @render.ui
    def payout_kpis():
        snap, m = ctx.snapshot.value(), ctx.metrics()
        history = ctx.history.value()
        dividend_yield, buybacks = m.get("dividend_yield"), m.get("buyback_yield")
        total = (dividend_yield or 0) + (buybacks or 0) if dividend_yield is not None or buybacks is not None else None
        return tags.div(
            c.kpi("Dividend yield", fmt.pct(dividend_yield, 2), f"5-yr average {fmt.pct(m.get('dividend_yield_5y'), 2)}"),
            c.kpi("Dividend growth", fmt.pct(fa.dividend_cagr(history)), "per year, last 5 years"),
            c.kpi("Payout ratio", fmt.pct(m.get("payout_ratio"), 0), "share of earnings paid as dividends"),
            c.kpi("Shareholder yield", fmt.pct(total, 2), f"incl. net buybacks {fmt.pct(buybacks, 2)}",
                  help="Dividends plus net share buybacks, as a share of market cap."),
            class_="grid grid-kpi",
        )

    @render_plotly
    def payouts():
        frame = fa.shareholder_payouts(statements())
        if frame.empty or not frame.abs().values.sum():
            return charts.empty_figure("No dividends or buybacks reported")
        return charts.stacked_payouts(frame, ctx.snapshot.value().currency_symbol)

    @render_plotly
    def dividends():
        by_year = fa.annual_dividends(ctx.history.value())
        if by_year.empty:
            return charts.empty_figure("No dividends paid")
        return charts.dividend_bars(by_year, ctx.snapshot.value().currency_symbol)
