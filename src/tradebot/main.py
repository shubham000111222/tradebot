"""Week 1 command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from tradebot.config import load_settings
from tradebot.logging import configure_logging
from tradebot.runtime.paper import PaperRuntime, synthetic_demo_candles
from tradebot.strategies.breakout import BreakoutStrategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Tradebot paper-mode bootstrap")
    parser.add_argument("--config", default="config/settings.yaml", help="path to settings YAML")
    parser.add_argument("--demo", action="store_true", help="run the deterministic paper demo")
    args = parser.parse_args()

    logger = configure_logging()
    settings = load_settings(args.config)
    logger.info(
        "configuration_validated",
        mode=settings.mode.value,
        initial_cash_usdt=str(settings.initial_cash_usdt),
        symbols=list(settings.symbols),
    )
    if args.demo:
        demo_state = Path("state/demo.sqlite3")
        PaperRuntime.reset_state(demo_state)
        runtime = PaperRuntime(demo_state)
        try:
            result = runtime.run(synthetic_demo_candles(), BreakoutStrategy())
            logger.info(
                "paper_demo_complete",
                signals=len(result.signals),
                fills=len(result.fills),
                rejections=len(result.rejections),
                ending_equity=str(result.ending_equity),
            )
        finally:
            runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
