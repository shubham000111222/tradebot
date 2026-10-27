"""Validated sentiment overlay; it can filter or reduce size, never trigger trades."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, ValidationInfo, field_validator

from tradebot.core.clock import require_utc
from tradebot.core.models import DomainModel


class SentimentScore(DomainModel):
    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    headline_count: int = Field(ge=0)
    published_at: datetime
    retrieved_at: datetime

    @field_validator("published_at", "retrieved_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @field_validator("retrieved_at")
    @classmethod
    def retrieval_is_not_before_publish(
        cls, value: datetime, info: ValidationInfo
    ) -> datetime:
        published_at = info.data.get("published_at")
        if published_at is not None and value < published_at:
            raise ValueError("retrieved_at cannot precede published_at")
        return value


class SentimentOverlay:
    """Apply sentiment only as a conservative confidence filter."""

    def __init__(self, minimum_score: Decimal = Decimal("-0.25")) -> None:
        self.minimum_score = minimum_score

    def allows_long(self, sentiment: SentimentScore | None) -> bool:
        return sentiment is None or sentiment.score >= self.minimum_score

    def confidence_multiplier(self, sentiment: SentimentScore | None) -> Decimal:
        if sentiment is None:
            return Decimal("1")
        return max(Decimal("0"), (sentiment.score + Decimal("1")) / Decimal("2"))
