from datetime import UTC, datetime
from decimal import Decimal

from tradebot.core.models import Order, OrderSide, OrderStatus, OrderType
from tradebot.data.models import OrderBookLevel, OrderBookSnapshot
from tradebot.execution.order_manager import OrderManager
from tradebot.execution.paper import PaperExchange
from tradebot.execution.reconcile import Reconciler
from tradebot.portfolio.ledger import Ledger


def book(ask: str = "100", ask_quantity: str = "1") -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTC/USDT",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        bids=(OrderBookLevel(price="99", quantity="2"),),
        asks=(OrderBookLevel(price=ask, quantity=ask_quantity),),
    )


def buy_order(quantity: str = "1", price: str = "101") -> Order:
    return Order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=quantity,
        price=price,
        client_order_id="client-1",
    )


def test_paper_exchange_walks_book_and_is_idempotent() -> None:
    exchange = PaperExchange()
    manager = OrderManager(exchange)
    order = buy_order(quantity="0.5")

    submitted = manager.submit(order)
    duplicate = manager.submit(order)
    fills = manager.process_market(book(ask_quantity="0.5"))

    assert submitted.status is OrderStatus.SUBMITTED
    assert duplicate.id == submitted.id
    assert len(fills) == 1
    assert fills[0].price == Decimal("100")
    assert exchange.get_order(order.client_order_id).status is OrderStatus.FILLED
    assert exchange.get_balances()["USDT"] == Decimal("949.95000")
    assert exchange.get_balances()["BTC"] == Decimal("0.5")


def test_ledger_records_decimal_pnl_and_reconciles(tmp_path) -> None:
    exchange = PaperExchange()
    manager = OrderManager(exchange)
    ledger = Ledger(tmp_path / "paper.sqlite3")
    try:
        manager.submit(buy_order(quantity="0.5"))
        fills = manager.process_market(book(ask_quantity="0.5"))
        for fill in fills:
            ledger.record_fill(fill)

        assert ledger.cash() == Decimal("949.95000")
        assert ledger.position("BTC/USDT").average_entry_price == Decimal("100")
        assert Reconciler(ledger, exchange).check(set()).clean

        sell = manager.submit(
            Order(
                symbol="BTC/USDT",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                quantity="0.5",
                client_order_id="client-2",
            )
        )
        sell_fills = manager.process_market(book())
        for fill in sell_fills:
            ledger.record_fill(fill)

        assert sell.status is OrderStatus.SUBMITTED
        assert ledger.position("BTC/USDT").quantity == Decimal("0")
        assert ledger.position("BTC/USDT").realized_pnl == Decimal("-0.5495")
        assert ledger.cash() == Decimal("999.4005")
        assert not Reconciler(ledger, exchange).check().mismatches
    finally:
        ledger.close()


def test_reconciliation_reports_balance_mismatch(tmp_path) -> None:
    exchange = PaperExchange()
    ledger = Ledger(tmp_path / "paper.sqlite3")
    try:
        exchange._balances["USDT"] = Decimal("999")
        result = Reconciler(ledger, exchange).check()
        assert not result.clean
        assert result.mismatches == ("balance:USDT:local=1000:exchange=999",)
    finally:
        ledger.close()
