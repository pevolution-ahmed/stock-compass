"""The color palette — the single source for both CSS (as custom properties) and charts.

Components use role names, never raw hex values. Several themes are defined
below; ``COMPASS_THEME`` (environment variable) picks one at startup, otherwise
``DEFAULT_THEME``. Every theme was checked against WCAG: text pairings ≥ 4.5:1
(brand text ≥ 7:1), chart lines and fills on white ≥ 3:1.
"""

from __future__ import annotations

import os
import re

# Gains and losses keep the finance convention in every theme, independent of the brand hues
STATUS = {
    "light": {"gain": "#12775a", "gain-wash": "#def3ea", "loss": "#c62b34", "loss-wash": "#f9e2e3"},
    "dark": {"gain": "#4cc38a", "gain-wash": "#0f3326", "loss": "#ff6b6b", "loss-wash": "#3a1418"},
}
HAIRLINE = {"light": "rgba(14, 15, 12, 0.12)", "dark": "rgba(255, 255, 255, 0.09)"}

# Roles: ink = brand color for text and lines on the page · ink-2 = second brand tone ·
# feature / feature-2 = dark feature surfaces (scorecard, pillar cards, loaders), defaulting to
# ink / ink-2 · on-feature = text on them · secondary = benchmark lines · accent = active fills only ·
# accent-on-dark = accent as text on feature surfaces · on-accent = text on accent fills ·
# paper = page canvas · fog = tiles · wash = tinted highlights · obsidian/charcoal/slate/pebble = text
THEMES: dict[str, dict[str, str]] = {
    "indigo-sky": {
        "ink": "#3A3E98", "ink-2": "#5256BC", "secondary": "#527CBC", "accent": "#bcedff",
        "accent-on-dark": "#a8dcf0", "on-accent": "#11132e",
        "obsidian": "#11132e", "charcoal": "#41445a", "slate": "#5f6379", "pebble": "#8a8da3",
        "fog": "#eceef6", "wash": "#e4f3fa", "paper": "#ffffff",
    },
    "forest-lime": {  # deep forest green with an electric lime accent
        "ink": "#163300", "ink-2": "#054d28", "secondary": "#0b6b8a", "accent": "#9fe870",
        "accent-on-dark": "#9fe870", "on-accent": "#163300",
        "obsidian": "#0e0f0c", "charcoal": "#454745", "slate": "#5f625f", "pebble": "#868685",
        "fog": "#e8ebe6", "wash": "#e2f6d5", "paper": "#ffffff",
    },
    "midnight-gold": {
        "ink": "#0f1f45", "ink-2": "#1e3466", "secondary": "#3f6fb5", "accent": "#f4c45c",
        "accent-on-dark": "#f6cf73", "on-accent": "#1c1404",
        "obsidian": "#0b1022", "charcoal": "#3d4254", "slate": "#5b6176", "pebble": "#8a8fa3",
        "fog": "#eef0f5", "wash": "#fdf3dc", "paper": "#ffffff",
    },
    "graphite-mint": {
        "ink": "#1d2a30", "ink-2": "#2f4149", "secondary": "#1f7a80", "accent": "#7ee8cf",
        "accent-on-dark": "#8ff0d8", "on-accent": "#062a24",
        "obsidian": "#0f1518", "charcoal": "#3c4448", "slate": "#5a6469", "pebble": "#889196",
        "fog": "#edf1f1", "wash": "#e1f7f1", "paper": "#ffffff",
    },
    "plum-peach": {
        "ink": "#3b1d4d", "ink-2": "#57306d", "secondary": "#8a4fa6", "accent": "#ffc3a1",
        "accent-on-dark": "#ffcdb0", "on-accent": "#2e1206",
        "obsidian": "#1c0f24", "charcoal": "#463d4c", "slate": "#665c6d", "pebble": "#958c9a",
        "fog": "#f3eff5", "wash": "#fff0e7", "paper": "#ffffff",
    },
    "ocean-coral": {
        "ink": "#06394f", "ink-2": "#0f5a78", "secondary": "#1d7fa8", "accent": "#ffa98a",
        "accent-on-dark": "#ffb69b", "on-accent": "#33130a",
        "obsidian": "#04141c", "charcoal": "#38464d", "slate": "#56656d", "pebble": "#86949b",
        "fog": "#ebf2f5", "wash": "#ffeee8", "paper": "#ffffff",
    },
    # ---- dark themes ----
    "midnight-indigo": {
        "mode": "dark", "paper": "#0e1024", "fog": "#181b38", "wash": "#1d2348",
        "feature": "#23285a", "feature-2": "#3A3E98", "on-feature": "#ffffff",
        "ink": "#aab4ff", "ink-2": "#7c86e8", "secondary": "#6fb6e8",
        "accent": "#bcedff", "on-accent": "#0e1024", "accent-on-dark": "#bcedff",
        "obsidian": "#f2f3ff", "charcoal": "#c9cce6", "slate": "#a0a6c8", "pebble": "#6f75a0",
    },
    "obsidian-lime": {
        "mode": "dark", "paper": "#0b0f08", "fog": "#151c10", "wash": "#1b2a12",
        "feature": "#163300", "feature-2": "#22500a", "on-feature": "#ffffff",
        "ink": "#b8f28f", "ink-2": "#7fcf55", "secondary": "#5fb3d4",
        "accent": "#9fe870", "on-accent": "#0b1405", "accent-on-dark": "#9fe870",
        "obsidian": "#f1f6ec", "charcoal": "#c8d0c2", "slate": "#9ea896", "pebble": "#6c7566",
    },
    "carbon-gold": {
        "mode": "dark", "paper": "#0d0f14", "fog": "#171a22", "wash": "#262012",
        "feature": "#1a2030", "feature-2": "#283047", "on-feature": "#ffffff",
        "ink": "#f4d58a", "ink-2": "#c9a24a", "secondary": "#7ea7e0",
        "accent": "#f4c45c", "on-accent": "#1c1404", "accent-on-dark": "#f6cf73",
        "obsidian": "#f5f2ea", "charcoal": "#cfcbc2", "slate": "#a19e96", "pebble": "#6e6b64",
    },
    "deep-sea-mint": {
        "mode": "dark", "paper": "#071416", "fog": "#0f2226", "wash": "#0f2e2a",
        "feature": "#0f2a30", "feature-2": "#173e47", "on-feature": "#ffffff",
        "ink": "#8ff0d8", "ink-2": "#4fc9b0", "secondary": "#6cb8e6",
        "accent": "#7ee8cf", "on-accent": "#062a24", "accent-on-dark": "#8ff0d8",
        "obsidian": "#eaf7f5", "charcoal": "#c2d6d3", "slate": "#93aca9", "pebble": "#627a77",
    },
    "aubergine-peach": {
        "mode": "dark", "paper": "#130b18", "fog": "#1e1426", "wash": "#2a1a22",
        "feature": "#2a1838", "feature-2": "#3d2452", "on-feature": "#ffffff",
        "ink": "#ffc3a1", "ink-2": "#d79ad8", "secondary": "#b48ee0",
        "accent": "#ffc3a1", "on-accent": "#2e1206", "accent-on-dark": "#ffcdb0",
        "obsidian": "#f8f0fa", "charcoal": "#d6cadb", "slate": "#a99aaf", "pebble": "#75687b",
    },
}

