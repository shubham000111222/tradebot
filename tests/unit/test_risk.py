from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradebot.core.models import Order, OrderSide, OrderType
from tradebot.risk.engine import RiskContext, RiskEngine
from tradebot.risk.killswitch import KillLevel, KillSwitch
from tradebot.risk.limits import RiskLimits, load_risk_limits


def order(quantity: str = "0.1") -> Order:
    return Order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=quantity,
        price="100",
    )


def context(**overrides) -> RiskContext:
    values = {
        "equity": "1000",
        "data_timestamp": datetime.now(UTC),
        "spread_fraction": "0.001",
        "price": "100",
        "mid_price": "100",
        "stop_price": "99",
        "top_book_depth": "1",
    }
    values.update(overrides)
    return RiskContext.model_validate(values)


def test_default_limits_load_and_hard_bounds_apply() -> None:
    limits = load_risk_limits()
    assert limits.risk_per_trade == Decimal("0.005")
    with pytest.raises(ValidationError):
        RiskLimits(
            risk_per_trade="0.021",
            max_symbol_exposure="0.2",
            max_total_exposure="0.6",
            max_correlated_bucket_exposure="0.4",
            max_open_positions=5,
            daily_loss_limit="0.02",
            daily_flatten_limit="0.03",
            weekly_loss_limit="0.05",
            max_drawdown="0.1",
            max_capital_usdt="1000",
        )


def test_approved_order_passes_ordered_checks(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "state.sqlite3")
    try:
        decision = RiskEngine(load_risk_limits(), switch).evaluate(order(), context())
        assert decision.approved
        assert decision.reasons == ()
    finally:
        switch.close()


def test_kill_switch_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = KillSwitch(path)
    first.pause("manual pause")
    first.close()

    second = KillSwitch(path)
    try:
        assert second.level is KillLevel.PAUSE
        decision = RiskEngine(load_risk_limits(), second).evaluate(order(), context())
        assert decision.reasons == ("kill_switch_level_1",)
    finally:
        second.close()


def test_risk_engine_rejects_stale_data_before_later_checks(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "state.sqlite3")
    try:
        decision = RiskEngine(load_risk_limits(), switch).evaluate(
            order(), context(data_timestamp=datetime.now(UTC) - timedelta(seconds=16))
        )
        assert decision.reasons == ("stale_market_data",)
    finally:
        switch.close()


def test_risk_engine_triggers_flatten_at_daily_limit(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "state.sqlite3")
    try:
        decision = RiskEngine(load_risk_limits(), switch).evaluate(
            order(), context(daily_loss="0.03")
        )
        assert decision.reasons == ("daily_flatten_limit",)
        assert switch.level is KillLevel.FLATTEN
    finally:
        switch.close()


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("spread_fraction", "spread_too_wide"),
        ("symbol_enabled", "symbol_disabled"),
        ("total_exposure", "total_exposure_cap"),
        ("top_book_depth", "book_depth_cap"),
        ("orders_last_minute", "orders_per_minute_cap"),
    ],
)
def test_risk_engine_reports_specific_veto_reasons(tmp_path, field: str, expected: str) -> None:
    switch = KillSwitch(tmp_path / f"{field}.sqlite3")
    try:
        value = {
            "spread_fraction": "0.002",
            "symbol_enabled": False,
            "total_exposure": "0.6",
            "top_book_depth": "0.9",
            "orders_last_minute": 20,
        }[field]
        decision = RiskEngine(load_risk_limits(), switch).evaluate(
            order(), context(**{field: value})
        )
        assert decision.reasons == (expected,)
    finally:
        switch.close()
