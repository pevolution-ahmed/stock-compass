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

from .palette import DARK_ROLES, ROLES, rgba, to_dark

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
    hoverlabel=dict(bgcolor=ROLES["feature"], bordercolor=ROLES["feature"],
                    font=dict(family=FONT, color=ROLES["on-feature"], size=12)),
    legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                font=dict(size=12), title=None),
    xaxis=dict(showgrid=False, linecolor=FOG, ticks="", zeroline=False, automargin=True,
               tickfont=dict(color=SLATE)),
    yaxis=dict(gridcolor=FOG, zeroline=False, ticks="", automargin=True, tickfont=dict(color=SLATE),
               side="right"),
    bargap=0.25,
))
pio.templates.default = "compass"


def session_mode() -> str:
    """The visitor's light/dark choice (a reactive read, so charts redraw when it changes)."""
    from shiny.session import get_current_session

    session = get_current_session()
    if session is None:
        return "light"
    root = session.root_scope()
    return "dark" if "theme" in root.input and root.input["theme"]() == "dark" else "light"


def _finish(fig: go.Figure, height: int = 340, **layout) -> go.Figure:
    fig.update_layout(height=height, template="compass", **layout)
    # shinywidgets serializes with strict JSON, which rejects NaN; Plotly's encoder turns NaN into null
    text = fig.to_json()
    if session_mode() == "dark":
        text = to_dark(text)
        figure = go.Figure(json.loads(text))
        figure.update_layout(hoverlabel=dict(bgcolor=DARK_ROLES["feature"], bordercolor=DARK_ROLES["feature"],
                                             font_color=DARK_ROLES["on-feature"]))
        return figure
    return go.Figure(json.loads(text))


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
        colorscale=[[0, LOSS], [0.5, FOG], [1, GAIN]],
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
                               xshift=8, font=dict(color=color, size=11))
    fig.update_yaxes(tickformat=".0%", side="left")
    fig.update_xaxes(type="category")
    return _finish(fig, height, showlegend=False, margin=dict(l=8, r=104, t=8, b=8))


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


# ---------- Analysts ----------

RATING_COLORS = {"Strong buy": GAIN, "Buy": rgba("gain", 0.55), "Hold": PEBBLE,
                 "Sell": rgba("loss", 0.55), "Strong sell": LOSS}
MONTHS_AGO = {"0m": "This month", "-1m": "1 month ago", "-2m": "2 months ago", "-3m": "3 months ago"}


def rating_trend(recommendations: pd.DataFrame, height: int = 300) -> go.Figure:
    frame = recommendations.reindex([p for p in MONTHS_AGO if p in recommendations.index][::-1])
    labels = [MONTHS_AGO[p] for p in frame.index]
    fig = go.Figure([
        go.Bar(x=labels, y=frame[column].values, name=column, marker_color=color,
               hovertemplate="%{y} analysts<extra>" + column + "</extra>")
        for column, color in RATING_COLORS.items() if column in frame
    ])
    fig.update_layout(barmode="stack", legend=dict(traceorder="normal"))
    fig.update_xaxes(type="category")
    return _finish(fig, height)


def surprise_chart(surprises: pd.DataFrame, height: int = 300) -> go.Figure:
    labels = [f"Q{(d.month - 1) // 3 + 1} {d.year}" for d in surprises.index]
    beat = surprises["actual"] >= surprises["estimate"]
    fig = go.Figure([
        go.Scatter(x=labels, y=surprises["estimate"], name="Estimate", mode="markers",
                   marker=dict(size=16, color="rgba(0,0,0,0)", line=dict(color=SECONDARY, width=2)),
                   hovertemplate="$%{y:.2f}<extra>Estimate</extra>"),
        go.Scatter(x=labels, y=surprises["actual"], name="Actual", mode="markers",
                   marker=dict(size=12, color=[GAIN if b else LOSS for b in beat]),
                   customdata=surprises["surprise"].fillna(0).values,
                   hovertemplate="$%{y:.2f} (%{customdata:+.1%})<extra>Actual</extra>"),
    ])
    fig.update_yaxes(tickprefix="$")
    fig.update_xaxes(type="category")
    return _finish(fig, height)


