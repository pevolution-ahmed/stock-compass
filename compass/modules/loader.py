"""Loading overlay that shows real progress while a stock's data arrives.

The overlay is static HTML that's visible from the first paint (before the
websocket connects). The server pushes the state of each background fetch as a
custom message and www/js/app.js updates the bar and checklist in place, so the
animation never restarts mid-load.
"""

from __future__ import annotations

from htmltools import HTML, tags
from shiny import module, reactive

from .. import config
from ..state import Resource, StockContext
from ..ui.palette import logo_svg

STEPS = [
    ("snapshot", "Quote & company profile"),
    ("history", "Full price history"),
    ("statements", "Financial statements"),
    ("insights", "Analyst estimates & ownership"),
    ("benchmark", f"{config.BENCHMARK_LABEL} benchmark"),
]


def step_state(resource: Resource) -> str:
    """pending | running | done | error, from a background fetch's status."""
    status = resource.task.status()
    if status == "initial":
        return "pending"
    if status == "running":
        return "running"
    if status == "success":
        result = resource.task.result()
        return "error" if result is not None and result.error else "done"
    return "error"


def progress(states: dict[str, str]) -> dict:
    finished = sum(state in ("done", "error") for state in states.values())
    return {"steps": [{"key": key, "label": label, "state": states[key]} for key, label in STEPS],
            "fraction": finished / len(STEPS), "done": finished == len(STEPS)}


@module.ui
def loader_ui():
    return tags.div(
        tags.div(
            tags.div(HTML(logo_svg(72)), class_="loader-mark", aria_hidden="true"),
            tags.div("Loading", class_="eyebrow", id="compass-loader-eyebrow"),
            tags.h2(f"Gathering {config.DEFAULT_SYMBOL}'s data", id="compass-loader-title"),
            tags.p("Prices, financials and analyst data come from several sources, so this takes a few seconds.",
                   class_="loader-sub", id="compass-loader-sub"),
            tags.div(tags.div(class_="loader-fill", id="compass-loader-fill"), class_="loader-track",
                     role="progressbar", aria_valuemin="0", aria_valuemax="100", aria_valuenow="0",
                     aria_label="Data loaded", id="compass-loader-bar"),
            tags.ul(*[tags.li(tags.span(class_="loader-icon"), tags.span(label), data_step=key, class_="pending")
                      for key, label in STEPS], class_="loader-steps"),
            tags.button("Show what's ready", type="button", class_="loader-skip", id="compass-loader-skip"),
            class_="loader-card", role="status", aria_live="polite",
        ),
        id="compass-loader", class_="loader is-visible",
    )


@module.server
def loader_server(input, output, session, ctx: StockContext):
    resources = {"snapshot": ctx.snapshot, "history": ctx.history, "statements": ctx.statements,
                 "insights": ctx.insights, "benchmark": ctx.benchmark}

    @reactive.effect
    async def _report():
        states = {key: step_state(resource) for key, resource in resources.items()}
        snapshot = ctx.snapshot.value_or_none()
        await session.send_custom_message("compass-loader", {
            "symbol": ctx.symbol(),
            "name": snapshot.name if snapshot is not None else None,
            **progress(states),
        })
