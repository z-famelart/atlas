"""AdapterManifest and AdapterContext — the declarative adapter contract."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..facts import Fact


@dataclasses.dataclass(frozen=True, slots=True)
class AdapterContext:
    """Runtime context injected into every adapter invocation."""

    target_path: Path
    run_id: str
    repository_id: str
    timestamp: datetime  # deterministic timestamp stamped on produced Facts


@dataclasses.dataclass(frozen=True, slots=True)
class AdapterManifest:
    """Declarative description of one adapter.

    CLI adapters:     command = ["radon", "cc", "."]
    Python adapters:  command = some_callable (receives AdapterContext, returns raw str)
    """

    name: str
    version: str  # adapter's own semver, independent of the wrapped tool's version
    category: str  # e.g. "language-detection", "complexity", "git"
    normalize: Callable[[str, AdapterContext], list[Fact]]
    command: list[str] | Callable[[AdapterContext], str]
    supported_ecosystems: list[str] | None = None
    output_format: str = "json"
    min_version: str | None = None
    max_version: str | None = None
    install_hint: str | None = None  # surfaced to the user when the tool is missing

    @property
    def source_analyzer_id(self) -> str:
        """Versioned identifier to stamp on every Fact this adapter produces."""
        return f"{self.name}@{self.version}"
