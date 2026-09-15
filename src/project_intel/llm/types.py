"""Core types for the LLM orchestration framework — Feature 07."""

from __future__ import annotations

import dataclasses
from typing import Any, Literal


@dataclasses.dataclass(frozen=True, slots=True)
class StructuredPrompt:
    """A fully self-contained LLM request bundle."""

    instructions: str
    content: str
    schema_version: str  # bump to invalidate cache
    category: str  # e.g. "architecture", "domain", "onboarding" — for budget tracking
    estimated_input_tokens: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class Hypothesis:
    """One possible interpretation with independent confidence and citations."""

    value: Any
    confidence: float  # [0, 1], supplied by the model
    fact_ids: list[str]


@dataclasses.dataclass(slots=True)
class LLMCallResult[T]:
    status: Literal["ok", "not_analyzed"]
    value: T | None = None
    reason: Literal["llm_failed", "budget_exceeded", "llm_disabled"] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class BudgetConfig:
    """Per-category token budgets for a single analysis run."""

    tokens_per_category: dict[str, int]

    @classmethod
    def unlimited(cls) -> BudgetConfig:
        return cls(tokens_per_category={})
