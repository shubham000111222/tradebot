"""Deterministic daily report outputs."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import Field

from tradebot.core.models import DomainModel


class ReportTrade(DomainModel):
    symbol: str
    strategy: str
    side: str
    quantity: Decimal = Field(gt=Decimal("0"))
    entry_price: Decimal = Field(gt=Decimal("0"))
    exit_price: Decimal = Field(gt=Decimal("0"))
    pnl: Decimal
    fees: Decimal = Field(ge=Decimal("0"))


class DailyReport(DomainModel):
    report_date: date
    mode: str
    kill_level: int
    starting_equity: Decimal
    ending_equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    tax_reserve: Decimal
    trades: tuple[ReportTrade, ...] = ()
    events: tuple[str, ...] = ()
    ai_commentary: tuple[str, ...] = ()

    @property
    def net_pnl(self) -> Decimal:
        return self.ending_equity - self.starting_equity

    @property
    def net_pnl_fraction(self) -> Decimal:
        return self.net_pnl / self.starting_equity if self.starting_equity else Decimal("0")


def render_text(report: DailyReport) -> str:
    wins = sum(trade.pnl > 0 for trade in report.trades)
    losses = sum(trade.pnl < 0 for trade in report.trades)
    lines = [
        (
            f"DAILY REPORT | {report.report_date.isoformat()} | {report.mode.upper()} | "
            f"Kill switch L{report.kill_level}"
        ),
        (
            f"Equity {report.ending_equity} (start {report.starting_equity}) | "
            f"Net {report.net_pnl} ({report.net_pnl_fraction:.2%})"
        ),
        (
            f"Realized {report.realized_pnl} | Unrealized {report.unrealized_pnl} | "
            f"Fees -{report.fees} | Tax reserve {report.tax_reserve}"
        ),
        f"Trades {len(report.trades)} (W{wins} / L{losses})",
        f"Events: {len(report.events)}",
    ]
    lines.extend(f"AI note: {note}" for note in report.ai_commentary)
    return "\n".join(lines)


def render_html(report: DailyReport) -> str:
    rows = "".join(
        f"<tr><td>{trade.symbol}</td><td>{trade.strategy}</td><td>{trade.pnl}</td></tr>"
        for trade in report.trades
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Tradebot daily report</title></head>"
        f"<body><h1>Daily report {report.report_date.isoformat()}</h1>"
        f"<p>Mode: {report.mode} | Kill switch: L{report.kill_level}</p>"
        f"<p>Equity: {report.ending_equity} | Net PnL: {report.net_pnl}</p>"
        f"<table><thead><tr><th>Symbol</th><th>Strategy</th><th>PnL</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>"
    )


def render_csv(report: DailyReport) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "mode", "symbol", "strategy", "side", "quantity", "pnl", "fees"])
    for trade in report.trades:
        writer.writerow(
            [
                report.report_date,
                report.mode,
                trade.symbol,
                trade.strategy,
                trade.side,
                trade.quantity,
                trade.pnl,
                trade.fees,
            ]
        )
    return output.getvalue()


def write_report(report: DailyReport, root: str | Path = "reports") -> tuple[Path, Path, Path]:
    directory = Path(root) / report.report_date.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / "summary.txt"
    html_path = directory / "report.html"
    csv_path = directory / "trades.csv"
    text_path.write_text(render_text(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    csv_path.write_text(render_csv(report), encoding="utf-8", newline="")
    return text_path, html_path, csv_path
