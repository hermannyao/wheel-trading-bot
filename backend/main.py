"""FastAPI application entry point."""

import os
import json
import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import Signal, ScanHistory, Alert, get_db, init_db
from schemas import SignalResponse, FilterParams, StatisticsResponse, ScanHistoryResponse, AlertResponse
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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
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


# ============================================================================
# REST API ENDPOINTS
# ============================================================================

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


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


@app.post("/api/scan")
async def trigger_scan(db: Session = Depends(get_db)):
    """Trigger a new scan (will run async)."""
    # Import scanning logic
    try:
        from main_scan import run_scan
        
        # Run scan and get results
        signals = await asyncio.to_thread(run_scan)
        
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
                apr=sig.get("apr"),
                status=sig.get("status"),
                expiration=sig.get("expiration"),
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
        )
        db.add(history)
        db.commit()

        # Broadcast update
        await manager.broadcast({
            "type": "scan_complete",
            "total_signals": len(signals),
            "sell_put_count": sell_put_count,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return {
            "status": "success",
            "total_signals": len(signals),
            "sell_put_count": sell_put_count,
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
