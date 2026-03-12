"""FastAPI application entry point."""

import os
import json
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import yfinance as yf
import pandas_market_calendars as mcal

from database import Signal, ScanHistory, SignalHistory, Alert, Position, get_db, init_db
from application.position_service import PositionService
from infrastructure.scan_runner import ScanRunner
from config import (
    SP500_SOURCE_URL,
    SP500_LOCAL_FILE,
    MIN_DTE,
    MAX_DTE,
    TARGET_OTM_PCT,
    MIN_OPEN_INTEREST,
    MIN_IV,
    MIN_APR,
    DELTA_MIN,
    DELTA_MAX,
    MAX_SPREAD_PCT,
    MAX_WORKERS,
    RISK_FREE_RATE,
    MAX_BUDGET_PER_TRADE,
    MAX_TOTAL_BUDGET,
)
from schemas import (
    SignalResponse,
    FilterParams,
    StatisticsResponse,
    ScanHistoryResponse,
    AlertResponse,
    ScanRequest,
    SymbolHistoryResponse,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    ScanRunResponse,
    ScanResultsResponse,
)
from logging_config import setup_logging

# Load environment variables
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
BACKEND_DEBUG = os.getenv("BACKEND_DEBUG", "false").lower() == "true"

# Logger setup
logger = setup_logging(__name__, LOG_LEVEL)

# FastAPI app
app = FastAPI(
    title="Wheel Trading Bot API",
    description="Real-time options scanner for the Wheel strategy",
    version="1.0.0",
    debug=BACKEND_DEBUG
)

# CORS middleware - Restricted to specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")


manager = ConnectionManager()
scan_runner = ScanRunner()

# In-memory cache for symbol metadata
_SYMBOL_INFO_CACHE: dict[str, dict] = {}
_SYMBOL_INFO_TS: dict[str, float] = {}
_SYMBOL_INFO_TTL_SECONDS = 60 * 60 * 12



