"""Reusable, stateless UI pieces styled by www/css/app.css."""

from __future__ import annotations

from typing import Callable, Iterable

from htmltools import Tag, TagChild, tags

from . import formatting as fmt

ARROWS = {"up": "▲", "down": "▼", "flat": ""}


def delta(value, formatter: Callable = None, chip: bool = False, suffix: str = "",
          arrow: bool = True) -> Tag:
    """Signed change with a gain/loss color and an arrow, so color is never the only cue."""
    formatter = formatter or (lambda v: fmt.pct(v, sign=True))
    direction = fmt.tone(value)
    classes = f"delta {direction}" + (" delta-chip" if chip else "")
    arrow = ARROWS[direction] if arrow else ""
    return tags.span(f"{arrow} " if arrow else "", formatter(value), suffix, class_=classes)


def pill(*children: TagChild, variant: str = "soft", **attrs) -> Tag:
    return tags.span(*children, class_=f"pill pill-{variant}", **attrs)


def pick_pill(symbol: str) -> Tag:
    """Pill that opens a ticker via the search module's JS bridge."""
    return tags.button(symbol, type="button", class_="pill pill-outline", data_pick_symbol=symbol)


def info(text: str) -> Tag:
    return tags.span("i", class_="info-tip", title=text, aria_label=text, role="img")


def kpi(label: str, value: TagChild, sub: TagChild = None, help: str | None = None,
        tone: str | None = None) -> Tag:
    return tags.div(
        tags.div(label, info(help) if help else None, class_="kpi-label"),
        tags.div(value, class_="kpi-value"),
        tags.div(sub, class_="kpi-sub") if sub is not None else None,
        class_=f"kpi {tone or ''}",
    )


def section(title: str, *children: TagChild, subtitle: str | None = None,
            actions: TagChild = None, id: str | None = None) -> Tag:
    return tags.section(
        tags.div(
            tags.div(tags.h2(title, class_="section-title"),
                     tags.p(subtitle, class_="section-sub") if subtitle else None),
            tags.div(actions) if actions is not None else None,
            class_="section-head",
        ),
        *children,
        class_="section",
        id=id,
    )


def card(*children: TagChild, title: str | None = None, subtitle: str | None = None,
         actions: TagChild = None, class_: str = "") -> Tag:
    head = None
    if title or actions is not None:
        head = tags.div(
            tags.div(tags.h3(title, class_="c-card-title") if title else None,
                     tags.p(subtitle, class_="c-card-sub") if subtitle else None),
            actions,
            class_="c-card-head",
        )
    return tags.div(head, *children, class_=f"c-card {class_}".strip())


def range_bar(low, high, value, left_label: str, right_label: str, caption: str | None = None) -> Tag:
    if fmt.is_missing(low) or fmt.is_missing(high) or fmt.is_missing(value) or high <= low:
        return tags.div()
    position = min(max((value - low) / (high - low), 0), 1) * 100
    return tags.div(
        tags.div(caption, class_="micro muted") if caption else None,
        tags.div(
            tags.div(class_="range-fill", style=f"width:{position:.1f}%"),
            tags.div(class_="range-dot", style=f"left:{position:.1f}%"),
            class_="range",
            role="img",
            aria_label=f"{caption or 'Range'}: {position:.0f}% of the way from {left_label} to {right_label}",
        ),
        tags.div(tags.span(left_label), tags.span(right_label), class_="range-labels"),
    )


def table(headers: Iterable[str], rows: Iterable[Iterable[TagChild]], class_: str = "") -> Tag:
    return tags.div(
        tags.table(
            tags.thead(tags.tr(*[tags.th(h) for h in headers])),
            tags.tbody(*[tags.tr(*[tags.td(cell) for cell in row]) for row in rows]),
            class_=f"c-table {class_}".strip(),
        ),
        class_="table-scroll",
    )


def empty_state(title: str, detail: str | None = None, *children: TagChild) -> Tag:
    return tags.div(tags.strong(title), tags.span(detail) if detail else None, *children, class_="empty")


def skeleton(height: int = 120, lines: int = 0) -> Tag:
    if lines:
        return tags.div(*[tags.div(class_="skeleton line", style=f"width:{90 - i * 15}%")
                          for i in range(lines)])
    return tags.div(class_="skeleton", style=f"min-height:{height}px")


def zone_bar(value: float, zones: list[tuple[str, float, float, str]], lo: float, hi: float,
             caption: str) -> Tag:
    """Horizontal bar split into labeled zones (label, start, end, tone) with a marker at ``value``."""
    span = hi - lo
    position = min(max((value - lo) / span, 0), 1) * 100
    return tags.div(
        tags.div(
            *[tags.div(tags.span(label), class_=f"zone {tone}", style=f"width:{(end - start) / span * 100:.2f}%")
              for label, start, end, tone in zones],
            tags.div(class_="zone-marker", style=f"left:{position:.1f}%"),
            class_="zones", role="img", aria_label=caption,
        ),
        tags.div(*[tags.span(f"{start:g}", style=f"left:{(start - lo) / span * 100:.2f}%")
                   for _, start, _, _ in zones[1:]], class_="zone-ticks"),
    )


def target_range(low, mean, high, current, symbol: str = "$") -> Tag:
    """Analyst low–high target range with the mean target and today's price marked."""
    values = [v for v in (low, mean, high, current) if not fmt.is_missing(v)]
    if fmt.is_missing(low) or fmt.is_missing(high) or high <= low or len(values) < 3:
        return tags.div()
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    at = lambda v: (v - lo) / (hi - lo) * 100
    return tags.div(
        tags.div(
            tags.div(class_="target-band", style=f"left:{at(low):.1f}%;width:{at(high) - at(low):.1f}%"),
            tags.div(tags.span(f"Mean {fmt.price(mean, symbol)}"), class_="target-mark mean",
                     style=f"left:{at(mean):.1f}%") if not fmt.is_missing(mean) else None,
            tags.div(tags.span(f"Now {fmt.price(current, symbol)}"), class_="target-mark now",
                     style=f"left:{at(current):.1f}%") if not fmt.is_missing(current) else None,
            class_="target", role="img",
            aria_label=f"Analyst targets {fmt.price(low, symbol)} to {fmt.price(high, symbol)}, "
                       f"mean {fmt.price(mean, symbol)}, price {fmt.price(current, symbol)}",
        ),
        tags.div(tags.span(f"Low {fmt.price(low, symbol)}"), tags.span(f"High {fmt.price(high, symbol)}"),
                 class_="range-labels"),
    )


def checklist(items: Iterable[tuple[bool | None, str, str]]) -> Tag:
    """Pass / fail / not-available list, each with a symbol as well as a color."""
    icon = {True: ("✓", "pass", "Passed"), False: ("✕", "fail", "Failed"), None: ("–", "na", "Not available")}
    return tags.ul(*[
        tags.li(tags.span(icon[passed][0], class_=f"check-icon {icon[passed][1]}", aria_label=icon[passed][2], role="img"),
                tags.div(tags.div(name, class_="check-name"), tags.div(detail, class_="check-detail")))
        for passed, name, detail in items
    ], class_="checks")
