from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime

from database import SessionLocal, ScanHistory, Signal, SignalHistory
from main_scan import run_scan


class ScanJob:
    def __init__(self, scan_id: str, thread: threading.Thread, cancel_event: threading.Event):
        self.scan_id = scan_id
        self.thread = thread
        self.cancel_event = cancel_event


class ScanRunner:
    def __init__(self):
        self.jobs: dict[str, ScanJob] = {}

    def start(self, params: dict) -> str:
        scan_id = str(uuid.uuid4())
        cancel_event = threading.Event()
        thread = threading.Thread(target=self._run, args=(scan_id, params, cancel_event), daemon=True)
        self.jobs[scan_id] = ScanJob(scan_id, thread, cancel_event)
        thread.start()
        return scan_id

    def cancel(self, scan_id: str) -> bool:
        job = self.jobs.get(scan_id)
        if not job:
            return False
        job.cancel_event.set()
        return True

    def _run(self, scan_id: str, params: dict, cancel_event: threading.Event) -> None:
        db = SessionLocal()
        last_progress_commit = 0.0
        try:
            history = ScanHistory(
                scan_date=datetime.utcnow(),
                total_symbols=0,
                total_signals=0,
                sell_put_count=0,
                avg_apr=0,
                max_apr=0,
                scan_id=scan_id,
                status="RUNNING",
                params_json=str(params),
            )
            db.add(history)
            db.commit()

            def progress_cb(processed: int, total: int) -> None:
                nonlocal last_progress_commit
                now = time.time()
                # throttle DB writes
                if now - last_progress_commit < 0.5:
                    return
                history.symbols_processed = processed
                history.symbols_affordable = total
                history.status = "RUNNING"
                try:
                    db.commit()
                    last_progress_commit = now
                except Exception:
                    db.rollback()

            result = run_scan(params, cancel_event=cancel_event, progress_cb=progress_cb)
            signals = result.get("signals", [])

            # Persist signals for this scan
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
                    scan_id=scan_id,
                )
                db.add(db_signal)
            db.commit()

            sell_put_count = sum(1 for s in signals if s.get("status") == "SELL PUT")
            low_volatility_count = sum(1 for s in signals if s.get("status") == "LOW VOLATILITY")
            expensive_count = sum(1 for s in signals if s.get("status") == "EXPENSIVE")
            illiquid_count = sum(1 for s in signals if s.get("status") == "ILLIQUID")
            avg_apr = sum(s.get("apr", 0) for s in signals if s.get("apr")) / len(signals) if signals else 0
            max_apr = max((s.get("apr", 0) for s in signals if s.get("apr")), default=0)

            history.total_symbols = result.get("symbols_total") or len(signals)
            history.total_signals = len(signals)
            history.sell_put_count = sell_put_count
            history.low_volatility_count = low_volatility_count
            history.expensive_count = expensive_count
            history.illiquid_count = illiquid_count
            history.avg_apr = avg_apr
            history.max_apr = max_apr
            history.symbols_total = result.get("symbols_total")
            history.symbols_priced = result.get("symbols_priced")
            history.symbols_affordable = result.get("symbols_affordable")
            history.symbols_processed = result.get("symbols_processed")
            history.status = "CANCELLED" if cancel_event.is_set() else "COMPLETED"
            if history.total_signals == 0:
                history.message = "Aucun signal trouvé — essayez d'élargir vos critères"
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
        except Exception as e:
            try:
                history.status = "FAILED"
                history.message = str(e)
                db.commit()
            except Exception:
                pass
        finally:
            db.close()
            self.jobs.pop(scan_id, None)
