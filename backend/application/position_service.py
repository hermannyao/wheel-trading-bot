from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException

from domain.position import (
    POSITION_STATUSES,
    POSITION_TYPES,
    ALLOWED_TRANSITIONS,
    calc_position_fields,
)
from database import Position


class PositionService:
    def __init__(self, db):
        self.db = db

    def list_positions(self):
        positions = self.db.query(Position).order_by(Position.opened_at.desc()).all()
        for position in positions:
            calc_position_fields(position)
        self.db.commit()
        return positions

    def create_position(self, payload):
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
        calc_position_fields(position)
        self.db.add(position)
        self.db.commit()
        self.db.refresh(position)
        return position

    def update_position(self, position_id: int, payload):
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status == "CANCELLED":
            raise HTTPException(status_code=409, detail="Cancelled positions are immutable")

        if payload.status not in POSITION_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")

        if position.status == payload.status:
            return position

        allowed = ALLOWED_TRANSITIONS.get(position.status, set())
        if payload.status not in allowed:
            raise HTTPException(status_code=409, detail="Invalid status transition")

        if payload.status == "CANCELLED":
            if payload.motif_annulation not in {"erreur_de_saisie", "trade_non_execute"}:
                raise HTTPException(
                    status_code=422,
                    detail="motif_annulation required (erreur_de_saisie or trade_non_execute)",
                )
            position.motif_annulation = payload.motif_annulation
        elif payload.status == "CLOSED_EARLY":
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
        calc_position_fields(position)
        self.db.commit()
        self.db.refresh(position)
        return position

    def delete_position(self, position_id: int):
        raise HTTPException(
            status_code=410,
            detail="Delete disabled. Use cancellation with motif instead.",
        )
