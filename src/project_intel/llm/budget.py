"""Per-category token budget tracker — Feature 07 (Décidé Q100, Q101).

Exceeding budget → LLMCallResult(not_analyzed, budget_exceeded), never a crash.
"""

from __future__ import annotations

from .types import BudgetConfig


class BudgetTracker:
    def __init__(self, config: BudgetConfig) -> None:
        self._config = config
        self._used: dict[str, int] = {}

    def within_budget(self, category: str, estimated_tokens: int) -> bool:
        limit = self._config.tokens_per_category.get(category)
        if limit is None:
            return True  # no limit configured for this category
        used = self._used.get(category, 0)
        return used + estimated_tokens <= limit

    def record(self, category: str, tokens: int) -> None:
        self._used[category] = self._used.get(category, 0) + tokens

    def used(self, category: str) -> int:
        return self._used.get(category, 0)
