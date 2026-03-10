"""Market data scan for Wheel strategy signals."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import yfinance as yf

from config import (
    SYMBOLS,
    MIN_DTE,
    MAX_DTE,
    TARGET_OTM_PCT,
    MIN_OPEN_INTEREST,
    MIN_IV,
    MIN_APR,
)


def _select_expiration(expirations: List[str]) -> str | None:
    """Pick an expiration within the DTE window, closest to mid range."""
    if not expirations:
        return None
    today = datetime.utcnow().date()
    candidates = []
    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (exp_date - today).days
        if MIN_DTE <= dte <= MAX_DTE:
            candidates.append((abs(dte - ((MIN_DTE + MAX_DTE) // 2)), exp, dte))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _pick_put(chain, price: float) -> dict | None:
    puts = chain.puts
    if puts is None or puts.empty:
        return None
    target_strike = price * (1 - TARGET_OTM_PCT)
    puts = puts.copy()
    puts["strike_diff"] = (puts["strike"] - target_strike).abs()
    puts = puts.sort_values(["strike_diff", "strike"])
    return puts.iloc[0].to_dict()


def _calc_apr(premium: float, strike: float, dte: int) -> float | None:
    if premium <= 0 or strike <= 0 or dte <= 0:
        return None
    return round((premium / strike) * (365 / dte) * 100, 2)


def _status_from_metrics(premium: float, iv: float | None, open_interest: int | None, apr: float | None) -> str:
    if premium <= 0 or (open_interest is not None and open_interest < MIN_OPEN_INTEREST):
        return "ILLIQUID"
    if iv is not None and iv < MIN_IV:
        return "LOW VOLATILITY"
    if apr is not None and apr >= MIN_APR:
        return "SELL PUT"
    return "EXPENSIVE"


def scan_all(capital: float) -> List[Dict[str, Any]]:
    """Scan symbols and return normalized signal dicts."""
    results: List[Dict[str, Any]] = []
    for symbol in SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if hist is None or hist.empty:
                continue
            price = float(hist["Close"].iloc[-1])

            expiration = _select_expiration(ticker.options)
            if not expiration:
                continue

            chain = ticker.option_chain(expiration)
            put = _pick_put(chain, price)
            if not put:
                continue

            strike = float(put.get("strike"))
            bid = float(put.get("bid") or 0)
            ask = float(put.get("ask") or 0)
            premium = bid if bid > 0 else ask
            iv = put.get("impliedVolatility")
            open_interest = put.get("openInterest")

            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
            dte = (exp_date - datetime.utcnow().date()).days

            apr = _calc_apr(premium, strike, dte)
            status = _status_from_metrics(premium, iv, open_interest, apr)

            results.append(
                {
                    "symbol": symbol,
                    "price": round(price, 2),
                    "strike": round(strike, 2),
                    "dte": dte,
                    "bid": bid if bid > 0 else None,
                    "ask": ask if ask > 0 else None,
                    "delta": None,
                    "iv": round(float(iv), 4) if iv is not None else None,
                    "openInterest": int(open_interest) if open_interest is not None else None,
                    "apr": apr,
                    "status": status,
                    "expiration": expiration,
                }
            )
        except Exception:
            # Skip symbol on any data error to keep scan robust
            continue
    return results


def export_to_csv(signals: List[Dict[str, Any]]) -> str:
    """Export signals to CSV in project root."""
    if not signals:
        return ""
    root = Path(__file__).resolve().parent.parent
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = root / f"scan_results_{ts}.csv"
    try:
        import pandas as pd

        df = pd.DataFrame(signals)
        df.to_csv(path, index=False)
    except Exception:
        # CSV export is non-critical
        return ""
    return str(path)
