from datetime import date
from decimal import Decimal

import pytest

from tradebot.reporting.tax_ledger import TaxLedger


def test_fifo_tax_ledger_calculates_gain_tds_and_reserve(tmp_path) -> None:
    ledger = TaxLedger()
    ledger.buy(
        trade_date=date(2026, 1, 1),
        asset="BTC",
        quantity=Decimal("1"),
        total_cost=Decimal("100"),
    )
    ledger.buy(
        trade_date=date(2026, 1, 2),
        asset="BTC",
        quantity=Decimal("1"),
        total_cost=Decimal("140"),
    )

    entry = ledger.sell(
        trade_date=date(2026, 1, 3),
        asset="BTC",
        quantity=Decimal("1.5"),
        sale_value=Decimal("300"),
        fees=Decimal("2"),
    )

    assert entry.cost_basis == Decimal("170")
    assert entry.gain == Decimal("128")
    assert entry.tds == Decimal("3.00")
    assert entry.tax_reserve == Decimal("38.40")
    path = ledger.write_csv(tmp_path / "tax.csv")
    assert path.exists()
    assert "BTC" in path.read_text(encoding="utf-8")


def test_tax_ledger_rejects_unrecorded_sales() -> None:
    with pytest.raises(ValueError, match="insufficient recorded lots"):
        TaxLedger().sell(
            trade_date=date(2026, 1, 1),
            asset="ETH",
            quantity=Decimal("1"),
            sale_value=Decimal("100"),
        )
