from decimal import Decimal

from dashboard.app import dashboard_snapshot
from tradebot.portfolio.ledger import Ledger
from tradebot.risk.killswitch import KillSwitch
from tradebot.runtime.paper import PaperRuntime, synthetic_demo_candles
from tradebot.strategies.breakout import BreakoutStrategy


def test_paper_runtime_connects_strategy_risk_execution_and_ledger(tmp_path) -> None:
    state_path = tmp_path / "demo.sqlite3"
    runtime = PaperRuntime(state_path)
    try:
        result = runtime.run(synthetic_demo_candles(), BreakoutStrategy())
        assert len(result.signals) == 1
        assert len(result.fills) == 1
        assert not result.rejections
        assert result.ending_equity == Decimal("999.989")
    finally:
        runtime.close()


def test_demo_state_reset_makes_repeated_runs_isolated(tmp_path) -> None:
    state_path = tmp_path / "demo.sqlite3"
    PaperRuntime.reset_state(state_path)
    first = PaperRuntime(state_path)
    try:
        first_result = first.run(synthetic_demo_candles(), BreakoutStrategy())
    finally:
        first.close()

    PaperRuntime.reset_state(state_path)
    second = PaperRuntime(state_path)
    try:
        second_result = second.run(synthetic_demo_candles(), BreakoutStrategy())
    finally:
        second.close()

    assert first_result.ending_equity == second_result.ending_equity == Decimal("999.989")


def test_dashboard_snapshot_is_read_only_and_serializable(tmp_path) -> None:
    state_path = tmp_path / "dashboard.sqlite3"
    ledger = Ledger(state_path)
    kill_switch = KillSwitch(state_path)
    try:
        snapshot = dashboard_snapshot(ledger, kill_switch, {})
        assert snapshot["balances"] == {"USDT": "1000"}
        assert snapshot["kill_level"] == 0
    finally:
        ledger.close()
        kill_switch.close()
