"""Bounded restart and flapping controls."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from tradebot.core.clock import utc_now


class RestartLimiter:
    def __init__(self, *, maximum: int = 3, window: timedelta = timedelta(hours=1)) -> None:
        self.maximum = maximum
        self.window = window
        self._attempts: dict[str, deque[datetime]] = {}

    def can_restart(self, component: str, *, now: datetime | None = None) -> bool:
        timestamp = now or utc_now()
        attempts = self._attempts.setdefault(component, deque())
        self._prune(attempts, timestamp)
        return len(attempts) < self.maximum

    def record_restart(self, component: str, *, now: datetime | None = None) -> None:
        timestamp = now or utc_now()
        if not self.can_restart(component, now=timestamp):
            raise RuntimeError(f"restart limit reached for {component}")
        self._attempts.setdefault(component, deque()).append(timestamp)

    def attempts(self, component: str, *, now: datetime | None = None) -> int:
        timestamp = now or utc_now()
        attempts = self._attempts.setdefault(component, deque())
        self._prune(attempts, timestamp)
        return len(attempts)

    def _prune(self, attempts: deque[datetime], now: datetime) -> None:
        while attempts and now - attempts[0] >= self.window:
            attempts.popleft()


class FlappingDetector:
    def __init__(
        self, *, maximum_changes: int = 5, window: timedelta = timedelta(minutes=10)
    ) -> None:
        self.maximum_changes = maximum_changes
        self.window = window
        self._changes: dict[str, deque[datetime]] = {}

    def record_change(self, component: str, *, now: datetime | None = None) -> bool:
        timestamp = now or utc_now()
        changes = self._changes.setdefault(component, deque())
        while changes and timestamp - changes[0] >= self.window:
            changes.popleft()
        changes.append(timestamp)
        return len(changes) > self.maximum_changes
