"""Read-only local Streamlit dashboard.

Run with: ``streamlit run dashboard/app.py``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tradebot.portfolio.ledger import Ledger
from tradebot.risk.killswitch import KillSwitch


def dashboard_snapshot(
    ledger: Ledger, kill_switch: KillSwitch, marks: dict[str, Decimal]
) -> dict[str, object]:
    return {
        "balances": {asset: str(amount) for asset, amount in ledger.balances().items()},
        "positions": [position.model_dump(mode="json") for position in ledger.positions()],
        "equity": str(ledger.equity(marks)),
        "kill_level": int(kill_switch.level),
        "kill_reason": kill_switch.reason,
    }


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Tradebot", layout="wide")
    st.title("Tradebot — read-only paper dashboard")
    state_path = Path(st.sidebar.text_input("State database", "state/demo.sqlite3"))
    if not state_path.is_file():
        st.info(f"No state database found at {state_path}. Run the paper demo first.")
        return
    ledger = Ledger(state_path)
    kill_switch = KillSwitch(state_path)
    try:
        marks = {
            position.symbol: Decimal(
                st.sidebar.text_input(f"Mark {position.symbol}", "0")
            )
            for position in ledger.positions()
        }
        snapshot = dashboard_snapshot(ledger, kill_switch, marks)
        st.metric("Equity", snapshot["equity"])
        st.metric("Kill switch", f"L{snapshot['kill_level']}")
        st.subheader("Balances")
        st.json(snapshot["balances"])
        st.subheader("Positions")
        st.json(snapshot["positions"])
    finally:
        ledger.close()
        kill_switch.close()


if __name__ == "__main__":
    main()
