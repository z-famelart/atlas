"""EvidenceRef shapes — one frozen dataclass per evidence kind."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class FileRef:
    repository_id: str
    path: str  # relative, never absolute


@dataclasses.dataclass(frozen=True, slots=True)
class LineRef:
    repository_id: str
    path: str
    line_start: int
    commit_hash: str  # pinned for invalidation
    line_end: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class SymbolRef:
    repository_id: str
    path: str
    symbol_id: str  # qualified name from the graph provider
    line_start: int | None = None
    line_end: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class CommitRef:
    repository_id: str
    commit_hash: str  # full hash only


@dataclasses.dataclass(frozen=True, slots=True)
class ConfigRef:
    repository_id: str
    path: str


@dataclasses.dataclass(frozen=True, slots=True)
class ToolOutputRef:
    source_analyzer: str
    raw_ref: str  # opaque pointer into the analyzer's captured output


@dataclasses.dataclass(frozen=True, slots=True)
class DocumentationRef:
    repository_id: str
    path: str


@dataclasses.dataclass(frozen=True, slots=True)
class ExternalRef:
    source_type: str
    identifier: str
    url: str | None = None  # reference only, never stores extracted sensitive content


EvidenceRef = (
    FileRef
    | LineRef
    | SymbolRef
    | CommitRef
    | ConfigRef
    | ToolOutputRef
    | DocumentationRef
    | ExternalRef
)

KIND_TO_REF_CLASS: dict[str, type] = {
    "file": FileRef,
    "line": LineRef,
    "symbol": SymbolRef,
    "commit": CommitRef,
    "config": ConfigRef,
    "tool_output": ToolOutputRef,
    "documentation": DocumentationRef,
    "external": ExternalRef,
}
