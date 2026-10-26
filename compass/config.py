"""App-wide settings. Everything tunable without touching feature code lives here."""

APP_NAME = "Stock Compass"
APP_TAGLINE = "Everything an investor needs on one stock, on one page."

DEFAULT_SYMBOL = "MSFT"
BENCHMARK_SYMBOL = "SPY"
BENCHMARK_LABEL = "S&P 500"

QUICK_PICKS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "JPM", "KO"]
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "GOOGL", "JPM"]

# 13-week T-bill yield (percent) used as the risk-free rate; fallback when unavailable
RISK_FREE_SYMBOL = "^IRX"
RISK_FREE_FALLBACK = 0.04
TREASURY_10Y_SYMBOL = "^TNX"
TREASURY_10Y_FALLBACK = 0.045

TRADING_DAYS = 252

# Seconds each kind of data stays in the shared cache
CACHE_TTL = {
    "quote": 60,
    "history": 15 * 60,
    "fundamentals": 12 * 60 * 60,
    "search": 60 * 60,
    "rates": 60 * 60,
}

DISCLAIMER = (
    "Data from Yahoo Finance, delayed and unaudited. "
    "For information only — not investment advice."
)
