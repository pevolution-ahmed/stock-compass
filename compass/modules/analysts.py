"""Analysts & Ownership tab: estimates and revisions, earnings surprises, ratings, holders and insiders."""

from __future__ import annotations

import pandas as pd
from htmltools import tags
from shiny import module, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

from ..analytics import sentiment
from ..data.schemas import ESTIMATE_PERIODS
from ..state import StockContext
from ..ui import charts
from ..ui import components as c
from ..ui import formatting as fmt

def insider_kind(text: str) -> str:
    """Short label for Yahoo's free-text insider transaction description."""
    lowered = text.lower()
    for needle, label in (("sale", "Sale"), ("purchase", "Purchase"), ("award", "Grant"), ("grant", "Grant"),
                          ("option", "Option exercise"), ("exercise", "Option exercise"), ("gift", "Gift"),
                          ("conversion", "Conversion")):
        if needle in lowered:
            return label
    return "Other filing"


ACTIONS = {"up": ("Upgrade", "soft"), "down": ("Downgrade", "outline"), "init": ("Initiated", "fog"),
           "main": ("Maintained", "fog"), "reit": ("Reiterated", "fog")}


@module.ui
def analysts_ui():
    return tags.div(
        ui.output_ui("not_applicable"),
        ui.panel_conditional(
            "output.applicable === 'yes'",
            c.section("Earnings outlook", ui.output_ui("outlook_kpis"),
                      c.card(ui.output_ui("estimates_table"), title="Consensus estimates",
                             subtitle="Average of analysts' forecasts, with the range and growth vs a year earlier",
                             class_="mt-3"),
                      subtitle="What analysts expect — and whether those expectations are rising or falling."),
            tags.section(
                tags.div(
                    c.card(output_widget("estimate_trend", height="300px"), title="How estimates have moved",
                           subtitle="Consensus EPS for this and next fiscal year over the last 90 days"),
                    c.card(output_widget("surprises", height="300px"), title="Earnings surprises",
                           subtitle="Reported EPS (dot) vs the estimate going in (ring); green = beat"),
                    class_="grid grid-2",
                ),
                class_="section",
            ),
            c.section("Analyst ratings",
                      tags.div(
                          c.card(output_widget("ratings", height="300px"), title="Rating mix",
                                 subtitle="Number of analysts at each rating, last four months"),
                          c.card(ui.output_ui("rating_summary"), title="Summary"),
                          class_="grid grid-3-1",
                      ),
                      c.card(ui.output_ui("grades"), title="Recent rating changes", class_="mt-3")),
            c.section("Ownership", ui.output_ui("ownership_kpis"),
                      tags.div(
                          c.card(ui.output_ui("institutions"), title="Largest institutional holders"),
                          c.card(ui.output_ui("insiders"), title="Recent insider transactions",
                                 subtitle="Officers' and directors' filings"),
                          class_="grid grid-2 mt-3",
                      ),
                      subtitle="Who owns the shares, and whether insiders are buying or selling."),
        ),
        class_="page",
    )


