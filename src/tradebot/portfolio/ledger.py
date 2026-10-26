"""SQLite WAL ledger with Decimal-safe balances, fills and positions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tradebot.core.clock import require_utc, utc_now
from tradebot.core.models import Fill, OrderSide, Position


class Ledger:
    def __init__(
        self,
        path: str | Path = "state/paper.sqlite3",
        *,
        initial_cash_usdt: Decimal = Decimal("1000"),
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()
        if self._get_balance("USDT") is None:
            self._set_balance("USDT", initial_cash_usdt)
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def cash(self, asset: str = "USDT") -> Decimal:
        return self._get_balance(asset.upper()) or Decimal("0")

    def position(self, symbol: str) -> Position:
        row = self.connection.execute(
            "SELECT quantity, average_entry_price, realized_pnl, unrealized_pnl, updated_at "
            "FROM positions WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        if row is None:
            return Position(symbol=symbol.upper())
        return Position(
            symbol=symbol.upper(),
            quantity=Decimal(row[0]),
            average_entry_price=Decimal(row[1]) if row[1] is not None else None,
            realized_pnl=Decimal(row[2]),
            unrealized_pnl=Decimal(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
        )

    def record_fill(self, fill: Fill) -> Decimal:
        if self.connection.execute("SELECT 1 FROM fills WHERE id = ?", (fill.id,)).fetchone():
            return self.equity({fill.symbol: fill.price})
        _base, quote = fill.symbol.split("/")
        if fill.fee_currency != quote:
            raise ValueError("Week 3 ledger supports quote-currency fees only")
        current = self.position(fill.symbol)
        cash_before = self.cash(quote)
        notional = fill.price * fill.quantity
        average: Decimal | None
        if fill.side is OrderSide.BUY:
            required = notional + fill.fee
            if cash_before < required:
                raise ValueError("insufficient quote balance")
            cash_after = cash_before - required
            quantity = current.quantity + fill.quantity
            average = (
                (current.quantity * (current.average_entry_price or Decimal("0"))) + notional
            ) / quantity
            realized = current.realized_pnl
        else:
            if current.quantity < fill.quantity:
                raise ValueError("insufficient position quantity")
            cash_after = cash_before + notional - fill.fee
            quantity = current.quantity - fill.quantity
            average = current.average_entry_price if quantity > 0 else None
            realized = current.realized_pnl + (
                (fill.price - (current.average_entry_price or Decimal("0"))) * fill.quantity
            ) - fill.fee

        timestamp = require_utc(fill.timestamp).isoformat()
        with self.connection:
            self._set_balance(quote, cash_after)
            self.connection.execute(
                "INSERT INTO fills(id, order_id, symbol, side, quantity, price, fee, "
                "fee_currency, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fill.id,
                    fill.order_id,
                    fill.symbol,
                    fill.side.value,
                    str(fill.quantity),
                    str(fill.price),
                    str(fill.fee),
                    fill.fee_currency,
                    timestamp,
                ),
            )
            self.connection.execute(
                "INSERT INTO positions(symbol, quantity, average_entry_price, realized_pnl, "
                "unrealized_pnl, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET "
                "quantity=excluded.quantity, "
                "average_entry_price=excluded.average_entry_price, "
                "realized_pnl=excluded.realized_pnl, "
                "updated_at=excluded.updated_at",
                (
                    fill.symbol,
                    str(quantity),
                    str(average) if average is not None else None,
                    str(realized),
                    "0",
                    timestamp,
                ),
            )
            self._event("fill_recorded", fill.model_dump(mode="json"))
        equity = self.equity({fill.symbol: fill.price})
        if equity < 0:
            raise AssertionError("ledger equity cannot be negative")
        return equity

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        total = sum((value for _, value in self._balances()), Decimal("0"))
        for symbol, quantity, _average in self._position_rows():
            if quantity == 0:
                continue
            if symbol not in marks:
                raise ValueError(f"missing mark price for {symbol}")
            total += quantity * marks[symbol]
        return total

    def balances(self) -> dict[str, Decimal]:
        return {asset: amount for asset, amount in self._balances()}

    def positions(self) -> list[Position]:
        return [self.position(symbol) for symbol, _quantity, _average in self._position_rows()]

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS balances(asset TEXT PRIMARY KEY, amount TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS positions(
                symbol TEXT PRIMARY KEY, quantity TEXT NOT NULL,
                average_entry_price TEXT, realized_pnl TEXT NOT NULL,
                unrealized_pnl TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fills(
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL, symbol TEXT NOT NULL,
                side TEXT NOT NULL, quantity TEXT NOT NULL, price TEXT NOT NULL,
                fee TEXT NOT NULL, fee_currency TEXT NOT NULL, timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                payload TEXT NOT NULL, timestamp TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def _get_balance(self, asset: str) -> Decimal | None:
        row = self.connection.execute(
            "SELECT amount FROM balances WHERE asset = ?", (asset,)
        ).fetchone()
        return Decimal(row[0]) if row else None

    def _set_balance(self, asset: str, amount: Decimal) -> None:
        self.connection.execute(
            "INSERT INTO balances(asset, amount) VALUES (?, ?) "
            "ON CONFLICT(asset) DO UPDATE SET amount=excluded.amount",
            (asset.upper(), str(amount)),
        )

    def _balances(self) -> list[tuple[str, Decimal]]:
        return [
            (asset, Decimal(amount))
            for asset, amount in self.connection.execute("SELECT asset, amount FROM balances")
        ]

    def _position_rows(self) -> list[tuple[str, Decimal, Decimal | None]]:
        return [
            (symbol, Decimal(quantity), Decimal(average) if average is not None else None)
            for symbol, quantity, average in self.connection.execute(
                "SELECT symbol, quantity, average_entry_price FROM positions WHERE quantity != '0'"
            )
        ]

    def _event(self, event_type: str, payload: dict[str, object]) -> None:
        self.connection.execute(
            "INSERT INTO events(event_type, payload, timestamp) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload, default=str), utc_now().isoformat()),
        )
