"""LLMOrchestrator — ties together provider, cache, budget, and citation validation.

This is the entry point synthesis features use; they never call a raw provider directly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cattrs

from ..facts.store import FactStore
from .budget import BudgetTracker
from .cache import LLMCache, cache_key
from .citation import validate_citations
from .providers import LLMProvider
from .types import BudgetConfig, LLMCallResult, StructuredPrompt

_CONVERTER = cattrs.Converter()
_log = logging.getLogger(__name__)


class LLMOrchestrator:
    """Wraps a raw LLMProvider with caching, budget enforcement, and citation validation."""

    def __init__(
        self,
        provider: LLMProvider,
        store: FactStore,
        cache: LLMCache,
        budget: BudgetTracker,
    ) -> None:
        self._provider = provider
        self._store = store
        self._cache = cache
        self._budget = budget

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    @classmethod
    def create(
        cls,
        provider: LLMProvider,
        store: FactStore,
        cache_db_path: Path,
        budget_config: BudgetConfig | None = None,
    ) -> LLMOrchestrator:
        return cls(
            provider=provider,
            store=store,
            cache=LLMCache(cache_db_path),
            budget=BudgetTracker(budget_config or BudgetConfig.unlimited()),
        )

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        # 1. Budget pre-check
        if not self._budget.within_budget(prompt.category, prompt.estimated_input_tokens):
            return LLMCallResult(status="not_analyzed", reason="budget_exceeded")

        # 2. Cache lookup
        key = cache_key(prompt, self._provider.provider_id)
        cached = self._cache.get(key)
        if cached is not None:
            try:
                payload = json.loads(cached)
                value = _CONVERTER.structure(payload, schema)
                return LLMCallResult(status="ok", value=value)
            except Exception:  # noqa: BLE001, S110
                pass  # stale/corrupt cache entry — fall through to provider

        # 3. Provider call
        _log.info("LLM call provider=%s category=%s tokens~%d",
                  self._provider.provider_id, prompt.category, prompt.estimated_input_tokens)
        result = self._provider.complete(prompt, schema)
        if result.status != "ok" or result.value is None:
            _log.warning("LLM call failed provider=%s category=%s reason=%s",
                         self._provider.provider_id, prompt.category, result.reason)
            return result

        # 4. Citation validation
        valid, bad_ids = validate_citations(result.value, self._store)
        if not valid:
            _log.warning("Citation validation failed provider=%s category=%s invalid_ids=%s",
                         self._provider.provider_id, prompt.category, bad_ids)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")

        # 5. Store in cache (serialize the value back to JSON for storage)
        try:
            payload = _CONVERTER.unstructure(result.value)
            self._cache.set(key, json.dumps(payload))
        except Exception:  # noqa: BLE001, S110
            pass  # cache failure is non-fatal

        # 6. Record token usage
        self._budget.record(prompt.category, prompt.estimated_input_tokens)

        return result
