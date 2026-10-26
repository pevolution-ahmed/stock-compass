# Stock Compass

A one-stop investor dashboard for any stock, built with Shiny for Python: returns and ROI, risk, valuation, business quality and financial health, with transparent 0–100 scores that show exactly which metrics they come from.

> Data from Yahoo Finance via [yahooquery](https://github.com/dpguthrie/yahooquery), delayed and unaudited. For information only — not investment advice.

## What's in it

- **Overview** — scorecard (Value, Quality, Growth, Health, Momentum), key numbers, growth of $10,000 against the S&P 500, and plain-language highlights.
- **Performance & Risk** — "if you had invested…" calculator (with or without dividend reinvestment), total returns by period, volatility, drawdowns, Sharpe/Sortino/Calmar, beta, value at risk, up/down capture, calendar-year and monthly returns.
- **Valuation** — multiples against their own ~4-year median, valuation history, analyst targets, and an adjustable two-stage DCF with reverse DCF (the growth today's price implies) and a sensitivity grid.
- **Fundamentals** — revenue, profit and free cash flow trends, margins, ROIC/ROE, debt and liquidity, Altman Z-score, an itemized Piotroski F-score, dividends and buybacks.
- Banks, insurers and funds get metrics that suit them; models that don't apply say so instead of showing misleading numbers.
- Search any ticker, or open one directly with `?symbol=NVDA`.

Analysts & Ownership, Technicals and a Watchlist are in progress.

## Run it

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv -r requirements-dev.txt
.venv/Scripts/shiny run app.py        # macOS/Linux: .venv/bin/shiny run app.py
```

Then open http://127.0.0.1:8000.

To work offline against recorded data, set `COMPASS_FIXTURES=tests/fixtures` before starting the app. Refresh the recordings with `python scripts/record_fixtures.py MSFT JPM SPY ^IRX`.

## Tests

```bash
.venv/Scripts/python -m pytest
```

Unit tests check the analytics against known answers; the smoke test starts the app on recorded fixtures and renders every output for a regular stock, a bank, an ETF and an unknown ticker.

## How it's organized

```
app.py                 entry point (re-exports compass.app.app)
compass/
  config.py            app name, benchmark, cache TTLs
  state.py             per-session StockContext: background fetches + shared derived data
  data/                the only code that talks to Yahoo; normalizes and caches its answers
  analytics/           pure pandas/numpy: returns, risk, metrics, scoring (no Shiny imports)
  ui/                  formatting, components, Plotly theme and chart builders
  modules/             one Shiny module per feature (search, hero, overview, performance, valuation, fundamentals)
  ui/palette.py        the color palette — single source for CSS variables and charts
  www/                 type/spacing tokens (from DESIGN.md), styles, scripts, logo
tests/                 analytics unit tests, end-to-end smoke test, recorded fixtures
```

Modules only read from `StockContext`, so a new section is one file in `compass/modules/` plus two lines in `compass/app.py`.

## Versions

- `v1.0.0` — the original 2023 technical analyzer (Shiny 0.2.9).
- `v1.1.0` — the same app ported to current Shiny, pandas and yahooquery.