DEFAULT_THEME = "indigo-sky"
# Dark counterpart offered by the light/dark switch for each light theme
DARK_PARTNER = {"indigo-sky": "midnight-indigo", "forest-lime": "obsidian-lime", "midnight-gold": "carbon-gold",
                "graphite-mint": "deep-sea-mint", "plum-peach": "aubergine-peach", "ocean-coral": "midnight-indigo"}


def roles(theme: str) -> dict[str, str]:
    """Every role for ``theme``, with feature surfaces defaulting to the brand ink."""
    values = dict(THEMES[theme])
    mode = values.pop("mode", "light")
    return {"feature": values["ink"], "feature-2": values["ink-2"], "on-feature": "#ffffff",
            **values, **STATUS[mode], "hairline": HAIRLINE[mode]}


def mode_of(theme: str) -> str:
    return THEMES[theme].get("mode", "light")


_chosen = os.environ.get("COMPASS_THEME", DEFAULT_THEME)
_chosen = _chosen if _chosen in THEMES else DEFAULT_THEME
if mode_of(_chosen) == "dark":
    LIGHT_THEME, DARK_THEME = DEFAULT_THEME, _chosen
else:
    LIGHT_THEME, DARK_THEME = _chosen, DARK_PARTNER.get(_chosen, "midnight-indigo")
