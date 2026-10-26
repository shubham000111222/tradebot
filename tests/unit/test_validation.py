from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradebot.backtest.engine import BacktestResult, BacktestTrade
from tradebot.backtest.experiments import ExperimentTracker
from tradebot.backtest.metrics import calculate_metrics
from tradebot.backtest.montecarlo import simulate_trades
from tradebot.backtest.validation import AcceptanceGates, evaluate_gates
from tradebot.backtest.walkforward import walk_forward


def trade(pnl: str, index: int) -> BacktestTrade:
    timestamp = datetime(2026, 1, 1 + index, tzinfo=UTC)
    return BacktestTrade(
        strategy="test",
        entry_time=timestamp,
        exit_time=timestamp,
        entry_price=Decimal("100"),
        exit_price=Decimal("100"),
        quantity=Decimal("1"),
        fees=Decimal("0.1"),
        pnl=Decimal(pnl),
        exit_reason="target",
    )


def test_walk_forward_windows_do_not_overlap_train_and_test() -> None:
    windows = walk_forward(list(range(10)), train_size=4, test_size=2)
    assert [(window.train, window.test) for window in windows] == [
        ((0, 1, 2, 3), (4, 5)),
        ((2, 3, 4, 5), (6, 7)),
        ((4, 5, 6, 7), (8, 9)),
    ]


def test_metrics_and_monte_carlo_are_deterministic() -> None:
    trades = (trade("10", 0), trade("-5", 1), trade("10", 2))
    result = BacktestResult(
        starting_cash=Decimal("1000"),
        ending_cash=Decimal("1015"),
        equity_curve=(Decimal("1000"), Decimal("1010"), Decimal("1005"), Decimal("1015")),
        trades=trades,
    )
    metrics = calculate_metrics(result)
    summary = simulate_trades(trades, starting_cash=Decimal("1000"), iterations=20, seed=7)

    assert metrics.trade_count == 3
    assert metrics.fees_paid == Decimal("0.3")
    assert summary == simulate_trades(trades, starting_cash=Decimal("1000"), iterations=20, seed=7)


def test_acceptance_gates_explain_failed_validation() -> None:
    result = BacktestResult(Decimal("1000"), Decimal("1000"), (Decimal("1000"),), ())
    metrics = calculate_metrics(result)
    decision = evaluate_gates(metrics, AcceptanceGates(minimum_trades=1))
    assert not decision.passed
    assert "sharpe" in decision.failures


def test_experiment_tracker_locks_final_holdout(tmp_path) -> None:
    tracker = ExperimentTracker(tmp_path / "experiments.sqlite3")
    try:
        run_id = tracker.start(
            strategy="test",
            parameters={"period": 20},
            data_hash="abc",
            cost_model="default-v1",
            split="holdout",
            seed=42,
            holdout=True,
        )
        tracker.finish(run_id, {"sharpe": Decimal("1.2")})
        with pytest.raises(ValueError, match="holdout is locked"):
            tracker.start(
                strategy="test",
                parameters={},
                data_hash="abc",
                cost_model="default-v1",
                split="holdout",
                seed=43,
                holdout=True,
            )
    finally:
        tracker.close()
