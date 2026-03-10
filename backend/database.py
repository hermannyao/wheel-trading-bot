"""Database models and configuration for Wheel Trading Bot."""

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, create_engine
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
    apr = Column(Float, nullable=True)
    status = Column(String)  # SELL PUT, LOW VOLATILITY, EXPENSIVE, ILLIQUID
    expiration = Column(String)
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
