"""Partitioned Parquet market-data storage with DuckDB query support."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast

from tradebot.data.models import OrderBookSnapshot, TradeTick


class MarketDataStore:
    """Write append-only batches under symbol/date partitions."""

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)

    def append_ticks(self, ticks: list[TradeTick]) -> Path:
        if not ticks:
            raise ValueError("cannot store an empty tick batch")
        self._require_same_partition(ticks)
        partition = self._partition("ticks", ticks[0].symbol, ticks[0].timestamp.date())
        rows: list[dict[str, object]] = [
            {
                "symbol": tick.symbol,
                "trade_id": tick.trade_id,
                "timestamp": tick.timestamp.isoformat(),
                "price": str(tick.price),
                "quantity": str(tick.quantity),
                "is_buyer_maker": tick.is_buyer_maker,
            }
            for tick in ticks
        ]
        self._append_rows(partition, rows)
        return partition

    def append_order_books(self, snapshots: list[OrderBookSnapshot]) -> Path:
        if not snapshots:
            raise ValueError("cannot store an empty order-book batch")
        if any(snapshot.symbol != snapshots[0].symbol for snapshot in snapshots):
            raise ValueError("a batch must contain one symbol")
        if any(
            snapshot.timestamp.date() != snapshots[0].timestamp.date()
            for snapshot in snapshots
        ):
            raise ValueError("a batch must contain one UTC date")
        partition = self._partition(
            "order_books", snapshots[0].symbol, snapshots[0].timestamp.date()
        )
        rows: list[dict[str, object]] = [
            {
                "symbol": snapshot.symbol,
                "timestamp": snapshot.timestamp.isoformat(),
                "bids": str([(str(level.price), str(level.quantity)) for level in snapshot.bids]),
                "asks": str([(str(level.price), str(level.quantity)) for level in snapshot.asks]),
                "best_bid": str(snapshot.best_bid),
                "best_ask": str(snapshot.best_ask),
                "spread_fraction": str(snapshot.spread_fraction),
            }
            for snapshot in snapshots
        ]
        self._append_rows(partition, rows)
        return partition

    def query(self, sql: str) -> list[tuple[Any, ...]]:
        """Run a read-only DuckDB query against the store."""
        import duckdb  # type: ignore[import-not-found]

        with duckdb.connect() as connection:
            return cast(list[tuple[Any, ...]], connection.execute(sql).fetchall())

    def _partition(self, kind: str, symbol: str, day: date) -> Path:
        path = self.root / kind / f"symbol={symbol.replace('/', '_')}" / f"date={day.isoformat()}"
        path.mkdir(parents=True, exist_ok=True)
        return path / "part-000.parquet"

    @staticmethod
    def _append_rows(path: Path, rows: list[dict[str, object]]) -> None:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        new_table = pa.Table.from_pylist(rows)
        if path.exists():
            old_table = pq.read_table(path)
            new_table = pa.concat_tables([old_table, new_table], promote_options="default")
        pq.write_table(new_table, path, compression="zstd")

    @staticmethod
    def _require_same_partition(records: list[TradeTick]) -> None:
        if any(tick.symbol != records[0].symbol for tick in records):
            raise ValueError("a batch must contain one symbol")
        if any(tick.timestamp.date() != records[0].timestamp.date() for tick in records):
            raise ValueError("a batch must contain one UTC date")