# ============================================================================
# REST API ENDPOINTS
# ============================================================================

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/signals", response_model=List[SignalResponse])
async def get_signals(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    min_apr: Optional[float] = None,
    max_apr: Optional[float] = None,
    min_iv: Optional[float] = None,
    min_dte: Optional[int] = None,
    max_dte: Optional[int] = None,
    sort_by: str = Query("apr"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    """Retrieve signals with filtering and sorting."""
    query = db.query(Signal)

    if status:
        query = query.filter(Signal.status == status)
    if symbol:
        query = query.filter(Signal.symbol.ilike(f"%{symbol}%"))
    if min_apr is not None:
        query = query.filter(Signal.apr >= min_apr)
    if max_apr is not None:
        query = query.filter(Signal.apr <= max_apr)
    if min_iv is not None:
        query = query.filter(Signal.iv >= min_iv)
    if min_dte is not None:
        query = query.filter(Signal.dte >= min_dte)
    if max_dte is not None:
        query = query.filter(Signal.dte <= max_dte)

    # Filters
    if sort_by not in {"apr", "dte", "iv", "delta", "price", "strike", "open_interest", "created_at"}:
        sort_by = "apr"

    # Sorting
    sort_column = getattr(Signal, sort_by, Signal.apr)
    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    total = query.count()
    signals = query.offset(offset).limit(limit).all()

    return signals


def _build_signal_query(
    db: Session,
    status: Optional[str],
    symbol: Optional[str],
    min_apr: Optional[float],
    max_apr: Optional[float],
    min_iv: Optional[float],
    min_dte: Optional[int],
    max_dte: Optional[int],
    scan_id: Optional[str] = None,
):
    query = db.query(Signal)
    if scan_id:
        query = query.filter(Signal.scan_id == scan_id)

    if status:
        query = query.filter(Signal.status == status)
    if symbol:
        query = query.filter(Signal.symbol.ilike(f"%{symbol}%"))
    if min_apr is not None:
        query = query.filter(Signal.apr >= min_apr)
    if max_apr is not None:
        query = query.filter(Signal.apr <= max_apr)
    if min_iv is not None:
        query = query.filter(Signal.iv >= min_iv)
    if min_dte is not None:
        query = query.filter(Signal.dte >= min_dte)
    if max_dte is not None:
        query = query.filter(Signal.dte <= max_dte)

    return query


@app.get("/api/scan/results", response_model=ScanResultsResponse | List[SignalResponse])
async def get_scan_results(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    min_apr: Optional[float] = None,
    max_apr: Optional[float] = None,
    min_iv: Optional[float] = None,
    min_dte: Optional[int] = None,
    max_dte: Optional[int] = None,
    sort_by: str = Query("apr"),
    sort_order: str = Query("desc"),
    scan_id: Optional[str] = None,
    latest: bool = Query(False),
    db: Session = Depends(get_db),
):
    if scan_id or latest:
        history = None
        resolved_scan_id = scan_id
        if not resolved_scan_id:
            history = db.query(ScanHistory).order_by(desc(ScanHistory.scan_date)).first()
            if not history:
                return {
                    "scan_id": "",
                    "status": "IDLE",
                    "message": "Aucun scan lancé",
                    "results": [],
                    "statistics": None,
                }
            resolved_scan_id = history.scan_id or str(history.id)

        if not history:
            history = db.query(ScanHistory).filter(ScanHistory.scan_id == resolved_scan_id).first()

        if not history:
            raise HTTPException(status_code=404, detail="Scan not found")

        query = _build_signal_query(
            db,
            status=status,
            symbol=symbol,
            min_apr=min_apr,
            max_apr=max_apr,
            min_iv=min_iv,
            min_dte=min_dte,
            max_dte=max_dte,
            scan_id=history.scan_id,
        )

        if sort_by not in {"apr", "dte", "iv", "delta", "price", "strike", "open_interest", "created_at"}:
            sort_by = "apr"

        sort_column = getattr(Signal, sort_by, Signal.apr)
        if sort_order.lower() == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        results = query.offset(offset).limit(limit).all()
        return {
            "scan_id": history.scan_id or resolved_scan_id,
            "status": history.status or "UNKNOWN",
            "message": history.message,
            "results": results,
            "statistics": history,
        }

    return await get_signals(
        limit=limit,
        offset=offset,
        status=status,
        symbol=symbol,
        min_apr=min_apr,
        max_apr=max_apr,
        min_iv=min_iv,
        min_dte=min_dte,
        max_dte=max_dte,
        sort_by=sort_by,
        sort_order=sort_order,
        db=db,
    )


@app.get("/api/signals/{symbol}", response_model=SignalResponse)
async def get_signal_by_symbol(symbol: str, db: Session = Depends(get_db)):
    """Get latest signal for a symbol."""
    signal = db.query(Signal).filter(Signal.symbol == symbol).order_by(desc(Signal.created_at)).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@app.get("/api/statistics", response_model=StatisticsResponse)
async def get_statistics(db: Session = Depends(get_db)):
    """Get aggregated statistics."""
    total = db.query(Signal).count()
    
    # Count by status
    by_status = {s: 0 for s in ["SELL PUT", "LOW VOLATILITY", "EXPENSIVE", "ILLIQUID"]}
    grouped = db.query(Signal.status, func.count(Signal.id)).group_by(Signal.status).all()
    for status, count in grouped:
        by_status[status] = count

    # APR stats
    apr_data = db.query(
        func.avg(Signal.apr).label("avg"),
        func.max(Signal.apr).label("max"),
        func.min(Signal.apr).label("min")
    ).filter(Signal.apr.isnot(None)).first()

    return {
        "total_signals": total,
        "total_scannable": by_status.get("SELL PUT", 0),
        "by_status": by_status,
        "avg_apr": apr_data.avg or 0,
        "max_apr": apr_data.max or 0,
        "min_apr": apr_data.min or 0,
    }


@app.get("/api/scan-history", response_model=List[ScanHistoryResponse])
async def get_scan_history(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """Get recent scan history."""
    scans = db.query(ScanHistory).order_by(desc(ScanHistory.scan_date)).limit(limit).all()
    return scans


@app.get("/api/scan/history", response_model=List[ScanHistoryResponse])
async def get_scan_history_alias(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return await get_scan_history(limit=limit, db=db)


@app.post("/api/scan/run", response_model=ScanRunResponse, status_code=202)
async def run_scan_alias(scan_request: ScanRequest | None = None):
    overrides = (scan_request.model_dump(exclude_none=True) if scan_request else {})
    scan_id = scan_runner.start(overrides)
    return {"scan_id": scan_id, "status": "RUNNING"}


@app.get("/api/market/status")
async def get_market_status():
    """Return US market status (ET) without holiday calendar."""
    now = datetime.now(ZoneInfo("America/New_York"))
    weekday = now.weekday()  # 0=Mon
    is_weekend = weekday >= 5
    is_trading_day = True
    try:
        nyse = mcal.get_calendar("NYSE")
        schedule = nyse.schedule(start_date=now.date(), end_date=now.date())
        is_trading_day = not schedule.empty
    except Exception:
        is_trading_day = True

    pre_open = dt_time(4, 0)
    regular_open = dt_time(9, 30)
    regular_close = dt_time(16, 0)
    after_close = dt_time(20, 0)

    status = "closed"
    label = "Ferme"
    if is_weekend:
        status = "closed"
        label = "Ferme (week-end)"
    elif not is_trading_day:
        status = "closed"
        label = "Ferme (ferie)"
    else:
        current_time = now.time()
        if pre_open <= current_time < regular_open:
            status = "pre"
            label = "Pre-market"
        elif regular_open <= current_time < regular_close:
            status = "open"
            label = "Ouvert"
        elif regular_close <= current_time < after_close:
            status = "after"
            label = "After-hours"

    return {
        "status": status,
        "label": label,
        "et_time": now.strftime("%H:%M"),
        "et_date": now.strftime("%Y-%m-%d"),
        "session": "09:30 - 16:00 ET",
        "pre_market": "04:00 - 09:30 ET",
        "after_hours": "16:00 - 20:00 ET",
    }


@app.get("/api/positions", response_model=List[PositionResponse])
async def list_positions(db: Session = Depends(get_db)):
    service = PositionService(db)
    return service.list_positions()


@app.post("/api/positions", response_model=PositionResponse)
async def create_position(payload: PositionCreate, db: Session = Depends(get_db)):
    service = PositionService(db)
    return service.create_position(payload)


@app.patch("/api/positions/{position_id}", response_model=PositionResponse)
async def update_position(position_id: int, payload: PositionUpdate, db: Session = Depends(get_db)):
    service = PositionService(db)
    return service.update_position(position_id, payload)


@app.delete("/api/positions/{position_id}")
async def delete_position(position_id: int, db: Session = Depends(get_db)):
    service = PositionService(db)
    return service.delete_position(position_id)


@app.get("/api/positions/export")
async def export_positions(db: Session = Depends(get_db)):
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "symbol",
        "position_type",
        "status",
        "motif_annulation",
        "strike",
        "dte_open",
        "expiration_date",
        "premium_received",
        "contracts",
        "capital_required",
        "opened_at",
        "closed_at",
        "close_price",
        "expired_at",
        "assigned_at",
        "pnl_net",
        "days_to_expiration",
        "expires_soon",
        "trigger_sell_call",
    ])
    positions = db.query(Position).order_by(desc(Position.opened_at)).all()
    for p in positions:
        writer.writerow([
            p.id,
            p.symbol,
            p.position_type,
            p.status,
            p.motif_annulation,
            p.strike,
            p.dte_open,
            p.expiration_date,
            p.premium_received,
            p.contracts,
            p.capital_required,
            p.opened_at,
            p.closed_at,
            p.close_price,
            p.expired_at,
            p.assigned_at,
            p.pnl_net,
            p.days_to_expiration,
            p.expires_soon,
            p.trigger_sell_call,
        ])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=positions.csv"},
    )


@app.get("/api/symbol-history/{symbol}", response_model=List[SymbolHistoryResponse])
async def get_symbol_history(symbol: str, limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    history = (
        db.query(SignalHistory)
        .filter(SignalHistory.symbol == symbol)
        .order_by(desc(SignalHistory.scan_date))
        .limit(limit)
        .all()
    )
    return history


@app.get("/api/scan-config")
async def get_scan_config():
    """Expose current scan criteria for UI display."""
    return {
        "sp500_source_url": SP500_SOURCE_URL,
        "sp500_local_file": SP500_LOCAL_FILE,
        "min_dte": MIN_DTE,
        "max_dte": MAX_DTE,
        "target_otm_pct": TARGET_OTM_PCT,
        "min_open_interest": MIN_OPEN_INTEREST,
        "min_iv": MIN_IV,
        "min_apr": MIN_APR,
        "delta_min": DELTA_MIN,
        "delta_max": DELTA_MAX,
        "max_spread_pct": MAX_SPREAD_PCT,
        "max_workers": MAX_WORKERS,
        "risk_free_rate": RISK_FREE_RATE,
        "max_budget_per_trade": MAX_BUDGET_PER_TRADE,
        "max_total_budget": MAX_TOTAL_BUDGET,
    }


def _fetch_symbol_info(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info = {}
        try:
            fast = getattr(ticker, "fast_info", None)
            if fast:
                info["exchange"] = fast.get("exchange") or fast.get("fullExchangeName")
        except Exception:
            pass
        try:
            full = ticker.get_info()
            info["name"] = full.get("longName") or full.get("shortName")
            info["exchange"] = info.get("exchange") or full.get("exchange") or full.get("fullExchangeName")
            info["currency"] = full.get("currency")
        except Exception:
            pass
        return info
    except Exception:
        return {}


@app.get("/api/symbols-info")
async def get_symbols_info(symbols: str = Query("", max_length=2000)):
    """Fetch and cache symbol metadata (name/exchange)."""
    if not symbols:
        return {}
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    now = time.time()
    result: dict[str, dict] = {}
    to_fetch: list[str] = []
    for sym in requested:
        ts = _SYMBOL_INFO_TS.get(sym)
        if ts and (now - ts) < _SYMBOL_INFO_TTL_SECONDS:
            cached = _SYMBOL_INFO_CACHE.get(sym)
            if cached:
                result[sym] = cached
                continue
        to_fetch.append(sym)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_symbol_info, sym): sym for sym in to_fetch}
            for future in as_completed(futures):
                sym = futures[future]
                info = future.result() or {}
                _SYMBOL_INFO_CACHE[sym] = info
                _SYMBOL_INFO_TS[sym] = now
                result[sym] = info

    return result


@app.post("/api/scan", response_model=ScanRunResponse, status_code=202)
async def trigger_scan(scan_request: ScanRequest | None = None):
    """Trigger a new scan (async)."""
    overrides = (scan_request.model_dump(exclude_none=True) if scan_request else {})
    scan_id = scan_runner.start(overrides)
    return {"scan_id": scan_id, "status": "RUNNING"}


@app.delete("/api/scan/cancel")
async def cancel_scan(scan_id: str = Query(..., min_length=1)):
    """Cancel an in-flight scan."""
    if scan_runner.cancel(scan_id):
        return {"scan_id": scan_id, "status": "CANCEL_REQUESTED"}
    raise HTTPException(status_code=404, detail="Scan not found")


@app.get("/api/alerts", response_model=List[AlertResponse])
async def get_alerts(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Get alerts."""
    query = db.query(Alert)
    if status:
        query = query.filter(Alert.status == status)
    alerts = query.order_by(desc(Alert.created_at)).limit(50).all()
    return alerts


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle commands
            logger.info(f"Received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Application started")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Application shutdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
