"""Plotly theme and figure builders using the roles in ``palette``.

The accent is used only for fills; lines and text use ink, secondary and the
neutrals so they stay readable on white.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from .palette import ROLES, rgba

INK = ROLES["ink"]
SECONDARY = ROLES["secondary"]
GAIN = ROLES["gain"]
LOSS = ROLES["loss"]
CHARCOAL = ROLES["charcoal"]
PEBBLE = ROLES["pebble"]
SLATE = ROLES["slate"]
FOG = ROLES["fog"]
FONT = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

STOCK_COLOR = INK
BENCH_COLOR = SECONDARY

pio.templates["compass"] = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, color=CHARCOAL, size=13),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    colorway=[INK, SECONDARY, ROLES["accent"], PEBBLE, SLATE, LOSS],
    margin=dict(l=8, r=8, t=8, b=8),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(family=FONT, color="#ffffff", size=12)),
    legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                font=dict(size=12), title=None),
    xaxis=dict(showgrid=False, linecolor=FOG, ticks="", zeroline=False, automargin=True,
               tickfont=dict(color=SLATE)),
    yaxis=dict(gridcolor=FOG, zeroline=False, ticks="", automargin=True, tickfont=dict(color=SLATE),
               side="right"),
    bargap=0.25,
))
pio.templates.default = "compass"


def _finish(fig: go.Figure, height: int = 340, **layout) -> go.Figure:
    fig.update_layout(height=height, template="compass", **layout)
    # shinywidgets serializes with strict JSON, which rejects NaN; Plotly's encoder turns NaN into null
    return go.Figure(json.loads(fig.to_json()))


def empty_figure(message: str, height: int = 280) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=SLATE, size=14),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _finish(fig, height)


def downsample(series: pd.Series, max_points: int = 2500) -> pd.Series:
    """Weekly points for long histories keep charts light without changing their shape."""
    if len(series) <= max_points:
        return series
    return series.resample("W").last().dropna()


def growth_chart(lines: dict[str, pd.Series], prefix: str = "$", height: int = 340) -> go.Figure:
    """Value-over-time lines; the first series is the stock and gets a soft area fill."""
    fig = go.Figure()
    for i, (label, series) in enumerate(lines.items()):
        series = downsample(series)
        is_stock = i == 0
        fig.add_trace(go.Scatter(
            x=series.index, y=series.values, name=label, mode="lines",
            line=dict(color=STOCK_COLOR if is_stock else BENCH_COLOR, width=2.5 if is_stock else 1.8),
            fill="tozeroy" if is_stock else None,
            fillcolor=rgba("accent", 0.14) if is_stock else None,
            hovertemplate=f"{prefix}%{{y:,.0f}}<extra>{label}</extra>",
        ))
    values = pd.concat(lines.values())
    low, high = values.min(), values.max()
    fig.update_yaxes(tickprefix=prefix, range=[low - (high - low) * 0.05, high + (high - low) * 0.05])
    return _finish(fig, height)


def drawdown_chart(lines: dict[str, pd.Series], height: int = 260) -> go.Figure:
    fig = go.Figure()
    for i, (label, series) in enumerate(lines.items()):
        series = downsample(series)
        is_stock = i == 0
        fig.add_trace(go.Scatter(
            x=series.index, y=series.values, name=label, mode="lines",
            line=dict(color=LOSS if is_stock else BENCH_COLOR, width=1.6 if is_stock else 1.2),
            fill="tozeroy" if is_stock else None,
            fillcolor=rgba("loss", 0.12) if is_stock else None,
            hovertemplate="%{y:.1%}<extra>" + label + "</extra>",
        ))
    deepest = min(float(s.min()) for s in lines.values()) if lines else -0.1
    fig.update_yaxes(tickformat=".0%", range=[deepest * 1.08, 0.01])
    return _finish(fig, height)


def calendar_bars(stock: pd.Series, benchmark: pd.Series | None, stock_label: str,
                  bench_label: str, height: int = 300) -> go.Figure:
    fig = go.Figure()
    current_year = pd.Timestamp.today().year
    years = ["YTD" if y == current_year else str(y) for y in stock.index]
    fig.add_trace(go.Bar(
        x=years, y=stock.values, name=stock_label,
        marker=dict(color=[GAIN if v >= 0 else LOSS for v in stock.values]),
        hovertemplate="%{y:+.1%}<extra>" + stock_label + "</extra>",
        showlegend=False,  # bars are colored by sign, so a single legend swatch would mislead
    ))
    if benchmark is not None:
        bench = benchmark.reindex(stock.index)
        fig.add_trace(go.Scatter(
            x=years, y=bench.values, name=bench_label, mode="markers",
            marker=dict(color=BENCH_COLOR, size=9, symbol="line-ew", line=dict(width=3, color=BENCH_COLOR)),
            hovertemplate="%{y:+.1%}<extra>" + bench_label + "</extra>",
        ))
    fig.update_yaxes(tickformat=".0%", zeroline=True, zerolinecolor=PEBBLE, zerolinewidth=1)
    fig.update_xaxes(type="category")
    return _finish(fig, height)


def monthly_heatmap(table: pd.DataFrame, height: int | None = None) -> go.Figure:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    table = table.sort_index(ascending=False)
    values = table.values.astype(float)
    limit = np.nanpercentile(np.abs(values), 95) if np.isfinite(values).any() else 0.1
    text = [[("" if np.isnan(v) else f"{v * 100:+.1f}") for v in row] for row in values]
    fig = go.Figure(go.Heatmap(
        z=values, x=months, y=[str(y) for y in table.index],
        zmin=-limit, zmax=limit,
        colorscale=[[0, LOSS], [0.5, "#f5f6fa"], [1, GAIN]],
        text=text, texttemplate="%{text}", textfont=dict(size=11),
        hovertemplate="%{x} %{y}: %{z:+.1%}<extra></extra>",
        showscale=False, xgap=2, ygap=2,
    ))
    fig.update_yaxes(type="category", side="left", showgrid=False)
    fig.update_xaxes(side="top")
    return _finish(fig, height or max(220, 28 * len(table) + 60), hovermode="closest")


INK_2 = ROLES["ink-2"]


def money_scale(*arrays) -> tuple[float, str]:
    """Divisor and suffix so money axes read $120B rather than d3's $120G."""
    values = [abs(float(v)) for array in arrays for v in array if pd.notna(v)]
    peak = max(values) if values else 0
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if peak >= limit:
            return limit, suffix
    return 1.0, ""


