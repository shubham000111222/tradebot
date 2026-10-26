"""SQLite-persistent kill switch state machine."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path

from tradebot.core.clock import utc_now


class KillLevel(IntEnum):
    NORMAL = 0
    PAUSE = 1
    FLATTEN = 2
    LOCKDOWN = 3


class KillSwitch:
    def __init__(self, path: str | Path = "state/paper.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS kill_switch(
                id INTEGER PRIMARY KEY CHECK(id = 1), level INTEGER NOT NULL,
                reason TEXT NOT NULL, updated_at TEXT NOT NULL,
                cooldown_until TEXT
            );
            CREATE TABLE IF NOT EXISTS kill_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, level INTEGER NOT NULL,
                reason TEXT NOT NULL, timestamp TEXT NOT NULL
            );
            """
        )
        if self.connection.execute("SELECT 1 FROM kill_switch WHERE id = 1").fetchone() is None:
            self.connection.execute(
                "INSERT INTO kill_switch VALUES (1, ?, ?, ?, NULL)",
                (KillLevel.NORMAL, "startup", utc_now().isoformat()),
            )
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    @property
    def level(self) -> KillLevel:
        row = self.connection.execute("SELECT level FROM kill_switch WHERE id = 1").fetchone()
        assert row is not None
        return KillLevel(row[0])

    @property
    def reason(self) -> str:
        row = self.connection.execute("SELECT reason FROM kill_switch WHERE id = 1").fetchone()
        assert row is not None
        return str(row[0])

    def trigger(self, level: KillLevel, reason: str) -> KillLevel:
        if level < self.level:
            return self.level
        self._set(level, reason, None)
        return level

    def pause(self, reason: str) -> KillLevel:
        return self.trigger(KillLevel.PAUSE, reason)

    def flatten(self, reason: str) -> KillLevel:
        return self.trigger(KillLevel.FLATTEN, reason)

    def lockdown(self, reason: str) -> KillLevel:
        cooldown = utc_now() + timedelta(hours=1)
        self._set(KillLevel.LOCKDOWN, reason, cooldown)
        return KillLevel.LOCKDOWN

    def reset(self, reason: str) -> KillLevel:
        if self.level is KillLevel.LOCKDOWN:
            row = self.connection.execute(
                "SELECT cooldown_until FROM kill_switch WHERE id = 1"
            ).fetchone()
            cooldown = datetime.fromisoformat(row[0]) if row and row[0] else None
            if cooldown is not None and utc_now() < cooldown:
                raise ValueError("lockdown cooldown has not elapsed")
        self._set(KillLevel.NORMAL, reason, None)
        return KillLevel.NORMAL

    def _set(self, level: KillLevel, reason: str, cooldown: datetime | None) -> None:
        timestamp = utc_now().isoformat()
        with self.connection:
            self.connection.execute(
                "UPDATE kill_switch SET level = ?, reason = ?, updated_at = ?, "
                "cooldown_until = ? WHERE id = 1",
                (int(level), reason, timestamp, cooldown.isoformat() if cooldown else None),
            )
            self.connection.execute(
                "INSERT INTO kill_events(level, reason, timestamp) VALUES (?, ?, ?)",
                (int(level), reason, timestamp),
            )
