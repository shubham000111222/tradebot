"""FIFO tax-record ledger for spot sales.

The rates are configuration defaults from the build plan, not tax advice. Verify
current Indian rules before using real-money records.
"""

from __future__ import annotations

import csv
import io
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field


class TaxLedgerEntry(BaseModel):
    trade_date: date
    asset: str
    quantity: Decimal = Field(gt=Decimal("0"))
    cost_basis: Decimal = Field(ge=Decimal("0"))
    sale_value: Decimal = Field(gt=Decimal("0"))
    fees: Decimal = Field(ge=Decimal("0"))
    gain: Decimal
    tds: Decimal = Field(ge=Decimal("0"))
    tax_reserve: Decimal = Field(ge=Decimal("0"))


@dataclass
class _Lot:
    quantity: Decimal
    unit_cost: Decimal


class TaxLedger:
    def __init__(
        self,
        *,
        gain_tax_rate: Decimal = Decimal("0.30"),
        tds_rate: Decimal = Decimal("0.01"),
    ) -> None:
        if not (Decimal("0") <= gain_tax_rate <= Decimal("1")):
            raise ValueError("gain_tax_rate must be between 0 and 1")
        if not (Decimal("0") <= tds_rate <= Decimal("1")):
            raise ValueError("tds_rate must be between 0 and 1")
        self.gain_tax_rate = gain_tax_rate
        self.tds_rate = tds_rate
        self._lots: dict[str, deque[_Lot]] = {}
        self.entries: list[TaxLedgerEntry] = []

    def buy(self, *, trade_date: date, asset: str, quantity: Decimal, total_cost: Decimal) -> None:
        if quantity <= 0 or total_cost < 0:
            raise ValueError("buy quantity must be positive and cost cannot be negative")
        self._lots.setdefault(asset.upper(), deque()).append(
            _Lot(quantity=quantity, unit_cost=total_cost / quantity)
        )

    def sell(
        self,
        *,
        trade_date: date,
        asset: str,
        quantity: Decimal,
        sale_value: Decimal,
        fees: Decimal = Decimal("0"),
    ) -> TaxLedgerEntry:
        if quantity <= 0 or sale_value <= 0 or fees < 0:
            raise ValueError("sale quantity/value must be positive and fees cannot be negative")
        asset = asset.upper()
        remaining = quantity
        cost_basis = Decimal("0")
        lots = self._lots.setdefault(asset, deque())
        while remaining > 0 and lots:
            lot = lots[0]
            consumed = min(remaining, lot.quantity)
            cost_basis += consumed * lot.unit_cost
            remaining -= consumed
            lot.quantity -= consumed
            if lot.quantity == 0:
                lots.popleft()
        if remaining > 0:
            raise ValueError(f"insufficient recorded lots for {asset} sale")
        gain = sale_value - fees - cost_basis
        entry = TaxLedgerEntry(
            trade_date=trade_date,
            asset=asset,
            quantity=quantity,
            cost_basis=cost_basis,
            sale_value=sale_value,
            fees=fees,
            gain=gain,
            tds=sale_value * self.tds_rate,
            tax_reserve=max(Decimal("0"), gain * self.gain_tax_rate),
        )
        self.entries.append(entry)
        return entry

    def to_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "date",
                "asset",
                "quantity",
                "cost_basis",
                "sale_value",
                "fees",
                "gain",
                "tds",
                "tax_reserve",
            ]
        )
        for entry in self.entries:
            writer.writerow(
                [
                    entry.trade_date,
                    entry.asset,
                    entry.quantity,
                    entry.cost_basis,
                    entry.sale_value,
                    entry.fees,
                    entry.gain,
                    entry.tds,
                    entry.tax_reserve,
                ]
            )
        return output.getvalue()

    def write_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_csv(), encoding="utf-8", newline="")
        return destination
