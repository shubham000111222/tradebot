"""Versioned, fail-safe model interface and lightweight demonstration model."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from pydantic import Field

from tradebot.ai.features import FeatureVector
from tradebot.core.models import DomainModel


class ModelPrediction(DomainModel):
    probability: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    model_version: str = Field(min_length=1)


class SignalModel(Protocol):
    version: str

    def predict(self, features: FeatureVector) -> ModelPrediction: ...


class LinearDemoModel:
    """A transparent demonstration model; production models remain registry artifacts."""

    def __init__(
        self,
        weights: dict[str, Decimal],
        *,
        bias: Decimal = Decimal("0.5"),
        version: str = "demo-v1",
    ) -> None:
        self.weights = weights
        self.bias = bias
        self.version = version

    def predict(self, features: FeatureVector) -> ModelPrediction:
        score = self.bias
        for name, weight in self.weights.items():
            score += weight * features.values.get(name, Decimal("0"))
        probability = max(Decimal("0"), min(Decimal("1"), score))
        return ModelPrediction(probability=probability, model_version=self.version)


class ModelCard(DomainModel):
    version: str
    data_hash: str
    features: tuple[str, ...]
    metrics: dict[str, Decimal]
    created_at: datetime
    weaknesses: tuple[str, ...] = ()


class ModelRegistry:
    def __init__(self, root: str | Path = "state/models") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_card(self, card: ModelCard) -> Path:
        path = self.root / f"{card.version}.json"
        path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_card(self, version: str) -> ModelCard:
        path = self.root / f"{version}.json"
        if not path.is_file():
            raise FileNotFoundError(f"model card does not exist: {path}")
        return ModelCard.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def hash_features(features: FeatureVector) -> str:
        payload = json.dumps(
            {key: str(value) for key, value in sorted(features.values.items())},
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()
