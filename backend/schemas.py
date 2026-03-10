"""Pydantic schemas for API requests/responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SignalBase(BaseModel):
    symbol: str
    price: float
    strike: float
    dte: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    delta: Optional[float] = None
    iv: Optional[float] = None
    open_interest: Optional[int] = None
    apr: Optional[float] = None
    status: str


class SignalCreate(SignalBase):
    expiration: str


class SignalResponse(SignalBase):
    id: int
    expiration: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScanHistoryResponse(BaseModel):
    id: int
    scan_date: datetime
    total_symbols: int
    total_signals: int
    sell_put_count: int
    low_volatility_count: int
    expensive_count: int
    illiquid_count: int
    avg_apr: Optional[float]
    max_apr: Optional[float]
    duration_seconds: Optional[float]

    class Config:
        from_attributes = True


class FilterParams(BaseModel):
    status: Optional[str] = None
    min_apr: Optional[float] = None
    max_apr: Optional[float] = None
    min_iv: Optional[float] = None
    min_dte: Optional[int] = None
    max_dte: Optional[int] = None
    sort_by: Optional[str] = "apr"  # apr, dte, iv, delta
    sort_order: Optional[str] = "desc"  # asc, desc


class StatisticsResponse(BaseModel):
    total_signals: int
    total_scannable: int
    by_status: dict  # {status: count}
    avg_apr: float
    max_apr: float
    min_apr: float


class AlertResponse(BaseModel):
    id: int
    symbol: str
    apr: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
