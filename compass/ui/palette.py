"""The color palette — the single source for both CSS (as custom properties) and charts.

Components use role names, never raw hex values, so a new palette is a change to
``BRAND`` and the role map below and nothing else. Contrast was checked against
WCAG: text pairings are ≥ 4.5:1, chart lines and fills on white ≥ 3:1.
"""

from __future__ import annotations

BRAND = {
    "indigo-900": "#3A3E98",
    "indigo-600": "#5256BC",
    "steel-500": "#527CBC",
    "sky-400": "#bcedff",
}

ROLES = {
    # Brand
    "ink": BRAND["indigo-900"],       # dominant dark: brand text, dark sections, icons (9.0:1 on white)
    "ink-2": BRAND["indigo-600"],     # raised surfaces on dark sections (white text 6.2:1)
    "secondary": BRAND["steel-500"],  # benchmark lines, secondary marks (4.2:1 on white)
    "accent": BRAND["sky-400"],       # active fills only — tabs, score bars; never text on white (2.5:1)
    "accent-on-dark": "#a8dcf0",      # accent as text on ink (6.1:1)
    "on-accent": "#11132e",           # text on accent fills (7.4:1)
    # Neutrals, tinted toward the indigo
    "obsidian": "#11132e",
    "charcoal": "#41445a",
    "slate": "#5f6379",
    "pebble": "#8a8da3",
    "fog": "#eceef6",
    "wash": "#e4f3fa",
    "paper": "#ffffff",
    # Status — gains and losses keep the finance convention, independent of the brand hues
    "gain": "#12775a",
    "gain-wash": "#def3ea",
    "loss": "#c62b34",
    "loss-wash": "#f9e2e3",
}


def rgb(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    return ", ".join(str(int(value[i:i + 2], 16)) for i in (0, 2, 4))


def rgba(role: str, alpha: float) -> str:
    return f"rgba({rgb(ROLES[role])}, {alpha})"


def css_variables() -> str:
    """``:root`` block exposing every role as ``--<role>`` plus ``--<role>-rgb`` for alpha use."""
    lines = [f"  --{name}: {value};\n  --{name}-rgb: {rgb(value)};" for name, value in ROLES.items()]
    return ":root {\n" + "\n".join(lines) + "\n}"


def logo_svg(size: int = 32) -> str:
    """Compass-needle mark in the current palette."""
    ink, accent, secondary = ROLES["ink"], ROLES["accent"], ROLES["secondary"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" height="{size}" '
        f'fill="none" aria-hidden="true">'
        f'<circle cx="16" cy="16" r="16" fill="{ink}"/>'
        f'<path d="M16 6 20 16 16 26 12 16Z" fill="{accent}"/>'
        f'<path d="M16 16 20 16 16 26Z" fill="{secondary}"/>'
        f'<circle cx="16" cy="16" r="2" fill="{ink}"/></svg>'
    )
