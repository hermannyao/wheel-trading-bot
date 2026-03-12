from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from fastapi import HTTPException

from database import Signal, ScanHistory, SignalHistory


def run_scan_and_persist(db, overrides):
    try:
        from main_scan import run_scan

        scan_result = run_scan(overrides)
        signals = scan_result.get("signals", [])

        db.query(Signal).delete()

        for sig in signals:
            db_signal = Signal(
                symbol=sig.get("symbol"),
                price=sig.get("price"),
                strike=sig.get("strike"),
                dte=sig.get("dte"),
                bid=sig.get("bid"),
                ask=sig.get("ask"),
                delta=sig.get("delta"),
                iv=sig.get("iv"),
                open_interest=sig.get("openInterest"),
                volume=sig.get("volume"),
                spread=sig.get("spread"),
                apr=sig.get("apr"),
                contract_price=sig.get("contract_price"),
                max_profit=sig.get("max_profit"),
                distance_to_strike_pct=sig.get("distance_to_strike_pct"),
                is_itm=1 if sig.get("is_itm") else 0,
                status=sig.get("status"),
                expiration=sig.get("expiration"),
                contracts=sig.get("contracts"),
                budget_used=sig.get("budget_used"),
                max_budget_per_trade=sig.get("max_budget_per_trade"),
                earnings_date=sig.get("earnings_date"),
            )
            db.add(db_signal)

        db.commit()

        sell_put_count = sum(1 for s in signals if s.get("status") == "SELL PUT")
        avg_apr = sum(s.get("apr", 0) for s in signals if s.get("apr")) / len(signals) if signals else 0
        max_apr = max((s.get("apr", 0) for s in signals if s.get("apr")), default=0)

        history = ScanHistory(
            total_symbols=len(signals),
            total_signals=len(signals),
            sell_put_count=sell_put_count,
            avg_apr=avg_apr,
            max_apr=max_apr,
            symbols_total=scan_result.get("symbols_total"),
            symbols_priced=scan_result.get("symbols_priced"),
            symbols_affordable=scan_result.get("symbols_affordable"),
        )
        db.add(history)
        db.commit()

        if history.id:
            snapshots = []
            for s in signals:
                snapshots.append(
                    SignalHistory(
                        scan_id=history.id,
                        scan_date=history.scan_date,
                        symbol=s.get("symbol"),
                        price=s.get("price"),
                        strike=s.get("strike"),
                        dte=s.get("dte"),
                        apr=s.get("apr"),
                    )
                )
            if snapshots:
                db.add_all(snapshots)
                db.commit()

        return {
            "status": "success",
            "total_signals": len(signals),
            "sell_put_count": sell_put_count,
            "symbols_total": scan_result.get("symbols_total"),
            "symbols_priced": scan_result.get("symbols_priced"),
            "symbols_affordable": scan_result.get("symbols_affordable"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def run_scan_async(db, overrides):
    return await asyncio.to_thread(run_scan_and_persist, db, overrides)
