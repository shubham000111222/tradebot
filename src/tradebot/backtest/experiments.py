"""Reproducible SQLite experiment log with final-holdout protection."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from tradebot.core.clock import utc_now


class ExperimentTracker:
    def __init__(self, path: str | Path = "state/experiments.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS experiments(" 
            "run_id TEXT PRIMARY KEY, strategy TEXT NOT NULL, parameters TEXT NOT NULL, "
            "data_hash TEXT NOT NULL, cost_model TEXT NOT NULL, split TEXT NOT NULL, "
            "seed INTEGER NOT NULL, metrics TEXT, notes TEXT NOT NULL, holdout INTEGER NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def start(
        self,
        *,
        strategy: str,
        parameters: dict[str, object],
        data_hash: str,
        cost_model: str,
        split: str,
        seed: int,
        notes: str = "",
        holdout: bool = False,
    ) -> str:
        if holdout and self._holdout_used(strategy):
            raise ValueError("final holdout is locked for this strategy")
        run_id = str(uuid4())
        with self.connection:
            self.connection.execute(
                "INSERT INTO experiments VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
                (
                    run_id,
                    strategy,
                    json.dumps(parameters, sort_keys=True, default=str),
                    data_hash,
                    cost_model,
                    split,
                    seed,
                    notes,
                    int(holdout),
                    utc_now().isoformat(),
                ),
            )
        return run_id

    def finish(self, run_id: str, metrics: dict[str, Decimal | int | float]) -> None:
        with self.connection:
            updated = self.connection.execute(
                "UPDATE experiments SET metrics = ? WHERE run_id = ?",
                (json.dumps(metrics, sort_keys=True, default=str), run_id),
            ).rowcount
        if updated != 1:
            raise KeyError(f"unknown experiment run: {run_id}")

    def _holdout_used(self, strategy: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM experiments WHERE strategy = ? AND holdout = 1 LIMIT 1", (strategy,)
        ).fetchone()
        return row is not None