def money_hover(prefix: str, suffix: str, label: str) -> str:
    return f"{prefix}%{{y:,.1f}}{suffix}<extra>{label}</extra>"


def multiple_history(series: pd.Series, label: str, median: float | None, height: int = 300) -> go.Figure:
    """A valuation multiple over time with its median and full range for context."""
    fig = go.Figure()
    if median is not None and len(series):
        fig.add_hrect(y0=float(series.min()), y1=float(series.max()), fillcolor=rgba("secondary", 0.07),
                      line_width=0, layer="below")
        fig.add_hline(y=median, line=dict(color=SECONDARY, width=1.2, dash="dash"),
                      annotation_text=f"median {median:.1f}", annotation_position="top left",
                      annotation_font=dict(color=SLATE, size=11))
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name=label, mode="lines+markers",
                             line=dict(color=INK, width=2.2), marker=dict(size=5, color=INK),
                             hovertemplate="%{y:.1f}<extra>" + label + "</extra>"))
    fig.update_layout(showlegend=False)
    return _finish(fig, height)


def statement_bars(frame: pd.DataFrame, prefix: str = "$", height: int = 320) -> go.Figure:
    """Grouped bars per fiscal year (e.g. revenue, net income, free cash flow)."""
    fig = go.Figure()
    colors = [INK, SECONDARY, SLATE, INK_2]
    years = [f"FY{d.year}" for d in frame.index]
    divisor, suffix = money_scale(frame.values.ravel())
    for color, column in zip(colors, frame.columns):
        fig.add_trace(go.Bar(x=years, y=frame[column].values / divisor, name=column, marker_color=color,
                             hovertemplate=money_hover(prefix, suffix, column)))
    fig.update_yaxes(tickprefix=prefix, ticksuffix=suffix)
    fig.update_layout(barmode="group", hovermode="x unified")
    return _finish(fig, height)


