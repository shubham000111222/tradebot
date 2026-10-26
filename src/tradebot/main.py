"""Week 1 command-line entry point."""

from __future__ import annotations

import argparse

from tradebot.config import load_settings
from tradebot.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Tradebot paper-mode bootstrap")
    parser.add_argument("--config", default="config/settings.yaml", help="path to settings YAML")
    args = parser.parse_args()

    logger = configure_logging()
    settings = load_settings(args.config)
    logger.info(
        "configuration_validated",
        mode=settings.mode.value,
        initial_cash_usdt=str(settings.initial_cash_usdt),
        symbols=list(settings.symbols),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