@module.server
def analysts_server(input, output, session, ctx: StockContext):
    @reactive.calc
    def insights():
        value = ctx.insights.value()
        req(not value.empty)
        return value

    @output(suspend_when_hidden=False)
    @render.text
    def applicable():
        value = ctx.insights.value_or_none()
        return "yes" if value is not None and not value.empty else "no"

    @render.ui
    def not_applicable():
        result = ctx.insights.result()
        if result is None:
            return tags.section(c.skeleton(height=320), class_="section")
        if result.value is None or result.value.empty:
            snap = ctx.snapshot.value_or_none()
            if snap is not None and snap.is_fund:
                return tags.section(c.empty_state("Funds have no analyst estimates",
                                                  "Analyst coverage applies to individual companies."), class_="section")
            return tags.section(c.empty_state("No analyst coverage", result.error or
                                              "Yahoo has no estimates or ratings for this symbol."), class_="section")
        return None

    @render.ui
    def outlook_kpis():
        m = ctx.metrics()
        data = insights()
        breadth = sentiment.revision_breadth(data)
        surprises = sentiment.surprise_stats(data)
        return tags.div(
            c.kpi("Expected EPS growth", fmt.pct(m.get("fwd_eps_growth")), "next fiscal year vs this one",
                  tone=fmt.tone(m.get("fwd_eps_growth"))),
            c.kpi("Estimate change (90 days)", c.delta(m.get("eps_revision_90d")), "this fiscal year's consensus EPS",
                  help="Rising estimates often lead share prices; falling ones are a warning sign."),
            c.kpi("Revisions (30 days)", f"{breadth[0]} up · {breadth[1]} down" if breadth else "—",
                  "analysts changing this or next year's EPS"),
            c.kpi("Beat rate", fmt.pct(surprises.beat_rate if surprises else None, 0),
                  f"last {surprises.quarters} quarters · avg surprise {fmt.pct(surprises.average_surprise, 1, sign=True)}"
                  if surprises else None),
            class_="grid grid-kpi",
        )

    @render.ui
    def estimates_table():
        est = insights().estimates
        symbol = ctx.snapshot.value().currency_symbol
        rows = []
        for period, label in ESTIMATE_PERIODS.items():
            if period not in est.index:
                continue
            r = est.loc[period]
            ends = f"ends {r['end']:%b %Y}" if pd.notna(r.get("end")) and r.get("end") else ""
            rows.append([
                tags.div(tags.div(label, class_="strong"), tags.div(ends, class_="micro muted")),
                tags.div(fmt.price(r["eps_avg"], symbol),
                         tags.div(f"{fmt.price(r['eps_low'], symbol)} – {fmt.price(r['eps_high'], symbol)}",
                                  class_="micro muted")),
                c.delta(r["eps_growth"]),
                tags.div(fmt.money(r["rev_avg"], symbol),
                         tags.div(f"{fmt.money(r['rev_low'], symbol)} – {fmt.money(r['rev_high'], symbol)}",
                                  class_="micro muted")),
                c.delta(r["rev_growth"]),
                fmt.integer(r["eps_analysts"]),
            ])
        return c.table(["Period", "EPS estimate", "EPS growth", "Revenue estimate", "Revenue growth", "Analysts"],
                       rows)

    @render_plotly
    def estimate_trend():
        return charts.estimate_trend(insights().estimates, ESTIMATE_PERIODS)

    @render_plotly
    def surprises():
        data = insights().surprises
        return charts.surprise_chart(data) if not data.empty else charts.empty_figure("No reported quarters")

    @render_plotly
    def ratings():
        data = insights().recommendations
        return charts.rating_trend(data) if not data.empty else charts.empty_figure("No ratings")

    @render.ui
    def rating_summary():
        data = insights()
        m = ctx.metrics()
        ratings = sentiment.current_ratings(data)
        raised, lowered = sentiment.recent_target_changes(data)
        total = int(ratings.sum()) if ratings is not None else 0
        return tags.div(
            c.kpi("Rate it Buy or better", fmt.pct(m.get("bullish_share"), 0), f"of {total} analysts this month"),
            c.kpi("Price targets (90 days)", f"{raised} raised · {lowered} cut",
                  tone="up" if raised > lowered else "down" if lowered > raised else None),
            class_="grid", style="grid-template-columns:1fr",
        )

    @render.ui
    def grades():
        data = insights().grades.head(12)
        if data.empty:
            return c.empty_state("No recent rating changes")
        symbol = ctx.snapshot.value().currency_symbol
        rows = []
        for _, g in data.iterrows():
            label, variant = ACTIONS.get(str(g["action"]), (str(g["action"]).title(), "fog"))
            rating = g["to"] if g["from"] in (None, "", g["to"]) or pd.isna(g["from"]) else f"{g['from']} → {g['to']}"
            target = "—"
            if pd.notna(g.get("target")) and g.get("target"):
                change = (g["target"] / g["prior_target"] - 1) if pd.notna(g.get("prior_target")) and g["prior_target"] else None
                target = tags.span(fmt.price(g["target"], symbol), " ",
                                   c.delta(change) if change else None)
            rows.append([fmt.day(g["date"].date()) if pd.notna(g["date"]) else "—", g["firm"],
                         c.pill(label, variant=variant), rating, target])
        return c.table(["Date", "Firm", "Action", "Rating", "Price target"], rows, align="lllll")

    @render.ui
    def ownership_kpis():
        data = insights()
        snap = ctx.snapshot.value()
        holders, net = data.holders, data.insider_summary
        bought, sold = net.get("buyInfoShares"), net.get("sellInfoShares")
        net_shares = net.get("netInfoShares")
        return tags.div(
            c.kpi("Held by institutions", fmt.pct(holders.get("institutionsPercentHeld"), 1),
                  f"{fmt.integer(holders.get('institutionsCount'))} institutions"),
            c.kpi("Held by insiders", fmt.pct(holders.get("insidersPercentHeld"), 2), "officers and directors"),
            c.kpi("Insider activity (6 months)",
                  c.delta(net_shares, lambda v: f"{fmt.count(abs(v))} net {'bought' if v > 0 else 'sold'}")
                  if net_shares else "—",
                  f"{fmt.count(bought)} bought · {fmt.count(sold)} sold (shares)",
                  help="Includes grants and option exercises, so 'bought' isn't always open-market buying."),
            c.kpi("Short interest", fmt.pct(snap.get("shortPercentOfFloat"), 2),
                  f"{fmt.num(snap.get('shortRatio'), 1)} days to cover",
                  help="Share of tradable shares sold short; high values mean many investors bet on a fall."),
            class_="grid grid-kpi",
        )

    @render.ui
    def institutions():
        data = insights().institutions
        if data.empty:
            return c.empty_state("No institutional holder data")
        symbol = ctx.snapshot.value().currency_symbol
        rows = [[r["holder"], fmt.pct(r["pct_held"], 2), fmt.money(r["value"], symbol), c.delta(r["pct_change"])]
                for _, r in data.iterrows()]  # holder names wrap; numbers stay right-aligned
        return c.table(["Holder", "Stake", "Value", "Change"], rows)

    @render.ui
    def insiders():
        data = insights().insider_trades.head(10)
        if data.empty:
            return c.empty_state("No recent insider filings")
        symbol = ctx.snapshot.value().currency_symbol
        rows = []
        for _, r in data.iterrows():
            kind = insider_kind(str(r["text"] or ""))
            rows.append([
                fmt.day(r["date"].date()) if pd.notna(r["date"]) else "—",
                tags.div(str(r["name"]).title(), tags.div(r["relation"], class_="micro muted")),
                c.pill(kind, variant="outline" if kind == "Sale" else "soft" if kind == "Purchase" else "fog"),
                fmt.count(r["shares"]),
                fmt.money(r["value"], symbol) if r["value"] else "—",
            ])
        return c.table(["Date", "Insider", "Type", "Shares", "Value"], rows, align="llrrr")
