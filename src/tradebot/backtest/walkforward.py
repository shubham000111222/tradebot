"""Leakage-resistant rolling train/test windows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class WalkForwardWindow(Generic[T]):
    index: int
    train: tuple[T, ...]
    test: tuple[T, ...]


def walk_forward(
    values: Sequence[T], *, train_size: int, test_size: int, step: int | None = None
) -> list[WalkForwardWindow[T]]:
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    increment = step or test_size
    if increment <= 0:
        raise ValueError("step must be positive")
    windows: list[WalkForwardWindow[T]] = []
    start = 0
    index = 0
    while start + train_size + test_size <= len(values):
        train_end = start + train_size
        windows.append(
            WalkForwardWindow(
                index=index,
                train=tuple(values[start:train_end]),
                test=tuple(values[train_end : train_end + test_size]),
            )
        )
        start += increment
        index += 1
    return windows
