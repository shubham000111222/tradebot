"""Deterministic spot paper exchange using live/replayed order books."""

from __future__ import annotations

from decimal import Decimal

from tradebot.core.clock import utc_now
from tradebot.core.models import Fill, Order, OrderSide, OrderStatus, OrderType
from tradebot.core.money import quantize_step
from tradebot.data.models import OrderBookLevel, OrderBookSnapshot
from tradebot.execution.base import MarketRules


DEFAULT_RULES = MarketRules(
    tick_size=Decimal("0.01"),
    lot_size=Decimal("0.00001"),
    min_notional=Decimal("10"),
    maker_fee=Decimal("0.001"),
    taker_fee=Decimal("0.001"),
)


class PaperExchange:
    """Long-only paper adapter with book walking and idempotent client IDs."""

    def __init__(
        self,
        balances: dict[str, Decimal] | None = None,
        rules: dict[str, MarketRules] | None = None,
    ) -> None:
        self._balances = {
            asset.upper(): Decimal(str(amount))
            for asset, amount in (balances or {"USDT": Decimal("1000")}).items()
        }
        self._rules = {symbol.upper(): value for symbol, value in (rules or {}).items()}
        self._orders: dict[str, Order] = {}
        self._books: dict[str, OrderBookSnapshot] = {}

    def place_order(self, order: Order) -> Order:
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            if existing.symbol != order.symbol or existing.quantity != order.quantity:
                raise ValueError("client order ID was reused for a different order")
            return existing

        rules = self.get_market_rules(order.symbol)
        self._validate_order(order, rules)
        submitted = order.model_copy(
            update={"status": OrderStatus.SUBMITTED, "updated_at": utc_now()}
        )
        self._orders[submitted.client_order_id] = submitted
        return submitted

    def cancel_order(self, client_order_id: str) -> Order:
        order = self._require_order(client_order_id)
        if order.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED}:
            return order
        canceled = order.model_copy(
            update={"status": OrderStatus.CANCELED, "updated_at": utc_now()}
        )
        self._orders[client_order_id] = canceled
        return canceled

    def cancel_all(self, symbol: str | None = None) -> list[Order]:
        return [
            self.cancel_order(order.client_order_id)
            for order in self.get_open_orders(symbol)
        ]

    def get_order(self, client_order_id: str) -> Order | None:
        return self._orders.get(client_order_id)

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        return [
            order
            for order in self._orders.values()
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
            and (symbol is None or order.symbol == symbol.upper())
        ]

    def get_balances(self) -> dict[str, Decimal]:
        return self._balances.copy()

    def get_market_rules(self, symbol: str) -> MarketRules:
        return self._rules.get(symbol.upper(), DEFAULT_RULES)

    def process_market(self, snapshot: OrderBookSnapshot) -> list[Fill]:
        self._books[snapshot.symbol] = snapshot
        fills: list[Fill] = []
        for order in list(self.get_open_orders(snapshot.symbol)):
            levels = self._eligible_levels(order, snapshot)
            remaining = order.quantity - order.filled_quantity
            for level in levels:
                if remaining <= 0:
                    break
                quantity = min(remaining, level.quantity)
                if not self._can_afford(order.side, snapshot.symbol, quantity, level.price):
                    break
                fee_rate = (
                    self.get_market_rules(order.symbol).taker_fee
                    if order.type is OrderType.MARKET
                    else self.get_market_rules(order.symbol).maker_fee
                )
                fee = level.price * quantity * fee_rate
                fill = Fill(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=quantity,
                    price=level.price,
                    fee=fee,
                    fee_currency=order.symbol.split("/")[1],
                    timestamp=snapshot.timestamp,
                )
                fills.append(fill)
                self._apply_fill(fill)
                remaining -= quantity
                order = self._orders[order.client_order_id]
            if order.filled_quantity == order.quantity:
                status = OrderStatus.FILLED
            elif order.filled_quantity > 0:
                status = OrderStatus.PARTIALLY_FILLED
            else:
                continue
            self._orders[order.client_order_id] = order.model_copy(
                update={"status": status, "updated_at": utc_now()}
            )
        return fills

    def _eligible_levels(
        self, order: Order, snapshot: OrderBookSnapshot
    ) -> tuple[OrderBookLevel, ...]:
        levels = snapshot.asks if order.side is OrderSide.BUY else snapshot.bids
        levels = tuple(
            sorted(levels, key=lambda level: level.price, reverse=order.side is OrderSide.SELL)
        )
        if order.type is OrderType.MARKET:
            return levels
        if order.price is None:
            return ()
        if order.side is OrderSide.BUY:
            return tuple(level for level in levels if level.price < order.price)
        return tuple(level for level in levels if level.price > order.price)

    def _apply_fill(self, fill: Fill) -> None:
        base, quote = fill.symbol.split("/")
        notional = fill.price * fill.quantity
        if fill.side is OrderSide.BUY:
            self._balances[quote] -= notional + fill.fee
            self._balances[base] = self._balances.get(base, Decimal("0")) + fill.quantity
        else:
            self._balances[base] -= fill.quantity
            self._balances[quote] = self._balances.get(quote, Decimal("0")) + notional - fill.fee
        if self._balances[base] < 0 or self._balances[quote] < 0:
            raise RuntimeError("paper exchange produced a negative balance")

        order = next(order for order in self._orders.values() if order.id == fill.order_id)
        self._orders[order.client_order_id] = order.model_copy(
            update={"filled_quantity": order.filled_quantity + fill.quantity}
        )

    def _can_afford(self, side: OrderSide, symbol: str, quantity: Decimal, price: Decimal) -> bool:
        base, quote = symbol.split("/")
        fee = self.get_market_rules(symbol).taker_fee
        if side is OrderSide.BUY:
            return self._balances.get(quote, Decimal("0")) >= price * quantity * (
                Decimal("1") + fee
            )
        return self._balances.get(base, Decimal("0")) >= quantity

    def _validate_order(self, order: Order, rules: MarketRules) -> None:
        rounded_price = order.price and quantize_step(order.price, rules.tick_size)
        rounded_quantity = quantize_step(order.quantity, rules.lot_size)
        if rounded_quantity != order.quantity or (
            order.price is not None and rounded_price != order.price
        ):
            raise ValueError("order does not conform to market tick or lot size")
        if order.price is not None and order.price * order.quantity < rules.min_notional:
            raise ValueError("order is below minimum notional")

    def _require_order(self, client_order_id: str) -> Order:
        order = self._orders.get(client_order_id)
        if order is None:
            raise KeyError(f"unknown client order ID: {client_order_id}")
        return order
