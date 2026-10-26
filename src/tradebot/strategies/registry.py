"""Named strategy registry used by replay and runtime workers."""

from tradebot.strategies.base import Strategy
from tradebot.strategies.breakout import BreakoutStrategy
from tradebot.strategies.ema_trend import EmaTrendStrategy
from tradebot.strategies.mean_reversion import MeanReversionStrategy


def default_strategies() -> dict[str, Strategy]:
    return {
        EmaTrendStrategy.name: EmaTrendStrategy(),
        MeanReversionStrategy.name: MeanReversionStrategy(),
        BreakoutStrategy.name: BreakoutStrategy(),
    }
