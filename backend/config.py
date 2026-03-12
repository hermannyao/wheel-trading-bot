"""Application configuration constants."""

import os

SP500_SOURCE_URL = os.getenv(
    "SP500_SOURCE_URL",
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
)
SP500_LOCAL_FILE = os.getenv("SP500_LOCAL_FILE", "backend/sp500_symbols.txt")
SP500_EXCLUDE_FILE = os.getenv("SP500_EXCLUDE_FILE", "backend/sp500_exclude.txt")

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "AMZN", "NVDA", "TSLA", "META", "GOOGL"]

SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("WHEEL_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",")
    if s.strip()
]

# Scan parameters
MIN_DTE = int(os.getenv("MIN_DTE", "21"))
MAX_DTE = int(os.getenv("MAX_DTE", "45"))
TARGET_OTM_PCT = float(os.getenv("TARGET_OTM_PCT", "0.05"))
MIN_OPEN_INTEREST = int(os.getenv("MIN_OPEN_INTEREST", "100"))
MIN_IV = float(os.getenv("MIN_IV", "0.20"))
MIN_APR = float(os.getenv("MIN_APR", "8.0"))
DELTA_MIN = float(os.getenv("DELTA_MIN", "0.20"))
DELTA_MAX = float(os.getenv("DELTA_MAX", "0.40"))
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.10"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.02"))

# Capital config
MAX_BUDGET_PER_TRADE = float(os.getenv("MAX_BUDGET_PER_TRADE", "3000"))
MAX_TOTAL_BUDGET = float(os.getenv("MAX_TOTAL_BUDGET", str(MAX_BUDGET_PER_TRADE)))
