"""Exchange adapter seam shared by paper, testnet and live implementations."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from pydantic import Field

from tradebot.core.models import DomainModel, Fill, Order
from tradebot.data.models import OrderBookSnapshot


class MarketRules(DomainModel):
    tick_size: Decimal = Field(gt=Decimal("0"))
    lot_size: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(gt=Decimal("0"))
    maker_fee: Decimal = Field(ge=Decimal("0"))
    taker_fee: Decimal = Field(ge=Decimal("0"))


class ExchangeAdapter(Protocol):
    """The only interface execution code may use for an exchange."""

    def place_order(self, order: Order) -> Order: ...

    def cancel_order(self, client_order_id: str) -> Order: ...

    def cancel_all(self, symbol: str | None = None) -> list[Order]: ...

    def get_order(self, client_order_id: str) -> Order | None: ...

    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...

    def get_balances(self) -> dict[str, Decimal]: ...

    def get_market_rules(self, symbol: str) -> MarketRules: ...


@runtime_checkable
class FillSource(Protocol):
    """Optional paper/replay hook for turning a market update into fills."""

    def process_market(self, snapshot: OrderBookSnapshot) -> list[Fill]: ...
