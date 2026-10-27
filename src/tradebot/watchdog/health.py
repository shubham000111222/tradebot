"""Component health model used by the watchdog and reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from tradebot.core.clock import utc_now
from tradebot.core.models import DomainModel


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class ComponentHealth(DomainModel):
    component: str = Field(min_length=1)
    state: HealthState
    score: int = Field(ge=0, le=100)
    detail: str = ""
    checked_at: datetime = Field(default_factory=utc_now)


class HealthMonitor:
    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}

    def report(
        self,
        component: str,
        state: HealthState,
        *,
        score: int,
        detail: str = "",
        checked_at: datetime | None = None,
    ) -> ComponentHealth:
        health = ComponentHealth(
            component=component,
            state=state,
            score=score,
            detail=detail,
            checked_at=checked_at or utc_now(),
        )
        self._components[component] = health
        return health

    def get(self, component: str) -> ComponentHealth | None:
        return self._components.get(component)

    def all(self) -> tuple[ComponentHealth, ...]:
        return tuple(self._components.values())

    def overall(self) -> ComponentHealth:
        if not self._components:
            return ComponentHealth(
                component="overall",
                state=HealthState.DEGRADED,
                score=0,
                detail="no checks reported",
            )
        components = self.all()
        score = sum(item.score for item in components) // len(components)
        if any(item.state is HealthState.FAILED for item in components):
            state = HealthState.FAILED
        elif any(item.state is HealthState.DEGRADED for item in components):
            state = HealthState.DEGRADED
        else:
            state = HealthState.HEALTHY
        return ComponentHealth(
            component="overall", state=state, score=score, detail=f"{len(components)} components"
        )
