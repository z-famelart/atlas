"""Pipeline abstractions: Stage protocol, PipelineContext, StageRunResult."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from ..facts.store import FactStore

if TYPE_CHECKING:
    from ..discovery.scope import ScopeConfig


class LLMProvider(Protocol):
    """Placeholder — fulfilled by Feature 07."""

    def complete(self, prompt: str, **kwargs: Any) -> str: ...


@dataclasses.dataclass(frozen=True, slots=True)
class PipelineContext:
    store: FactStore
    repository_path: Path
    run_id: str
    scope: ScopeConfig
    llm_provider: LLMProvider | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class StageRunResult:
    name: str
    status: Literal["ok", "skipped", "failed"]
    facts_produced: int
    detail: str | None = None


@runtime_checkable
class Stage(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> StageRunResult: ...
