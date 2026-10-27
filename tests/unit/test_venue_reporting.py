from datetime import UTC, date, datetime
from decimal import Decimal

from tradebot.reporting.daily import (
    DailyReport,
    ReportTrade,
    render_csv,
    render_html,
    render_text,
    write_report,
)
from tradebot.venue.models import (
    CryptoCalendar,
    Instrument,
    PercentageCostModel,
    ProductType,
    SessionHours,
)


def report() -> DailyReport:
    return DailyReport(
        report_date=date(2026, 1, 1),
        mode="paper",
        kill_level=0,
        starting_equity="1000",
        ending_equity="1005",
        realized_pnl="5",
        unrealized_pnl="0",
        fees="1",
        tax_reserve="1.5",
        trades=(
            ReportTrade(
                symbol="BTC/USDT",
                strategy="breakout",
                side="buy",
                quantity="0.1",
                entry_price="100",
                exit_price="150",
                pnl="5",
                fees="1",
            ),
        ),
        ai_commentary=("Template-only commentary",),
    )


def test_venue_abstractions_cover_crypto_and_session_markets() -> None:
    instrument = Instrument(
        symbol="BTC/USDT",
        venue="demo",
        quote_currency="USDT",
        tick_size="0.01",
        quantity_step="0.00001",
        min_quantity="0.0001",
        min_notional="10",
        product_type=ProductType.SPOT,
    )
    costs = PercentageCostModel(Decimal("0.001"), Decimal("0.002"))
    timestamp = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    assert instrument.product_type is ProductType.SPOT
    assert costs.estimate(notional=Decimal("100"), side="buy") == Decimal("0.2")
    assert CryptoCalendar().is_open(timestamp)
    assert SessionHours().is_open(timestamp)
    assert not SessionHours().is_open(datetime(2026, 1, 1, 16, 0, tzinfo=UTC))


def test_daily_report_has_text_html_csv_and_files(tmp_path) -> None:
    daily = report()
    assert "Net 5" in render_text(daily)
    assert "<table>" in render_html(daily)
    assert "BTC/USDT" in render_csv(daily)
    paths = write_report(daily, tmp_path)
    assert all(path.exists() for path in paths)
