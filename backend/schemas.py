"""Pydantic schemas for API requests/responses."""

from datetime import datetime, date
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
    volume: Optional[int] = None
    spread: Optional[float] = None
    apr: Optional[float] = None
    contract_price: Optional[float] = None
    max_profit: Optional[float] = None
    distance_to_strike_pct: Optional[float] = None
    is_itm: Optional[bool] = None
    status: str
    contracts: Optional[int] = None
    budget_used: Optional[float] = None
    max_budget_per_trade: Optional[float] = None
    earnings_date: Optional[str] = None
    scan_id: Optional[str] = None


class SignalCreate(SignalBase):
    expiration: str


class SignalResponse(SignalBase):
    id: int
    expiration: str
    created_at: datetime

    class Config:
        from_attributes = True


class PositionBase(BaseModel):
    symbol: str
    position_type: str  # SELL PUT / SELL CALL
    status: str  # OPEN / CLOSED_EARLY / EXPIRED_WORTHLESS / ASSIGNED
    strike: float
    dte_open: int
    expiration_date: date
    premium_received: float
    contracts: int
    capital_required: float
    opened_at: datetime
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    expired_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    pnl_net: Optional[float] = None
    days_to_expiration: Optional[int] = None
    expires_soon: Optional[bool] = None
    trigger_sell_call: Optional[bool] = None
    motif_annulation: Optional[str] = None
    snooze_until: Optional[date] = None


class PositionCreate(BaseModel):
    symbol: str
    position_type: str  # SELL PUT / SELL CALL
    strike: float
    dte_open: int
    expiration_date: date
    premium_received: float
    contracts: int
    opened_at: Optional[datetime] = None


class PositionUpdate(BaseModel):
    status: str
    closed_at: Optional[datetime] = None
    close_price: Optional[float] = None
    expired_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    motif_annulation: Optional[str] = None
    snooze_until: Optional[date] = None


class PositionLegBase(BaseModel):
    position_id: int
    leg_type: str
    strike: float
    premium_received: float
    dte: Optional[int] = None
    expiration_date: Optional[date] = None
    opened_at: Optional[datetime] = None
    status: Optional[str] = "OPEN"


class PositionLegCreate(BaseModel):
    leg_type: str
    strike: float
    premium_received: float
    dte: Optional[int] = None
    expiration_date: Optional[date] = None
    opened_at: Optional[datetime] = None


class PositionLegResponse(PositionLegBase):
    id: int

    class Config:
        from_attributes = True


class PositionResponse(PositionBase):
    id: int

    class Config:
        from_attributes = True


class ScanHistoryResponse(BaseModel):
    id: int
    scan_date: datetime
    total_symbols: int
    total_signals: int
    scan_id: Optional[str] = None
    status: Optional[str] = None
    params_json: Optional[str] = None
    message: Optional[str] = None
    sell_put_count: int
    low_volatility_count: int
    expensive_count: int
    illiquid_count: int
    avg_apr: Optional[float]
    max_apr: Optional[float]
    duration_seconds: Optional[float]
    symbols_total: Optional[int]
    symbols_priced: Optional[int]
    symbols_affordable: Optional[int]
    symbols_processed: Optional[int]

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


class ScanRequest(BaseModel):
    capital: Optional[float] = None
    delta_target: Optional[float] = None
    min_dte: Optional[int] = None
    max_dte: Optional[int] = None
    min_iv: Optional[float] = None
    min_apr: Optional[float] = None


class ScanRunResponse(BaseModel):
    scan_id: str
    status: str


class ScanResultsResponse(BaseModel):
    scan_id: str
    status: str
    message: Optional[str] = None
    results: list[SignalResponse]
    statistics: Optional[ScanHistoryResponse] = None


class SymbolHistoryResponse(BaseModel):
    scan_date: datetime
    symbol: str
    price: float
    strike: float
    dte: int
    apr: Optional[float]


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


class AssignedCallSuggestion(BaseModel):
    position_id: int
    symbol: str
    assigned_at: datetime
    put_strike: float
    contracts: int
    shares: int
    premium_put: float
    total_premiums: float
    cost_basis_adjusted: float
    reduction_pct: float
    spot_price: Optional[float] = None
    status: str
    message: Optional[str] = None
    suggested_calls: Optional[list[dict]] = None
    legs: Optional[list[dict]] = None
    snooze_until: Optional[date] = None