def margin_lines(frame: pd.DataFrame, height: int = 320) -> go.Figure:
    fig = go.Figure()
    styles = {"Gross": (INK, "solid"), "Operating": (INK_2, "solid"), "Net": (SECONDARY, "solid"),
              "Free cash flow": (SLATE, "dot")}
    years = [f"FY{d.year}" for d in frame.index]
    for column in frame.columns:
        color, dash = styles.get(column, (PEBBLE, "solid"))
        series = frame[column]
        fig.add_trace(go.Scatter(x=years, y=series.values, name=column, mode="lines+markers",
                                 line=dict(color=color, width=2, dash=dash), marker=dict(size=6),
                                 hovertemplate="%{y:.1%}<extra>" + column + "</extra>"))
        last = series.dropna()
        if not last.empty:
            # Label each line at its end so similar hues are never ambiguous
            fig.add_annotation(x=years[frame.index.get_loc(last.index[-1])], y=float(last.iloc[-1]),
                               text=f"{column} {last.iloc[-1] * 100:.0f}%", showarrow=False, xanchor="left",
                               xshift=10, font=dict(color=color, size=12))
    fig.update_yaxes(tickformat=".0%", side="left")
    fig.update_xaxes(type="category")
    return _finish(fig, height, showlegend=False, margin=dict(l=8, r=120, t=8, b=8))


def stacked_payouts(frame: pd.DataFrame, prefix: str = "$", height: int = 300) -> go.Figure:
    fig = go.Figure()
    years = [f"FY{d.year}" for d in frame.index]
    divisor, suffix = money_scale(frame.sum(axis=1).values, frame.values.ravel())
    for color, column in zip([INK, SECONDARY], frame.columns):
        fig.add_trace(go.Bar(x=years, y=frame[column].values / divisor, name=column, marker_color=color,
                             hovertemplate=money_hover(prefix, suffix, column)))
    fig.update_yaxes(tickprefix=prefix, ticksuffix=suffix)
    fig.update_layout(barmode="relative")
    return _finish(fig, height)


def dividend_bars(by_year: pd.Series, prefix: str = "$", height: int = 300) -> go.Figure:
    fig = go.Figure(go.Bar(x=[str(y) for y in by_year.index], y=by_year.values, marker_color=INK,
                           hovertemplate=f"{prefix}%{{y:.2f}} per share<extra></extra>"))
    fig.update_yaxes(tickprefix=prefix)
    fig.update_xaxes(type="category")
    return _finish(fig, height, hovermode="closest")


def dcf_bars(years: list[int], cash_flows: list[float], present_values: list[float],
             prefix: str = "$", height: int = 280) -> go.Figure:
    labels = [f"Y{y}" for y in years]
    divisor, suffix = money_scale(cash_flows)
    fig = go.Figure([
        go.Bar(x=labels, y=[v / divisor for v in cash_flows], name="Projected free cash flow",
               marker_color=rgba("secondary", 0.45), hovertemplate=money_hover(prefix, suffix, "Projected")),
        go.Bar(x=labels, y=[v / divisor for v in present_values], name="Worth today (discounted)",
               marker_color=INK, hovertemplate=money_hover(prefix, suffix, "Present value")),
    ])
    fig.update_yaxes(tickprefix=prefix, ticksuffix=suffix)
    fig.update_layout(barmode="overlay", bargap=0.35)
    return _finish(fig, height)
