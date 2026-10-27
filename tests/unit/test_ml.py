from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradebot.ai.drift import population_stability_index
from tradebot.ai.features import build_features
from tradebot.ai.models import LinearDemoModel, ModelCard, ModelRegistry
from tradebot.ai.sentiment import SentimentOverlay, SentimentScore
from tradebot.core.models import Candle
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.ml_signal import MlSignalStrategy


def candle(index: int, close: str = "100") -> Candle:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    value = Decimal(close)
    return Candle(
        symbol="BTC/USDT",
        timeframe="1m",
        open_time=start,
        close_time=start + timedelta(minutes=1),
        open=value,
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("10"),
    )


def test_features_are_unavailable_before_warmup() -> None:
    assert build_features([candle(index) for index in range(20)]) is None
    features = build_features([candle(index) for index in range(21)])
    assert features is not None
    assert "return_1" in features.values


def test_ml_strategy_fails_safe_on_low_probability_and_model_error() -> None:
    context = StrategyContext("BTC/USDT", "1m", tuple(candle(index) for index in range(21)))
    low_probability = MlSignalStrategy(LinearDemoModel({}, bias=Decimal("0.5")))
    assert low_probability.on_candle(context) == []

    class BrokenModel:
        version = "broken"

        def predict(self, _features):
            raise RuntimeError("model unavailable")

    assert MlSignalStrategy(BrokenModel()).on_candle(context) == []


def test_sentiment_filters_negative_headlines() -> None:
    sentiment = SentimentScore(
        score="-0.5",
        headline_count=4,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert not SentimentOverlay().allows_long(sentiment)


def test_model_registry_round_trips_model_card(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    card = ModelCard(
        version="demo-v1",
        data_hash="abc",
        features=("return_1",),
        metrics={"sharpe": "1.2"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert registry.save_card(card).exists()
    assert registry.load_card("demo-v1").metrics["sharpe"] == Decimal("1.2")


def test_psi_is_zero_for_identical_samples_and_positive_for_shift() -> None:
    baseline = [Decimal(index) for index in range(100)]
    assert population_stability_index(baseline, baseline) == Decimal("0")
    assert population_stability_index(baseline, [value + 50 for value in baseline]) > 0