def estimate_trend(estimates: pd.DataFrame, labels: dict, height: int = 300) -> go.Figure:
    points = [("90 days ago", "trend_90d"), ("60 days ago", "trend_60d"), ("30 days ago", "trend_30d"),
              ("7 days ago", "trend_7d"), ("Today", "trend_current")]
    fig = go.Figure()
    for period, color in (("0y", INK), ("+1y", SECONDARY)):
        if period not in estimates.index:
            continue
        values = [estimates.at[period, column] for _, column in points]
        fig.add_trace(go.Scatter(x=[x for x, _ in points], y=values, name=labels[period], mode="lines+markers",
                                 line=dict(color=color, width=2.2), marker=dict(size=7),
                                 hovertemplate="$%{y:.2f}<extra>" + labels[period] + "</extra>"))
    fig.update_yaxes(tickprefix="$")
    fig.update_xaxes(type="category")
    return _finish(fig, height)


# ---------- Technicals ----------

def price_chart(df: pd.DataFrame, overlay: str, height: int = 460) -> go.Figure:
    """Candlesticks with an indicator overlay and volume underneath."""
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Price",
        increasing=dict(line=dict(color=GAIN, width=1), fillcolor=GAIN),
        decreasing=dict(line=dict(color=LOSS, width=1), fillcolor=LOSS),
    ), row=1, col=1)

    def line(column, name, color, width=1.6, dash="solid"):
        return go.Scatter(x=df.index, y=df[column], name=name, mode="lines",
                          line=dict(color=color, width=width, dash=dash),
                          hovertemplate="%{y:.2f}<extra>" + name + "</extra>")

    if overlay == "ma":
        fig.add_trace(line("sma50", "50-day average", SECONDARY), row=1, col=1)
        fig.add_trace(line("sma200", "200-day average", INK, 2), row=1, col=1)
    elif overlay == "bollinger":
        fig.add_trace(line("upper_band", "Upper band", SECONDARY, 1), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["lower_band"], name="Lower band", mode="lines",
                                 line=dict(color=SECONDARY, width=1), fill="tonexty",
                                 fillcolor=rgba("secondary", 0.10),
                                 hovertemplate="%{y:.2f}<extra>Lower band</extra>"), row=1, col=1)
        fig.add_trace(line("middle_band", "20-day average", INK, 1.2, "dot"), row=1, col=1)
    elif overlay == "ichimoku":
        # Cloud between Span A and B: green while A is above B, red otherwise
        label = (df["SpanA"] > df["SpanB"]).astype(int)
        groups = label.ne(label.shift()).cumsum()
        for _, segment in df.groupby(groups):
            bullish = bool((segment["SpanA"] > segment["SpanB"]).iloc[0])
            fig.add_trace(go.Scatter(x=segment.index, y=segment["SpanA"], mode="lines", line=dict(width=0),
                                     showlegend=False, hoverinfo="skip"), row=1, col=1)
            fig.add_trace(go.Scatter(x=segment.index, y=segment["SpanB"], mode="lines", line=dict(width=0),
                                     fill="tonexty", fillcolor=rgba("gain" if bullish else "loss", 0.18),
                                     showlegend=False, hoverinfo="skip"), row=1, col=1)
        fig.add_trace(line("Conversion", "Conversion line", SECONDARY, 1.2), row=1, col=1)
        fig.add_trace(line("Baseline", "Base line", INK, 1.6), row=1, col=1)
        fig.add_trace(line("Lagging", "Lagging span", SLATE, 1, "dot"), row=1, col=1)

    up = df["close"] >= df["open"]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="Volume", showlegend=False,
                         marker_color=[rgba("gain", 0.5) if u else rgba("loss", 0.5) for u in up],
                         hovertemplate="%{y:,.0f}<extra>Volume</extra>"), row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False, rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(tickformat="~s", row=2, col=1)
    return _finish(fig, height)


