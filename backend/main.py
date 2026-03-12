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

# In-memory cache for symbol metadata
_SYMBOL_INFO_CACHE: dict[str, dict] = {}
_SYMBOL_INFO_TS: dict[str, float] = {}
_SYMBOL_INFO_TTL_SECONDS = 60 * 60 * 12

# Position rules
POSITION_STATUSES = {"OPEN", "CLOSED_EARLY", "EXPIRED_WORTHLESS", "ASSIGNED"}
POSITION_TYPES = {"SELL PUT", "SELL CALL"}
ALLOWED_TRANSITIONS = {
    "OPEN": {"CLOSED_EARLY", "EXPIRED_WORTHLESS", "ASSIGNED"},
}


def _calc_position_fields(position: Position) -> None:
    capital_required = position.strike * 100 * position.contracts
    position.capital_required = capital_required

    today = datetime.now(timezone.utc).date()
    if position.expiration_date:
        position.days_to_expiration = (position.expiration_date - today).days
    else:
        position.days_to_expiration = None

    position.expires_soon = (
        position.status == "OPEN"
        and position.days_to_expiration is not None
        and position.days_to_expiration <= 5
    )

    position.trigger_sell_call = position.status == "ASSIGNED"

    if position.status == "CLOSED_EARLY":
        position.pnl_net = (
            (position.premium_received * 100 * position.contracts)
            - (position.close_price or 0) * 100 * position.contracts
        )
    elif position.status == "EXPIRED_WORTHLESS":
        position.pnl_net = position.premium_received * 100 * position.contracts
    elif position.status == "ASSIGNED":
        position.pnl_net = position.premium_received * 100 * position.contracts
    else:
        position.pnl_net = None


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


@app.get("/api/scan/results", response_model=List[SignalResponse])
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
    db: Session = Depends(get_db),
):
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


@app.post("/api/scan/run")
async def run_scan_alias(scan_request: ScanRequest | None = None, db: Session = Depends(get_db)):
    return await trigger_scan(scan_request=scan_request, db=db)


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
    positions = db.query(Position).order_by(desc(Position.opened_at)).all()
    for position in positions:
        _calc_position_fields(position)
    db.commit()
    return positions


@app.post("/api/positions", response_model=PositionResponse)
async def create_position(payload: PositionCreate, db: Session = Depends(get_db)):
    if payload.position_type not in POSITION_TYPES:
        raise HTTPException(status_code=422, detail="Invalid position_type")
    opened_at = payload.opened_at or datetime.now(timezone.utc)
    position = Position(
        symbol=payload.symbol,
        position_type=payload.position_type,
        status="OPEN",
        strike=payload.strike,
        dte_open=payload.dte_open,
        expiration_date=payload.expiration_date,
        premium_received=payload.premium_received,
        contracts=payload.contracts,
        capital_required=0,
        opened_at=opened_at,
    )
    _calc_position_fields(position)
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


@app.patch("/api/positions/{position_id}", response_model=PositionResponse)
async def update_position(position_id: int, payload: PositionUpdate, db: Session = Depends(get_db)):
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if payload.status not in POSITION_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")

    if position.status == payload.status:
        return position

    allowed = ALLOWED_TRANSITIONS.get(position.status, set())
    if payload.status not in allowed:
        raise HTTPException(status_code=409, detail="Invalid status transition")

    if payload.status == "CLOSED_EARLY":
        if not payload.closed_at or payload.close_price is None:
            raise HTTPException(status_code=422, detail="closed_at and close_price required")
        position.closed_at = payload.closed_at
        position.close_price = payload.close_price
    elif payload.status == "EXPIRED_WORTHLESS":
        if not payload.expired_at:
            raise HTTPException(status_code=422, detail="expired_at required")
        position.expired_at = payload.expired_at
    elif payload.status == "ASSIGNED":
        if not payload.assigned_at:
            raise HTTPException(status_code=422, detail="assigned_at required")
        position.assigned_at = payload.assigned_at

    position.status = payload.status
    _calc_position_fields(position)
    db.commit()
    db.refresh(position)
    return position


@app.delete("/api/positions/{position_id}")
async def delete_position(position_id: int, db: Session = Depends(get_db)):
    position = db.query(Position).filter(Position.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    if position.status != "OPEN":
        raise HTTPException(status_code=409, detail="Only OPEN positions can be deleted")
    db.delete(position)
    db.commit()
    return {"status": "deleted"}


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


@app.post("/api/scan")
async def trigger_scan(scan_request: ScanRequest | None = None, db: Session = Depends(get_db)):
    """Trigger a new scan (will run async)."""
    # Import scanning logic
    try:
        from main_scan import run_scan
        overrides = (scan_request.model_dump(exclude_none=True) if scan_request else {})

        # Run scan and get results
        scan_result = await asyncio.to_thread(run_scan, overrides)
        signals = scan_result.get("signals", [])
        
        # Clear old signals and insert new ones
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

        # Create scan history record
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

        # Broadcast update
        await manager.broadcast({
            "type": "scan_complete",
            "total_signals": len(signals),
            "sell_put_count": sell_put_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "success",
            "total_signals": len(signals),
            "sell_put_count": sell_put_count,
            "symbols_total": scan_result.get("symbols_total"),
            "symbols_priced": scan_result.get("symbols_priced"),
            "symbols_affordable": scan_result.get("symbols_affordable"),
        }
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
