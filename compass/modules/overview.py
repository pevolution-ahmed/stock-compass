"""Overview tab: scorecard, key numbers, growth of $10k and what stands out."""

from __future__ import annotations

from datetime import date, timedelta

from htmltools import tags
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_plotly

from .. import config
from ..analytics import performance, risk
from ..analytics.scoring import PillarScore, Rule
from ..state import StockContext
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt


@module.ui
def overview_ui():
    return tags.div(
        tags.section(ui.output_ui("scorecard"), class_="section"),
        c.section("Key numbers", ui.output_ui("kpis"),
                  subtitle="Returns include reinvested dividends. Risk figures cover the last 5 years."),
        tags.section(
            tags.div(
                c.card(output_widget("growth", height="340px"), title="Growth of 10,000",
                       subtitle=f"Last 5 years vs the {config.BENCHMARK_LABEL}, dividends reinvested"),
                c.card(ui.output_ui("notes"), title="What stands out"),
                class_="grid grid-3-1",
            ),
            class_="section",
        ),
        c.section("About", ui.output_ui("about")),
        class_="page",
    )


def thresholds(rule: Rule) -> str:
    show = lambda v: fmt.by_kind(v, rule.fmt)
    if rule.good > rule.bad:
        return f"100 at ≥ {show(rule.good)}, 0 at ≤ {show(rule.bad)}"
    return f"100 at ≤ {show(rule.good)}, 0 at ≥ {show(rule.bad)}"


def pillar_card(pillar: PillarScore, is_financial: bool = False):
    score = pillar.score
    if score is None:
        if pillar.applicable:
            reason = "Not enough data"
        else:
            reason = "Not used for banks & insurers" if is_financial else "Not applicable"
        score_view = tags.div(reason, class_="pillar-score na")
    else:
        score_view = tags.div(f"{score:.0f}", tags.small("/100"), class_="pillar-score")
    items = [
        tags.li(
            tags.span(m.rule.label),
            tags.span(fmt.by_kind(m.value, m.rule.fmt), class_="v"),
            tags.span(("n/a" if m.score is None else f"Score {m.score:.0f}") + " · " + thresholds(m.rule),
                      class_="t"),
        )
        for m in pillar.metrics
    ]
    return tags.details(
        tags.summary(
            tags.div(pillar.name, class_="pillar-name"),
            score_view,
            tags.div(tags.div(class_="score-fill", style=f"width:{score or 0}%"), class_="score-track"),
            tags.div(pillar.question, class_="pillar-q"),
            tags.div(tags.span("Show the metrics ▾", class_="closed"), tags.span("Hide ▴", class_="opened"),
                     class_="pillar-more") if items else None,
        ),
        tags.ul(*items, class_="pillar-metrics") if items else None,
        class_="pillar",
    )


