"""Response schema for onboarding path synthesis — Feature 10."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class EntryPoint:
    component: str
    fact_ids: list[str]
    rationale: str


@dataclasses.dataclass
class WorkflowRef:
    description: str
    fact_ids: list[str]


@dataclasses.dataclass
class AvoidItem:
    component: str
    fact_ids: list[str]
    rationale: str


@dataclasses.dataclass
class TimeBoxed:
    thirty_minutes: str
    two_hours: str


@dataclasses.dataclass
class OnboardingPathResponse:
    entry_points: list[EntryPoint]
    recommended_workflow: WorkflowRef
    avoid_initially: list[AvoidItem]
    time_boxed_understanding: TimeBoxed
    open_questions: list[str]
    confidence: float
    fact_ids: list[str]
