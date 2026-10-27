"""ML signal strategy with stale/invalid-output fail-safe behavior."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tradebot.ai.features import build_features, features_are_fresh
from tradebot.ai.models import SignalModel
from tradebot.ai.sentiment import SentimentOverlay, SentimentScore
from tradebot.core.clock import utc_now
from tradebot.core.models import OrderSide, Signal, SignalEntryType
from tradebot.data.models import OrderBookSnapshot
from tradebot.strategies.base import StrategyContext
from tradebot.strategies.indicators import atr


class MlSignalStrategy:
    name = "ml_signal"

    def __init__(
        self,
        model: SignalModel,
        *,
        threshold: Decimal = Decimal("0.65"),
        overlay: SentimentOverlay | None = None,
        max_feature_age_seconds: int = 15,
    ) -> None:
        self.model = model
        self.threshold = threshold
        self.overlay = overlay or SentimentOverlay()
        self.max_feature_age = timedelta(seconds=max_feature_age_seconds)

    def on_candle(
        self,
        context: StrategyContext,
        *,
        order_book: OrderBookSnapshot | None = None,
        sentiment: SentimentScore | None = None,
    ) -> list[Signal]:
        if sentiment is not None and not self.overlay.allows_long(sentiment):
            return []
        sentiment_value = sentiment.score if sentiment else Decimal("0")
        features = build_features(
            list(context.candles), order_book=order_book, sentiment=sentiment_value
        )
        if features is None or not features_are_fresh(
            features, now=utc_now(), max_age=self.max_feature_age
        ):
            return []
        try:
            prediction = self.model.predict(features)
        except Exception:
            return []
        if not prediction.probability.is_finite() or prediction.probability < self.threshold:
            return []
        volatility = atr(list(context.candles))
        if volatility is None or volatility <= 0:
            return []
        entry = context.latest.close
        confidence = prediction.probability * self.overlay.confidence_multiplier(sentiment)
        return [
            Signal(
                symbol=context.symbol,
                side=OrderSide.BUY,
                entry_type=SignalEntryType.MARKET,
                entry_price=entry,
                stop_price=entry - Decimal("1.5") * volatility,
                target_price=entry + Decimal("3") * volatility,
                confidence=min(Decimal("1"), confidence),
                reason=f"model {prediction.model_version} probability={prediction.probability:.4f}",
                strategy=self.name,
                timestamp=context.latest.close_time,
            )
        ]