def rsi_chart(rsi: pd.Series, height: int = 200) -> go.Figure:
    fig = go.Figure(go.Scatter(x=rsi.index, y=rsi.values, mode="lines", name="RSI (14)",
                               line=dict(color=INK, width=1.6), hovertemplate="%{y:.0f}<extra>RSI</extra>"))
    fig.add_hrect(y0=70, y1=100, fillcolor=rgba("loss", 0.07), line_width=0, layer="below")
    fig.add_hrect(y0=0, y1=30, fillcolor=rgba("gain", 0.07), line_width=0, layer="below")
    for level in (30, 70):
        fig.add_hline(y=level, line=dict(color=PEBBLE, width=1, dash="dot"))
    fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70])
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return _finish(fig, height, showlegend=False)


def macd_chart(macd: pd.DataFrame, height: int = 220) -> go.Figure:
    hist = macd["histogram"]
    colors = [rgba("gain", 0.55) if v >= 0 else rgba("loss", 0.55) for v in hist.fillna(0)]
    fig = go.Figure([
        go.Bar(x=macd.index, y=hist, name="Histogram", marker_color=colors,
               hovertemplate="%{y:.2f}<extra>Histogram</extra>"),
        go.Scatter(x=macd.index, y=macd["macd"], name="MACD", mode="lines", line=dict(color=INK, width=1.6),
                   hovertemplate="%{y:.2f}<extra>MACD</extra>"),
        go.Scatter(x=macd.index, y=macd["signal"], name="Signal", mode="lines",
                   line=dict(color=SECONDARY, width=1.4, dash="dot"), hovertemplate="%{y:.2f}<extra>Signal</extra>"),
    ])
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return _finish(fig, height)


# ---------- Watchlist ----------

SERIES_STYLES = [(INK, "solid"), (SECONDARY, "solid"), (INK_2, "solid"), (SLATE, "solid"), (GAIN, "solid"),
                 (INK, "dot"), (SECONDARY, "dot"), (INK_2, "dot"), (SLATE, "dot"), (GAIN, "dot"),
                 (PEBBLE, "solid"), (PEBBLE, "dot")]


def spread_labels(values: list[float], min_gap: float) -> list[float]:
    """Nudge end-of-line label positions apart so none overlap (keeps their order)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = [0.0] * len(values)
    previous = None
    for i in order:
        y = values[i] if previous is None else max(values[i], previous + min_gap)
        placed[i] = previous = y
    return placed


def comparison_chart(lines: dict, height: int = 380) -> go.Figure:
    """Total return since the period start for several series, each labeled at its end."""
    fig = go.Figure()
    styled = list(zip(lines.items(), SERIES_STYLES))
    finals = []
    for (label, series), (color, dash) in styled:
        series = downsample(series) / 100 - 1  # rebased-to-100 input → return since start
        finals.append((label, series.index[-1], float(series.iloc[-1]), color))
        fig.add_trace(go.Scatter(x=series.index, y=series.values, name=label, mode="lines",
                                 line=dict(color=color, width=2, dash=dash),
                                 hovertemplate="%{y:+.1%}<extra>" + label + "</extra>"))
    if finals:
        values = [v for _, _, v, _ in finals]
        all_y = pd.concat([trace_y for trace_y in (pd.Series(t.y) for t in fig.data)])
        gap = (float(all_y.max()) - float(all_y.min())) * 0.045 or 0.01
        for (label, x, value, color), y in zip(finals, spread_labels(values, gap)):
            fig.add_annotation(x=x, y=y, text=f"{label} {value * 100:+.0f}%", showarrow=False, xanchor="left",
                               xshift=8, font=dict(color=color, size=11))
    fig.add_hline(y=0, line=dict(color=PEBBLE, width=1, dash="dot"))
    fig.update_yaxes(side="left", tickformat="+.0%")
    if finals:  # pin the axis to the data; annotations must not stretch it
        start = min(trace.x[0] for trace in fig.data)
        fig.update_xaxes(range=[start, max(x for _, x, _, _ in finals)])
    return _finish(fig, height, showlegend=False, margin=dict(l=8, r=104, t=8, b=8))
