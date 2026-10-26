"""Idempotent order lifecycle coordination."""

from __future__ import annotations

from tradebot.core.models import Fill, Order, OrderStatus
from tradebot.data.models import OrderBookSnapshot
from tradebot.execution.base import ExchangeAdapter, FillSource


class OrderManager:
    def __init__(self, adapter: ExchangeAdapter) -> None:
        self.adapter = adapter
        self._orders: dict[str, Order] = {}

    def submit(self, order: Order) -> Order:
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            return existing
        submitted = self.adapter.place_order(order)
        self._orders[submitted.client_order_id] = submitted
        return submitted

    def cancel(self, client_order_id: str) -> Order:
        canceled = self.adapter.cancel_order(client_order_id)
        self._orders[client_order_id] = canceled
        return canceled

    def cancel_all(self, symbol: str | None = None) -> list[Order]:
        canceled = self.adapter.cancel_all(symbol)
        for order in canceled:
            self._orders[order.client_order_id] = order
        return canceled

    def process_market(self, snapshot: OrderBookSnapshot) -> list[Fill]:
        if not isinstance(self.adapter, FillSource):
            raise TypeError("adapter does not support market processing")
        fills = self.adapter.process_market(snapshot)
        for fill in fills:
            order = self._orders.get(next(
                client_id
                for client_id, tracked in self._orders.items()
                if tracked.id == fill.order_id
            ))
            if order is None:
                raise RuntimeError(f"fill received for unknown order: {fill.order_id}")
            updated_quantity = order.filled_quantity + fill.quantity
            status = (
                OrderStatus.FILLED
                if updated_quantity == order.quantity
                else OrderStatus.PARTIALLY_FILLED
            )
            self._orders[order.client_order_id] = order.model_copy(
                update={"filled_quantity": updated_quantity, "status": status}
            )
        return fills

    def open_orders(self) -> list[Order]:
        return [
            order
            for order in self._orders.values()
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        ]
