from datetime import UTC, datetime, timedelta

import pytest

from tradebot.risk.killswitch import KillLevel, KillSwitch
from tradebot.watchdog.controller import KillFileController
from tradebot.watchdog.health import HealthMonitor, HealthState
from tradebot.watchdog.recovery import FlappingDetector, RestartLimiter


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_health_monitor_aggregates_failed_and_degraded_components() -> None:
    monitor = HealthMonitor()
    monitor.report("feed", HealthState.HEALTHY, score=100, checked_at=NOW)
    monitor.report("database", HealthState.DEGRADED, score=60, detail="slow", checked_at=NOW)
    overall = monitor.overall()
    assert overall.state is HealthState.DEGRADED
    assert overall.score == 80

    monitor.report("database", HealthState.FAILED, score=0, checked_at=NOW)
    assert monitor.overall().state is HealthState.FAILED


def test_restart_limiter_caps_three_attempts_per_hour() -> None:
    limiter = RestartLimiter()
    for index in range(3):
        limiter.record_restart("strategy", now=NOW + timedelta(minutes=index))
    assert not limiter.can_restart("strategy", now=NOW + timedelta(minutes=4))
    with pytest.raises(RuntimeError, match="limit reached"):
        limiter.record_restart("strategy", now=NOW + timedelta(minutes=4))
    assert limiter.can_restart("strategy", now=NOW + timedelta(hours=1))


def test_flapping_detector_escalates_after_five_changes() -> None:
    detector = FlappingDetector()
    results = [
        detector.record_change("feed", now=NOW + timedelta(minutes=index))
        for index in range(6)
    ]
    assert results[:5] == [False] * 5
    assert results[5]


def test_kill_file_triggers_persistent_flatten(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "state.sqlite3")
    kill_file = tmp_path / "KILL"
    try:
        kill_file.write_text("operator emergency", encoding="utf-8")
        assert KillFileController(switch, kill_file).check()
        assert switch.level is KillLevel.FLATTEN
        assert switch.reason == "operator emergency"
    finally:
        switch.close()
