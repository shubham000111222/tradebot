from pathlib import Path

import pytest
from pydantic import ValidationError

from tradebot.config import TradingMode, load_settings

CONFIG = Path("config/settings.yaml")


def test_default_config_is_safe_paper_mode() -> None:
    settings = load_settings(CONFIG)

    assert settings.mode is TradingMode.PAPER
    assert str(settings.initial_cash_usdt) == "1000.00"
    assert settings.symbols == ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT")


def test_live_mode_requires_independent_environment_guard(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "settings.yaml"
    config.write_text("mode: live\n", encoding="utf-8")
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)

    with pytest.raises(ValidationError, match="LIVE_TRADING_ENABLED=true"):
        load_settings(config)


def test_live_mode_can_pass_first_guard_only_when_explicitly_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "settings.yaml"
    config.write_text("mode: live\n", encoding="utf-8")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    assert load_settings(config).mode is TradingMode.LIVE
