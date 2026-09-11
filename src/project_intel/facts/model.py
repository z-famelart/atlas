"""Core domain types: EntityRef, Entity, Evidence, Fact."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, Literal

from .enums import EntityType
from .refs import EvidenceRef


@dataclasses.dataclass(frozen=True, slots=True)
class EntityRef:
    type: EntityType
    id: str


@dataclasses.dataclass(frozen=True, slots=True)
class Entity:
    type: EntityType
    id: str
    attributes: dict[str, Any]
    repository_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclasses.dataclass(frozen=True, slots=True)
class Evidence:
    kind: Literal["file", "line", "symbol", "commit", "config", "tool_output", "documentation", "external"]
    ref: EvidenceRef
    source_analyzer: str
    retrieved_at: datetime


@dataclasses.dataclass(frozen=True, slots=True)
class Fact:
    id: str
    type: str
    subject: EntityRef
    evidence: tuple[Evidence, ...]
    provenance: Literal["observed", "computed", "inferred", "hypothesis"]
    confidence: float
    source_analyzer: str
    created_at: datetime
    schema_version: str
    run_id: str
    predicate: str | None = None
    object: EntityRef | None = None
    value: Any | None = None

    def __post_init__(self) -> None:
        # Defensive copy: caller mutating the list they passed in must not affect this Fact.
        object.__setattr__(self, "evidence", tuple(self.evidence))
