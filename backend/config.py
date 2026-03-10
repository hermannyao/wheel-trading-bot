"""Application configuration constants."""

import os

# Scan universe
DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "AMZN",
    "NVDA",
    "TSLA",
    "META",
    "GOOGL",
]

SYMBOLS = [
    s.strip().upper()
    for s in os.getenv("WHEEL_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",")
    if s.strip()
]

# Scan parameters
MIN_DTE = int(os.getenv("MIN_DTE", "21"))
MAX_DTE = int(os.getenv("MAX_DTE", "45"))
TARGET_OTM_PCT = float(os.getenv("TARGET_OTM_PCT", "0.05"))
MIN_OPEN_INTEREST = int(os.getenv("MIN_OPEN_INTEREST", "10"))
MIN_IV = float(os.getenv("MIN_IV", "0.20"))
MIN_APR = float(os.getenv("MIN_APR", "15.0"))

# Capital config
MAX_CAPITAL_PER_TRADE = float(os.getenv("MAX_CAPITAL_PER_TRADE", "2000"))
