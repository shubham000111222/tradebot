"""Ordered, explainable pre-trade risk evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from tradebot.core.clock import utc_now
from tradebot.core.models import Order, OrderSide
from tradebot.risk.killswitch import KillLevel, KillSwitch
from tradebot.risk.limits import RiskLimits


class RiskContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equity: Decimal = Field(gt=Decimal("0"))
    data_timestamp: datetime
    symbol_enabled: bool = True
    spread_fraction: Decimal = Field(ge=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    mid_price: Decimal = Field(gt=Decimal("0"))
    stop_price: Decimal = Field(gt=Decimal("0"))
    symbol_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    total_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    correlated_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    open_positions: int = Field(default=0, ge=0)
    top_book_depth: Decimal = Field(gt=Decimal("0"))
    daily_loss: Decimal = Decimal("0")
    weekly_loss: Decimal = Decimal("0")
    drawdown: Decimal = Decimal("0")
    symbol_cooldown_until: datetime | None = None
    orders_last_minute: int = Field(default=0, ge=0)
    orders_today: int = Field(default=0, ge=0)


class RiskDecision(BaseModel):
    approved: bool
    reasons: tuple[str, ...]
    checked_at: datetime


class RiskEngine:
    def __init__(self, limits: RiskLimits, kill_switch: KillSwitch) -> None:
        self.limits = limits
        self.kill_switch = kill_switch

    def evaluate(
        self, order: Order, context: RiskContext, *, now: datetime | None = None
    ) -> RiskDecision:
        current_time = now or utc_now()
        reasons: list[str] = []
        checks = (
            self._check_kill_switch,
            self._check_mode_side,
            self._check_data_freshness,
            self._check_symbol,
            self._check_spread,
            self._check_fat_finger,
            self._check_notional,
            self._check_trade_risk,
            self._check_exposure,
            self._check_position_count,
            self._check_book_depth,
            self._check_losses,
            self._check_cooldown,
            self._check_order_caps,
        )
        for check in checks:
            reason = check(order, context, current_time)
            if reason is not None:
                reasons.append(reason)
                break
        return RiskDecision(approved=not reasons, reasons=tuple(reasons), checked_at=current_time)

    def _check_kill_switch(
        self, _order: Order, _context: RiskContext, _now: datetime
    ) -> str | None:
        return (
            f"kill_switch_level_{self.kill_switch.level}"
            if self.kill_switch.level is not KillLevel.NORMAL
            else None
        )

    @staticmethod
    def _check_mode_side(order: Order, _context: RiskContext, _now: datetime) -> str | None:
        return "shorting_not_supported" if order.side is OrderSide.SELL else None

    @staticmethod
    def _check_data_freshness(_order: Order, context: RiskContext, now: datetime) -> str | None:
        return "stale_market_data" if now - context.data_timestamp > timedelta(seconds=15) else None

    @staticmethod
    def _check_symbol(_order: Order, context: RiskContext, _now: datetime) -> str | None:
        return None if context.symbol_enabled else "symbol_disabled"

    @staticmethod
    def _check_spread(_order: Order, context: RiskContext, _now: datetime) -> str | None:
        return "spread_too_wide" if context.spread_fraction >= Decimal("0.0015") else None

    @staticmethod
    def _check_fat_finger(_order: Order, context: RiskContext, _now: datetime) -> str | None:
        outside_band = (
            abs(context.price - context.mid_price) / context.mid_price > Decimal("0.01")
        )
        return "price_outside_mid_band" if outside_band else None

    def _check_notional(self, order: Order, context: RiskContext, _now: datetime) -> str | None:
        notional = (order.price or context.price) * order.quantity
        if notional < Decimal("10"):
            return "below_min_notional"
        if notional > context.equity * self.limits.max_symbol_exposure:
            return "symbol_notional_cap"
        return None

    def _check_trade_risk(self, order: Order, context: RiskContext, _now: datetime) -> str | None:
        entry = order.price or context.price
        risk = (entry - context.stop_price) * order.quantity
        return "risk_per_trade_cap" if risk > context.equity * self.limits.risk_per_trade else None

    def _check_exposure(self, order: Order, context: RiskContext, _now: datetime) -> str | None:
        notional = (order.price or context.price) * order.quantity
        if context.total_exposure + notional / context.equity > self.limits.max_total_exposure:
            return "total_exposure_cap"
        if (
            context.correlated_exposure + notional / context.equity
            > self.limits.max_correlated_bucket_exposure
        ):
            return "correlated_exposure_cap"
        return None

    def _check_position_count(
        self, _order: Order, context: RiskContext, _now: datetime
    ) -> str | None:
        return (
            "max_open_positions"
            if context.open_positions >= self.limits.max_open_positions
            else None
        )

    @staticmethod
    def _check_book_depth(order: Order, context: RiskContext, _now: datetime) -> str | None:
        return (
            "book_depth_cap"
            if order.quantity > context.top_book_depth * Decimal("0.10")
            else None
        )

    def _check_losses(self, _order: Order, context: RiskContext, _now: datetime) -> str | None:
        if context.drawdown >= self.limits.max_drawdown:
            self.kill_switch.lockdown("maximum_drawdown")
            return "maximum_drawdown"
        if context.weekly_loss >= self.limits.weekly_loss_limit:
            return "weekly_loss_limit"
        if context.daily_loss >= self.limits.daily_flatten_limit:
            self.kill_switch.flatten("daily_flatten_limit")
            return "daily_flatten_limit"
        if context.daily_loss >= self.limits.daily_loss_limit:
            return "daily_loss_limit"
        return None

    @staticmethod
    def _check_cooldown(_order: Order, context: RiskContext, now: datetime) -> str | None:
        active = context.symbol_cooldown_until and now < context.symbol_cooldown_until
        return "symbol_cooldown" if active else None

    @staticmethod
    def _check_order_caps(_order: Order, context: RiskContext, _now: datetime) -> str | None:
        if context.orders_last_minute >= 20:
            return "orders_per_minute_cap"
        return "orders_per_day_cap" if context.orders_today >= 500 else None
