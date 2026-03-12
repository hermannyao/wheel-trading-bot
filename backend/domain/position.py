from __future__ import annotations

from datetime import datetime, timezone

POSITION_STATUSES = {"OPEN", "CLOSED_EARLY", "EXPIRED_WORTHLESS", "ASSIGNED", "CANCELLED", "CLOSED"}
POSITION_TYPES = {"SELL PUT", "SELL CALL"}
ALLOWED_TRANSITIONS = {
    "OPEN": {"CLOSED_EARLY", "EXPIRED_WORTHLESS", "ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"CLOSED"},
}


def calc_position_fields(position) -> None:
    if position.status == "CANCELLED":
        position.capital_required = 0
        position.pnl_net = None
        position.days_to_expiration = None
        position.expires_soon = False
        position.trigger_sell_call = False
        return

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