THEME = LIGHT_THEME
MODE = "light"

# Charts are built with the light roles and translated for dark sessions (see ``to_dark``)
ROLES: dict[str, str] = roles(LIGHT_THEME)
DARK_ROLES: dict[str, str] = roles(DARK_THEME)


def rgb(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    return ", ".join(str(int(value[i:i + 2], 16)) for i in (0, 2, 4))


def rgba(role: str, alpha: float) -> str:
    return f"rgba({rgb(ROLES[role])}, {alpha})"


def _css_block(selector: str, values: dict[str, str], mode: str) -> str:
    lines = [f"  --{name}: {value};" + (f"\n  --{name}-rgb: {rgb(value)};" if value.startswith("#") else "")
             for name, value in values.items()]
    return f"{selector} {{\n  color-scheme: {mode};\n" + "\n".join(lines) + "\n}"


def css_variables() -> str:
    """Both palettes as custom properties; ``<html data-theme="dark">`` switches to the dark one."""
    return (_css_block(':root, :root[data-theme="light"]', ROLES, "light") + "\n"
            + _css_block(':root[data-theme="dark"]', DARK_ROLES, "dark"))


def _color_map() -> dict[str, str]:
    """Light role color → dark role color (first role wins when two share a value)."""
    # Line and text roles first: in light themes the feature surface shares the ink's value,
    # but on a chart that color is always a line, so it must become the dark theme's ink
    priority = ["ink", "ink-2", "secondary", "gain", "loss", "obsidian", "charcoal", "slate", "pebble",
                "accent", "gain-wash", "loss-wash", "fog", "wash", "paper"]
    ordered = priority + [role for role in ROLES if role not in priority]
    mapping: dict[str, str] = {}
    for role in ordered:
        light = ROLES[role]
        dark = DARK_ROLES.get(role)
        if light.startswith("#") and dark and dark.startswith("#"):
            mapping.setdefault(light.lower(), dark)
    return mapping


_DARK_MAP = _color_map()
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_RGBA = re.compile(r"rgba\((\d+), (\d+), (\d+),")


def to_dark(figure_json: str) -> str:
    """Recolor a Plotly figure's JSON from the light palette to the dark one."""
    out = _HEX.sub(lambda m: _DARK_MAP.get(m.group(0).lower(), m.group(0)), figure_json)

    def rgba(m: re.Match) -> str:
        light = "#{:02x}{:02x}{:02x}".format(*(int(v) for v in m.groups()))
        dark = _DARK_MAP.get(light)
        return f"rgba({rgb(dark)}," if dark else m.group(0)

    return _RGBA.sub(rgba, out)


def logo_svg(size: int = 32, static: bool = False) -> str:
    """Compass-needle mark. Inline marks follow the light/dark switch through CSS variables;
    ``static`` uses fixed colors for places CSS can't reach (the favicon)."""
    if static:
        disc, ring, accent, secondary = ROLES["feature"], ROLES["ink"], ROLES["accent"], ROLES["secondary"]
        fill = lambda color: f'fill="{color}"'
        stroke = f'stroke="{ring}"'
    else:
        fill = lambda var: f'style="fill: var(--{var})"'
        disc, accent, secondary = "feature", "accent", "secondary"
        stroke = 'style="fill: var(--feature); stroke: var(--ink)"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" height="{size}" '
        f'fill="none" aria-hidden="true">'
        f'<circle cx="16" cy="16" r="15.25" {fill(disc) if static else ""} {stroke} stroke-width="1.5"/>'
        f'<path d="M16 6 20 16 16 26 12 16Z" {fill(accent)}/>'
        f'<path d="M16 16 20 16 16 26Z" {fill(secondary)}/>'
        f'<circle cx="16" cy="16" r="2" {fill(disc)}/></svg>'
    )
