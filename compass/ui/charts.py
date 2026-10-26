"""Plotly theme and figure builders in the DESIGN.md palette.

Lime is used only for fills; lines and text use Forest Ink, Signal Blue and the
neutrals so they stay readable on white.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

FOREST = "#163300"
LIME = "#9fe870"
SPRUCE = "#054d28"
LINEN = "#e2f6d5"
SIGNAL_BLUE = "#0b4c72"
ALARM = "#cb272f"
CHARCOAL = "#454745"
PEBBLE = "#868685"
SLATE = "#6a6c6a"
FOG = "#e8ebe6"
FONT = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

STOCK_COLOR = FOREST
BENCH_COLOR = SIGNAL_BLUE

pio.templates["compass"] = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, color=CHARCOAL, size=13),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    colorway=[FOREST, SIGNAL_BLUE, SPRUCE, PEBBLE, SLATE, ALARM],
    margin=dict(l=8, r=8, t=8, b=8),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=FOREST, bordercolor=FOREST, font=dict(family=FONT, color="#ffffff", size=12)),
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
            fillcolor="rgba(159, 232, 112, 0.18)" if is_stock else None,
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
            line=dict(color=ALARM if is_stock else BENCH_COLOR, width=1.6 if is_stock else 1.2),
            fill="tozeroy" if is_stock else None,
            fillcolor="rgba(203, 39, 47, 0.12)" if is_stock else None,
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
        marker=dict(color=[SPRUCE if v >= 0 else ALARM for v in stock.values]),
        hovertemplate="%{y:+.1%}<extra>" + stock_label + "</extra>",
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
        colorscale=[[0, ALARM], [0.5, "#f4f6f3"], [1, SPRUCE]],
        text=text, texttemplate="%{text}", textfont=dict(size=11),
        hovertemplate="%{x} %{y}: %{z:+.1%}<extra></extra>",
        showscale=False, xgap=2, ygap=2,
    ))
    fig.update_yaxes(type="category", side="left", showgrid=False)
    fig.update_xaxes(side="top")
    return _finish(fig, height or max(220, 28 * len(table) + 60), hovermode="closest")
