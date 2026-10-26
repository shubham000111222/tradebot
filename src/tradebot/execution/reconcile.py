"""Compare exchange state with the local ledger before resuming trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tradebot.core.clock import utc_now
from tradebot.execution.base import ExchangeAdapter
from tradebot.portfolio.ledger import Ledger


@dataclass(frozen=True)
class ReconciliationResult:
    clean: bool
    mismatches: tuple[str, ...]
    checked_at: datetime


class Reconciler:
    def __init__(self, ledger: Ledger, adapter: ExchangeAdapter) -> None:
        self.ledger = ledger
        self.adapter = adapter

    def check(self, expected_open_order_ids: set[str] | None = None) -> ReconciliationResult:
        mismatches: list[str] = []
        local_balances = self.ledger.balances()
        for position in self.ledger.positions():
            base_asset = position.symbol.split("/")[0]
            local_balances[base_asset] = position.quantity
        exchange_balances = self.adapter.get_balances()
        for asset in sorted(set(local_balances) | set(exchange_balances)):
            local = local_balances.get(asset, Decimal("0"))
            remote = exchange_balances.get(asset, Decimal("0"))
            if local != remote:
                mismatches.append(f"balance:{asset}:local={local}:exchange={remote}")

        if expected_open_order_ids is not None:
            remote_ids = {order.client_order_id for order in self.adapter.get_open_orders()}
            if remote_ids != expected_open_order_ids:
                mismatches.append(
                    f"open_orders:local={sorted(expected_open_order_ids)}:exchange={sorted(remote_ids)}"
                )
        return ReconciliationResult(not mismatches, tuple(mismatches), utc_now())
