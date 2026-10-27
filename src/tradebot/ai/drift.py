"""Simple population stability index monitor."""

from __future__ import annotations

from decimal import Decimal


def population_stability_index(
    baseline: list[Decimal], current: list[Decimal], *, bins: int = 10
) -> Decimal:
    if not baseline or not current or bins <= 1:
        raise ValueError("PSI requires two non-empty samples and at least two bins")
    lower = min(min(baseline), min(current))
    upper = max(max(baseline), max(current))
    if upper == lower:
        return Decimal("0")
    width = (upper - lower) / bins

    def distribution(values: list[Decimal]) -> list[Decimal]:
        counts = [0] * bins
        for value in values:
            index = min(bins - 1, int((value - lower) / width))
            counts[index] += 1
        total = Decimal(len(values))
        return [(Decimal(count) + Decimal("0.001")) / total for count in counts]

    base_distribution = distribution(baseline)
    current_distribution = distribution(current)
    return sum(
        (
            (current_value - base_value)
            * (current_value / base_value).ln()
            for base_value, current_value in zip(
                base_distribution, current_distribution, strict=True
            )
        ),
        Decimal("0"),
    )