@module.server
def overview_server(input, output, session, ctx: StockContext):
    @reactive.calc
    def risk_5y():
        return risk.risk_report(ctx.prices(), ctx.benchmark_prices(), ctx.risk_free.value_or_none() or
                                config.RISK_FREE_FALLBACK, years=5)

    @render.ui
    def scorecard():
        if ctx.snapshot.result() is None:
            return c.skeleton(height=320)
        snap = ctx.snapshot.value()
        return tags.div(
            tags.div("Scorecard", class_="eyebrow"),
            tags.h2(f"How {snap.symbol} scores"),
            tags.p("Each pillar averages its metrics on a 0–100 scale using fixed rules of thumb, "
                   "not sector comparisons. Open a pillar to see exactly why. "
                   "For information only — not investment advice.", class_="micro"),
            tags.div(*[pillar_card(p, snap.is_financial) for p in ctx.pillars()], class_="pillars"),
            class_="c-dark",
        )

    @render.ui
    def kpis():
        snap = ctx.snapshot.value()
        m = ctx.metrics()
        symbol = snap.currency_symbol
        returns = performance.period_returns(ctx.prices())
        bench = ctx.benchmark_prices()
        bench_returns = performance.period_returns(bench) if bench is not None else {}
        report = risk_5y()
        drawdown = report.max_drawdown

        tiles = [
            c.kpi("1-year return", c.delta(returns["1Y"]),
                  f"{config.BENCHMARK_LABEL} {fmt.pct(bench_returns.get('1Y'), sign=True)}"),
            c.kpi("5-year CAGR", fmt.pct(returns["5Y"] and performance.annualize(returns["5Y"], 5 * 365.25)),
                  "per year, dividends reinvested", tone=fmt.tone(returns["5Y"])),
            c.kpi("Max drawdown (5Y)", fmt.pct(drawdown.depth if drawdown else None),
                  f"{fmt.day(drawdown.peak.date())} → {fmt.day(drawdown.trough.date())}" if drawdown else None,
                  help="Largest peak-to-trough fall in the period.", tone="down" if drawdown else None),
            c.kpi("Beta (5Y)", fmt.num(report.beta), f"vs {config.BENCHMARK_LABEL} · volatility {fmt.pct(report.volatility, 0)}",
                  help="1.0 moves with the market; above 1 swings more."),
        ]
        if snap.is_fund:
            tiles += [
                c.kpi("Dividend yield", fmt.pct(m["dividend_yield"], 2)),
                c.kpi("Sharpe ratio (5Y)", fmt.num(report.sharpe), "return per unit of risk"),
                c.kpi("YTD return", c.delta(returns["YTD"])),
                c.kpi("Trailing P/E", fmt.mult(m["trailing_pe"]), "of its holdings" if snap.quote_type == "ETF" else None),
            ]
        else:
            tiles += [
                c.kpi("Forward P/E", fmt.mult(m["forward_pe"]), f"Trailing {fmt.mult(m['trailing_pe'])}",
                      help="Price ÷ expected earnings over the next 12 months."),
                c.kpi("Price / book", fmt.mult(m["price_to_book"]), f"ROA {fmt.pct(m['roa'], 2)}")
                if snap.is_financial else
                c.kpi("Free cash flow yield", fmt.pct(m["fcf_yield"]), f"FCF {fmt.money(m['fcf'], snap.statement_symbol)} (TTM)",
                      help="Free cash flow ÷ market cap — the cash return if you owned the whole company."),
                c.kpi("Return on equity", fmt.pct(m["roe"]), f"Net margin {fmt.pct(m['net_margin'])}"),
                c.kpi("Dividend yield", fmt.pct(m["dividend_yield"], 2), f"Payout {fmt.pct(m['payout_ratio'], 0)}")
                if snap.is_financial else
                c.kpi("Net debt / EBITDA", fmt.mult(m["net_debt_ebitda"]),
                      "Net cash" if (m["net_debt_ebitda"] or 0) < 0 else f"Debt/equity {fmt.mult(m['debt_to_equity'])}",
                      help="Years of EBITDA needed to pay off debt net of cash."),
            ]
        return tags.div(*tiles, class_="grid grid-kpi")

    @render_plotly
    def growth():
        symbol = ctx.snapshot.value().major_symbol
        prices = performance.trailing(ctx.prices(), 5)
        lines = {ctx.symbol(): performance.rebase(prices, 10_000)}
        bench = ctx.benchmark_prices()
        if bench is not None:
            stock, bench = performance.align(prices, bench)
            lines = {ctx.symbol(): performance.rebase(stock, 10_000),
                     config.BENCHMARK_LABEL: performance.rebase(bench, 10_000)}
        return charts.growth_chart(lines, prefix=symbol)

    @render.ui
    def notes():
        snap = ctx.snapshot.value()
        m = ctx.metrics()
        notes: list[tuple[str, str]] = []

        high = snap.get("fiftyTwoWeekHigh")
        if high and snap.price:
            below = snap.price / high - 1
            if below > -0.03:
                notes.append(("up", "Trading near its 52-week high."))
            elif below < -0.15:
                notes.append(("down", f"{fmt.pct(-below, 0)} below its 52-week high."))
        if m.get("relative_1y") is not None:
            gap = m["relative_1y"]
            if abs(gap) < 0.01:
                notes.append(("flat", f"Kept pace with the {config.BENCHMARK_LABEL} over the past year."))
            else:
                verb = "Beat" if gap > 0 else "Lagged"
                notes.append((fmt.tone(gap), f"{verb} the {config.BENCHMARK_LABEL} by {abs(gap) * 100:.0f} "
                                             "percentage points over the past year."))
        if m.get("vs_sma200") is not None:
            gap = m["vs_sma200"]
            notes.append((fmt.tone(gap), f"Price is {fmt.pct(abs(gap), 0)} {'above' if gap > 0 else 'below'} "
                                         "its 200-day average."))
        if m.get("analyst_upside") is not None and m.get("analyst_count"):
            rating = str(snap.get("recommendationKey", "")).replace("_", " ")
            notes.append((fmt.tone(m["analyst_upside"]),
                          f"Analysts' mean target {fmt.price(m['analyst_target'], snap.currency_symbol)} implies "
                          f"{fmt.pct(m['analyst_upside'], 0, sign=True)} ({fmt.integer(m['analyst_count'])} analysts"
                          + (f", consensus “{rating}”" if rating and rating != "none" else "") + ")."))
        if m.get("forward_pe") and m.get("trailing_pe") and 0 < m["forward_pe"] < m["trailing_pe"] * 0.9:
            notes.append(("up", f"Earnings expected to grow: forward P/E {fmt.mult(m['forward_pe'])} vs "
                                f"trailing {fmt.mult(m['trailing_pe'])}."))
        if not snap.is_financial and (m.get("net_debt_ebitda") or 0) < 0:
            notes.append(("up", "Holds more cash than debt."))
        if (m.get("dividend_yield") or 0) >= 0.02:
            notes.append(("flat", f"Pays a {fmt.pct(m['dividend_yield'], 1)} dividend yield."))
        drawdown = risk_5y().max_drawdown
        if drawdown and drawdown.depth < -0.25:
            recovered = (f"recovered by {fmt.day(drawdown.recovery.date())}" if drawdown.recovery
                         else "not yet recovered")
            notes.append(("down", f"Worst fall in 5 years: {fmt.pct(drawdown.depth, 0)}, {recovered}."))
        if snap.next_earnings and date.today() <= snap.next_earnings <= date.today() + timedelta(days=30):
            notes.append(("flat", f"Reports earnings on {fmt.day(snap.next_earnings)}."))

        if not notes:
            return c.empty_state("Nothing unusual", "No standout signals in the latest data.")
        return tags.ul(*[tags.li(tags.span(class_=f"dot {tone}"), tags.span(text)) for tone, text in notes],
                       class_="notes")

    @render.ui
    def about():
        snap = ctx.snapshot.value()
        facts = [
            c.pill("Employees ", fmt.integer(snap.employees), variant="fog") if snap.employees else None,
            tags.a(snap.website.replace("https://", "").replace("http://", ""), href=snap.website,
                   target="_blank", rel="noopener", class_="pill pill-outline") if snap.website else None,
        ]
        return c.card(
            tags.p(snap.summary or "No company description available.", class_="about"),
            tags.div(*facts, class_="hero-meta"),
        )
