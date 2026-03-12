from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException

from domain.position import (
    POSITION_STATUSES,
    POSITION_TYPES,
    ALLOWED_TRANSITIONS,
    calc_position_fields,
)
from database import Position, PositionLeg


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
        leg = PositionLeg(
            position_id=position.id,
            leg_type=position.position_type,
            strike=position.strike,
            premium_received=position.premium_received,
            dte=position.dte_open,
            expiration_date=position.expiration_date,
            opened_at=position.opened_at,
            status="OPEN",
        )
        self.db.add(leg)
        self.db.commit()
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

    def list_legs(self, position_id: int):
        return (
            self.db.query(PositionLeg)
            .filter(PositionLeg.position_id == position_id)
            .order_by(PositionLeg.opened_at.asc())
            .all()
        )

    def create_leg(self, position_id: int, payload):
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        if position.status != "ASSIGNED":
            raise HTTPException(status_code=409, detail="Only ASSIGNED positions can add call legs")
        if payload.leg_type not in {"SELL CALL"}:
            raise HTTPException(status_code=422, detail="Invalid leg_type")
        existing_open = (
            self.db.query(PositionLeg)
            .filter(
                PositionLeg.position_id == position_id,
                PositionLeg.leg_type == "SELL CALL",
                PositionLeg.status == "OPEN",
            )
            .first()
        )
        if existing_open:
            raise HTTPException(
                status_code=409,
                detail="Un Call est déjà ouvert sur ce cycle.",
            )
        leg = PositionLeg(
            position_id=position_id,
            leg_type=payload.leg_type,
            strike=payload.strike,
            premium_received=payload.premium_received,
            dte=payload.dte,
            expiration_date=payload.expiration_date,
            opened_at=payload.opened_at or datetime.now(timezone.utc),
            status="OPEN",
        )
        self.db.add(leg)
        self.db.commit()
        self.db.refresh(leg)
        return leg

    def snooze_position(self, position_id: int, snooze_until):
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        if position.status != "ASSIGNED":
            raise HTTPException(status_code=409, detail="Only ASSIGNED positions can be snoozed")
        position.snooze_until = snooze_until
        self.db.commit()
        self.db.refresh(position)
        return position

    def _load_position_and_leg(self, position_id: int, call_id: int):
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        leg = (
            self.db.query(PositionLeg)
            .filter(PositionLeg.id == call_id, PositionLeg.position_id == position_id)
            .first()
        )
        if not leg:
            raise HTTPException(status_code=404, detail="Call leg not found")
        if leg.leg_type != "SELL CALL":
            raise HTTPException(status_code=422, detail="Not a CALL leg")
        if leg.status != "OPEN":
            raise HTTPException(status_code=409, detail="Call leg is not open")
        return position, leg

    def _get_position_legs(self, position_id: int):
        return (
            self.db.query(PositionLeg)
            .filter(PositionLeg.position_id == position_id)
            .order_by(PositionLeg.opened_at.asc())
            .all()
        )

    def _total_premiums(self, position: Position, legs: list[PositionLeg]) -> float:
        call_premiums = sum(l.premium_received for l in legs if l.leg_type == "SELL CALL")
        buybacks = sum(
            l.buyback_premium or 0 for l in legs if l.leg_type == "SELL CALL" and l.status == "BOUGHT_BACK"
        )
        return (position.premium_received or 0) + call_premiums - buybacks

    def call_close_impact(self, position_id: int, call_id: int, scenario: str, buyback_premium: float | None):
        position, leg = self._load_position_and_leg(position_id, call_id)
        legs = self._get_position_legs(position_id)
        total_premiums = self._total_premiums(position, legs)
        cost_basis = (position.strike or 0) - total_premiums

        if scenario == "bought_back" and buyback_premium is None:
            raise HTTPException(status_code=422, detail="buyback_premium required")
        if scenario not in {"expired", "exerced", "bought_back"}:
            raise HTTPException(status_code=422, detail="Invalid scenario")

        total_after = total_premiums
        new_cost_basis = cost_basis
        pnl_total = None
        pnl_pct = None
        delivery_price = None
        capital_initial = (position.strike or 0) * 100 * position.contracts

        if scenario == "bought_back":
            total_after = total_premiums - float(buyback_premium or 0)
            new_cost_basis = (position.strike or 0) - total_after
        elif scenario == "exerced":
            delivery_price = leg.strike
            pnl_total = (delivery_price - cost_basis) * 100 * position.contracts
            pnl_pct = (pnl_total / capital_initial) * 100 if capital_initial else 0

        return {
            "current_cost_basis": round(cost_basis, 4),
            "new_cost_basis": round(new_cost_basis, 4),
            "total_premiums": round(total_premiums, 4),
            "total_premiums_after": round(total_after, 4),
            "pnl_total": round(pnl_total, 2) if pnl_total is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "delivery_price": delivery_price,
            "capital_initial": capital_initial,
        }

    def close_call_leg(self, position_id: int, call_id: int, payload):
        position, leg = self._load_position_and_leg(position_id, call_id)

        scenario = payload.scenario
        close_date = payload.close_date or datetime.now(timezone.utc).date()
        if scenario == "expired":
            leg.status = "EXPIRED"
        elif scenario == "exerced":
            leg.status = "EXERCISED"
            position.status = "CLOSED"
            position.closed_at = datetime.combine(close_date, datetime.min.time(), tzinfo=timezone.utc)
        elif scenario == "bought_back":
            if payload.buyback_premium is None:
                raise HTTPException(status_code=422, detail="buyback_premium required")
            leg.status = "BOUGHT_BACK"
            leg.buyback_premium = payload.buyback_premium
        else:
            raise HTTPException(status_code=422, detail="Invalid scenario")

        leg.closed_at = datetime.combine(close_date, datetime.min.time(), tzinfo=timezone.utc)
        self.db.commit()
        self.db.refresh(leg)
        return leg
