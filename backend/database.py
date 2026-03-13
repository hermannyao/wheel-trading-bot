"""Database models and configuration for Wheel Trading Bot."""

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, Integer, Float, String, DateTime, Date, Boolean, ForeignKey, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()

# Database URL from environment or default SQLite file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wheel_bot.db")

# SQLite specific configuration
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

# Create engine and session factory
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Signal(Base):
    """Represents a trading signal (put option opportunity)."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    price = Column(Float)
    strike = Column(Float)
    dte = Column(Integer)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)
    iv = Column(Float, nullable=True)
    open_interest = Column(Integer, nullable=True)
    volume = Column(Integer, nullable=True)
    spread = Column(Float, nullable=True)
    apr = Column(Float, nullable=True)
    contract_price = Column(Float, nullable=True)
    max_profit = Column(Float, nullable=True)
    distance_to_strike_pct = Column(Float, nullable=True)
    is_itm = Column(Integer, nullable=True)
    status = Column(String)  # SELL PUT, LOW VOLATILITY, EXPENSIVE, ILLIQUID
    expiration = Column(String)
    contracts = Column(Integer, nullable=True)
    budget_used = Column(Float, nullable=True)
    max_budget_per_trade = Column(Float, nullable=True)
    earnings_date = Column(String, nullable=True)
    scan_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanHistory(Base):
    """Tracks each scan execution."""
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True, index=True)
    scan_date = Column(DateTime, default=datetime.utcnow, index=True)
    total_symbols = Column(Integer)
    total_signals = Column(Integer)
    sell_put_count = Column(Integer, default=0)
    low_volatility_count = Column(Integer, default=0)
    expensive_count = Column(Integer, default=0)
    illiquid_count = Column(Integer, default=0)
    avg_apr = Column(Float, nullable=True)
    max_apr = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    scan_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=True)
    params_json = Column(String, nullable=True)
    message = Column(String, nullable=True)
    symbols_total = Column(Integer, nullable=True)
    symbols_priced = Column(Integer, nullable=True)
    symbols_affordable = Column(Integer, nullable=True)
    symbols_processed = Column(Integer, nullable=True)


class SignalHistory(Base):
    """Snapshot of signals per scan for trend analysis."""
    __tablename__ = "signal_history"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scan_history.id"), index=True)
    scan_date = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String, index=True)
    price = Column(Float)
    strike = Column(Float)
    dte = Column(Integer)
    apr = Column(Float, nullable=True)


class Position(Base):
    """Represents an opened Wheel position."""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    position_type = Column(String, nullable=False)  # SELL PUT / SELL CALL
    status = Column(String, nullable=False)  # OPEN / CLOSED_EARLY / EXPIRED_WORTHLESS / ASSIGNED
    strike = Column(Float, nullable=False)
    dte_open = Column(Integer, nullable=False)
    expiration_date = Column(Date, nullable=False)
    premium_received = Column(Float, nullable=False)  # per contract premium (real)
    contracts = Column(Integer, nullable=False)
    capital_required = Column(Float, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    closed_at = Column(DateTime, nullable=True)
    close_price = Column(Float, nullable=True)
    expired_at = Column(DateTime, nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    pnl_net = Column(Float, nullable=True)
    days_to_expiration = Column(Integer, nullable=True)
    expires_soon = Column(Boolean, default=False)
    trigger_sell_call = Column(Boolean, default=False)
    motif_annulation = Column(String, nullable=True)
    snooze_until = Column(Date, nullable=True)
    ignore_calls = Column(Boolean, default=False)


class PositionLeg(Base):
    """Represents a leg within a Wheel cycle."""
    __tablename__ = "position_legs"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), index=True)
    leg_type = Column(String, nullable=False)  # SELL PUT / SELL CALL
    strike = Column(Float, nullable=False)
    premium_received = Column(Float, nullable=False)
    dte = Column(Integer, nullable=True)
    expiration_date = Column(Date, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, nullable=False, default="OPEN")  # OPEN / EXPIRED / EXERCISED / BOUGHT_BACK
    closed_at = Column(DateTime, nullable=True)
    buyback_premium = Column(Float, nullable=True)


class Alert(Base):
    """Alert for high-opportunity signals."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), index=True)
    symbol = Column(String)
    status = Column(String)  # PENDING, SENT, DISMISSED
    apr = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI routes to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_column("positions", "ignore_calls", "BOOLEAN DEFAULT 0")


def _ensure_column(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
