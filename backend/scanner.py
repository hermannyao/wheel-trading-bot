"""High-performance Wheel scanner (S&P 500)."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
import contextlib
import io
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf

from config import (
    SP500_SOURCE_URL,
    SP500_LOCAL_FILE,
    SP500_EXCLUDE_FILE,
    SYMBOLS,
    MIN_DTE,
    MAX_DTE,
    TARGET_OTM_PCT,
    MIN_OPEN_INTEREST,
    MIN_IV,
    MIN_APR,
    DELTA_MIN,
    DELTA_MAX,
    CALL_DELTA_MIN,
    CALL_DELTA_MAX,
    MAX_SPREAD_PCT,
    MAX_WORKERS,
    RISK_FREE_RATE,
    MAX_BUDGET_PER_TRADE,
    MAX_TOTAL_BUDGET,
)


def _read_local_symbols() -> List[str]:
    path = Path(SP500_LOCAL_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        return []
    symbols = []
    for line in path.read_text().splitlines():
        sym = line.strip().upper()
        if sym and not sym.startswith("#"):
            symbols.append(sym.replace(".", "-"))
    return symbols


def _read_exclude_symbols() -> set[str]:
    path = Path(SP500_EXCLUDE_FILE)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        return set()
    excluded = set()
    for line in path.read_text().splitlines():
        sym = line.strip().upper()
        if sym and not sym.startswith("#"):
            excluded.add(sym.replace(".", "-"))
    return excluded


# Reduce yfinance noise for missing symbols
logging.getLogger("yfinance").setLevel(logging.ERROR)


def fetch_sp500_symbols() -> List[str]:
    """Fetch S&P 500 tickers from local file or Wikipedia."""
    excluded = _read_exclude_symbols()
    local = _read_local_symbols()
    if local:
        return [s for s in local if s not in excluded]
    try:
        resp = requests.get(SP500_SOURCE_URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", {"id": "constituents"})
        if not table:
            return SYMBOLS
        symbols = []
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if not cols:
                continue
            sym = cols[0].get_text(strip=True).upper().replace(".", "-")
            if sym:
                symbols.append(sym)
        if symbols:
            return [s for s in symbols if s not in excluded]
        return [s for s in SYMBOLS if s not in excluded]
    except Exception:
        return [s for s in SYMBOLS if s not in excluded]


def fetch_prices_bulk(symbols: List[str]) -> Dict[str, float]:
    """Fetch latest prices for all symbols in a single call."""
    if not symbols:
        return {}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            data = yf.download(
                tickers=" ".join(symbols),
                period="1d",
                group_by="ticker",
                threads=True,
                auto_adjust=False,
                progress=False,
            )
        if data is None or data.empty:
            return {}
        prices = {}
        if isinstance(data.columns, pd.MultiIndex):
            for sym in symbols:
                if sym in data.columns.get_level_values(0):
                    try:
                        close = data[sym]["Close"].dropna()
                        if not close.empty:
                            prices[sym] = float(close.iloc[-1])
                    except Exception:
                        continue
        else:
            try:
                close = data["Close"].dropna()
                if not close.empty and len(symbols) == 1:
                    prices[symbols[0]] = float(close.iloc[-1])
            except Exception:
                return {}
        return prices
    except Exception:
        return {}


_EARNINGS_CACHE: dict[str, str] = {}


def _fetch_earnings_date(symbol: str) -> str | None:
    if symbol in _EARNINGS_CACHE:
        return _EARNINGS_CACHE[symbol]
    try:
        ticker = yf.Ticker(symbol)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            dates = ticker.get_earnings_dates(limit=1)
        if dates is not None and not dates.empty:
            idx = dates.index[0]
            if isinstance(idx, pd.Timestamp):
                value = idx.date().isoformat()
            else:
                value = str(idx)
            _EARNINGS_CACHE[symbol] = value
            return value
    except Exception:
        pass
    return None


def _select_expiration(expirations: List[str], min_dte: int, max_dte: int) -> Tuple[str | None, int | None]:
    """Pick an expiration within the DTE window, closest to mid range."""
    if not expirations:
        return None, None
    today = datetime.utcnow().date()
    candidates = []
    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte:
            candidates.append((abs(dte - ((min_dte + max_dte) // 2)), exp, dte))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _put_delta(price: float, strike: float, dte: int, iv: float, r: float) -> float | None:
    if price <= 0 or strike <= 0 or dte <= 0 or iv is None or iv <= 0:
        return None
    t = dte / 365.0
    try:
        d1 = (math.log(price / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    except (ValueError, ZeroDivisionError):
        return None
    return _norm_cdf(d1) - 1.0


def _call_delta(price: float, strike: float, dte: int, iv: float, r: float) -> float | None:
    if price <= 0 or strike <= 0 or dte <= 0 or iv is None or iv <= 0:
        return None
    t = dte / 365.0
    try:
        d1 = (math.log(price / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    except (ValueError, ZeroDivisionError):
        return None
    return _norm_cdf(d1)


def _calc_apr(premium: float, strike: float, dte: int) -> float | None:
    if premium <= 0 or strike <= 0 or dte <= 0:
        return None
    return round((premium / strike) * (365 / dte) * 100, 2)


def _pick_candidate_put(
    puts: pd.DataFrame,
    price: float,
    dte: int,
    target_delta: float | None,
) -> dict | None:
    if puts is None or puts.empty:
        return None
    target_strike = price * (1 - TARGET_OTM_PCT)
    puts = puts.copy()
    puts["strike_diff"] = (puts["strike"] - target_strike).abs()
    puts = puts.sort_values(["strike_diff", "strike"]).reset_index(drop=True)

    best = None
    best_score = None
    for _, row in puts.iterrows():
        strike = float(row.get("strike") or 0)
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        premium = bid if bid > 0 else ask
        if premium <= 0:
            continue
        # Enforce strict OTM target: strike must be <= target strike
        if strike > target_strike:
            continue
        iv = row.get("impliedVolatility")
        delta = _put_delta(price, strike, dte, iv, RISK_FREE_RATE)
        if delta is None:
            continue
        delta_abs = abs(delta)
        if target_delta is not None:
            score = abs(delta_abs - target_delta)
        else:
            if not (DELTA_MIN <= delta_abs <= DELTA_MAX):
                continue
            score = delta_abs
        if best_score is None or score < best_score:
            best_score = score
            best = row.to_dict()
    return best


def _pick_candidate_call(
    calls: pd.DataFrame,
    price: float,
    cost_basis: float,
    min_otm_pct: float = 0.03,
    max_otm_pct: float = 0.08,
) -> dict | None:
    if calls is None or calls.empty:
        return None
    calls = calls.copy()
    calls["otm_pct"] = (calls["strike"] - price) / price
    candidates = calls[
        (calls["strike"] >= cost_basis)
        & (calls["otm_pct"] >= min_otm_pct)
        & (calls["otm_pct"] <= max_otm_pct)
    ].copy()
    if candidates.empty:
        return None
    target = (min_otm_pct + max_otm_pct) / 2
    candidates["score"] = (candidates["otm_pct"] - target).abs()
    candidates = candidates.sort_values(["score", "strike"]).reset_index(drop=True)
    return candidates.iloc[0].to_dict()


def scan_covered_calls(
    symbol: str,
    price: float,
    cost_basis: float,
    put_strike: float | None,
    contracts: int,
    overrides: dict,
) -> list[dict]:
    try:
        min_dte = overrides.get("min_dte", MIN_DTE)
        max_dte = overrides.get("max_dte", MAX_DTE)
        min_iv = overrides.get("min_iv", MIN_IV)
        min_apr = overrides.get("min_apr", MIN_APR)
        min_open_interest = overrides.get("min_open_interest", MIN_OPEN_INTEREST)
        max_spread_pct = overrides.get("max_spread_pct", MAX_SPREAD_PCT)
        call_delta_min = overrides.get("call_delta_min", CALL_DELTA_MIN)
        call_delta_max = overrides.get("call_delta_max", CALL_DELTA_MAX)

        ticker = yf.Ticker(symbol)
        expiration, dte = _select_expiration(ticker.options, min_dte, max_dte)
        if not expiration or not dte:
            return None
        chain = ticker.option_chain(expiration)
        calls_df = chain.calls
        if calls_df is None or calls_df.empty:
            return []
        calls_df = calls_df.copy()
        calls_df["otm_pct"] = (calls_df["strike"] - price) / price
        min_strike = max(cost_basis, put_strike or cost_basis)
        calls_df = calls_df[
            (calls_df["strike"] >= min_strike)
            & (calls_df["otm_pct"] >= 0.03)
            & (calls_df["otm_pct"] <= 0.08)
        ].copy()
        if calls_df.empty:
            return []

        results: list[dict] = []
        for _, call in calls_df.iterrows():
            strike = float(call.get("strike") or 0)
            bid = float(call.get("bid") or 0)
            ask = float(call.get("ask") or 0)
            volume = call.get("volume")
            if bid <= 0 or (volume is None or volume <= 0):
                continue
            premium = bid if bid > 0 else ask
            iv = call.get("impliedVolatility")
            open_interest = call.get("openInterest")
            spread = abs(ask - bid) if ask and bid else None
            spread_pct = (spread / bid) if spread is not None and bid > 0 else None
            if iv is None or iv < min_iv:
                continue
            if open_interest is None or int(open_interest) < min_open_interest:
                continue
            if spread_pct is None or spread_pct > max_spread_pct:
                continue

            delta = _call_delta(price, strike, dte, float(iv), RISK_FREE_RATE) if iv is not None else None
            if delta is None:
                continue
            if not (call_delta_min <= delta <= call_delta_max):
                continue

            apr = _calc_apr(premium, strike, dte) if bid > 0 and ask > 0 else None
            if apr is None or apr < min_apr:
                continue

            distance_to_basis = strike - cost_basis
            distance_to_basis_pct = (distance_to_basis / cost_basis) * 100 if cost_basis else 0
            otm_pct = ((strike - price) / price) * 100 if price else 0
            contract_price = round(premium * 100, 2) if bid > 0 and ask > 0 else None
            max_profit = round(contract_price * contracts, 2) if contract_price is not None else None
            gain_max_call = round(premium * 100 * contracts, 2)

            results.append({
                "symbol": symbol,
                "price": round(price, 2),
                "strike": round(strike, 2),
                "dte": dte,
                "bid": bid if bid > 0 else None,
                "ask": ask if ask > 0 else None,
                "delta": round(delta, 4),
                "iv": round(float(iv), 4) if iv is not None else None,
                "openInterest": int(open_interest) if open_interest is not None else None,
                "volume": int(volume) if volume is not None else None,
                "spread": round(spread, 4) if spread is not None else None,
                "apr": apr,
                "contract_price": contract_price,
                "max_profit": max_profit,
                "gain_max_call": gain_max_call,
                "distance_to_basis": round(distance_to_basis, 2),
                "distance_to_basis_pct": round(distance_to_basis_pct, 2),
                "otm_pct": round(otm_pct, 2),
                "expiration": expiration,
            })

        results.sort(key=lambda x: x.get("apr") or 0, reverse=True)
        return results[:3]
    except Exception:
        return []


def _status_from_metrics(
    apr: float | None,
    iv: float | None,
    open_interest: int | None,
    spread_pct: float | None,
    bid: float,
    ask: float,
    min_iv: float,
    min_apr: float,
    min_open_interest: int,
    max_spread_pct: float,
) -> str:
    if bid <= 0 or ask <= 0:
        return "ILLIQUID"
    if open_interest is not None and open_interest < min_open_interest:
        return "ILLIQUID"
    if spread_pct is not None and spread_pct > max_spread_pct:
        return "ILLIQUID"
    if iv is not None and iv < min_iv:
        return "LOW VOLATILITY"
    if apr is not None and apr >= min_apr:
        return "SELL PUT"
    return "EXPENSIVE"


def scan_symbol(symbol: str, price: float, overrides: dict) -> Dict[str, Any] | None:
    try:
        min_dte = overrides.get("min_dte", MIN_DTE)
        max_dte = overrides.get("max_dte", MAX_DTE)
        min_iv = overrides.get("min_iv", MIN_IV)
        min_apr = overrides.get("min_apr", MIN_APR)
        min_open_interest = overrides.get("min_open_interest", MIN_OPEN_INTEREST)
        max_spread_pct = overrides.get("max_spread_pct", MAX_SPREAD_PCT)
        delta_target = overrides.get("delta_target")

        ticker = yf.Ticker(symbol)
        expiration, dte = _select_expiration(ticker.options, min_dte, max_dte)
        if not expiration or not dte:
            return None
        chain = ticker.option_chain(expiration)
        put = _pick_candidate_put(chain.puts, price, dte, delta_target)
        if not put:
            return None

        strike = float(put.get("strike"))
        distance_to_strike_pct = ((strike - price) / price) * 100 if price else 0
        is_itm = strike >= price if price else False
        if is_itm:
            return None
        bid = float(put.get("bid") or 0)
        ask = float(put.get("ask") or 0)
        volume = put.get("volume")
        if bid <= 0 or (volume is None or volume <= 0):
            return None
        premium = bid if bid > 0 else ask
        iv = put.get("impliedVolatility")
        open_interest = put.get("openInterest")
        spread = abs(ask - bid) if ask and bid else None
        spread_pct = (spread / bid) if spread is not None and bid > 0 else None
        # Hard filters for IV, OI, Spread
        if iv is None or iv < min_iv:
            return None
        if open_interest is None or int(open_interest) < min_open_interest:
            return None
        if spread_pct is None or spread_pct > max_spread_pct:
            return None

        apr = _calc_apr(premium, strike, dte) if bid > 0 and ask > 0 else None
        if apr is None or apr < min_apr:
            return None
        max_budget_per_trade = overrides.get("capital", MAX_BUDGET_PER_TRADE)
        contracts = int(max_budget_per_trade // (strike * 100)) if strike > 0 else 0
        budget_used = round(contracts * strike * 100, 2)
        if budget_used > max_budget_per_trade or contracts <= 0:
            return None
        contract_price = round(premium * 100, 2) if bid > 0 and ask > 0 else None
        max_profit = round(contract_price * contracts, 2) if contract_price is not None else None

        status = _status_from_metrics(
            apr,
            iv,
            int(open_interest) if open_interest is not None else None,
            spread_pct,
            bid,
            ask,
            min_iv,
            min_apr,
            min_open_interest,
            max_spread_pct,
        )

        earnings_date = _fetch_earnings_date(symbol)
        return {
            "symbol": symbol,
            "price": round(price, 2),
            "strike": round(strike, 2),
            "dte": dte,
            "bid": bid if bid > 0 else None,
            "ask": ask if ask > 0 else None,
            "delta": abs(_put_delta(price, strike, dte, iv, RISK_FREE_RATE)) if iv else None,
            "iv": round(float(iv), 4) if iv is not None else None,
            "openInterest": int(open_interest) if open_interest is not None else None,
            "volume": int(volume) if volume is not None else None,
            "spread": round(spread, 4) if spread is not None else None,
            "apr": apr,
            "contract_price": contract_price,
            "max_profit": max_profit,
            "distance_to_strike_pct": round(distance_to_strike_pct, 2),
            "is_itm": is_itm,
            "status": status,
            "expiration": expiration,
            "contracts": contracts,
            "budget_used": budget_used,
            "max_budget_per_trade": max_budget_per_trade,
            "earnings_date": earnings_date,
        }
    except Exception:
        return None


def scan_all(
    capital: float | None = None,
    overrides: dict | None = None,
    cancel_event: Any | None = None,
    progress_cb: Any | None = None,
) -> Dict[str, Any]:
    """Scan S&P 500, filter by budget, scan options in parallel."""
    overrides = overrides or {}
    budget = capital if capital is not None else MAX_BUDGET_PER_TRADE
    overrides = {**overrides, "capital": budget, "max_total_budget": budget}

    symbols = fetch_sp500_symbols()
    prices = fetch_prices_bulk(symbols)

    affordable = [
        sym
        for sym, price in prices.items()
        if price > 0 and (price * 100) <= budget
    ]

    results: List[Dict[str, Any]] = []
    processed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for sym in affordable:
            if cancel_event and cancel_event.is_set():
                break
            futures[executor.submit(scan_symbol, sym, prices[sym], overrides)] = sym

        for future in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                break
            res = future.result()
            if res:
                results.append(res)
            processed += 1
            if progress_cb:
                progress_cb(processed, len(affordable))

    results.sort(key=lambda x: x.get("apr") or 0, reverse=True)
    return {
        "signals": results,
        "symbols_total": len(symbols),
        "symbols_priced": len(prices),
        "symbols_affordable": len(affordable),
        "symbols_processed": processed,
    }


def export_to_csv(signals: List[Dict[str, Any]]) -> str:
    """Export signals to CSV in project root."""
    if not signals:
        return ""
    root = Path(__file__).resolve().parent.parent
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = root / f"scan_results_{ts}.csv"
    try:
        df = pd.DataFrame(signals)
        df.to_csv(path, index=False)
    except Exception:
        return ""
    return str(path)
