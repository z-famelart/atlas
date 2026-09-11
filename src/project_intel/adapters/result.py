"""AdapterResult and AdapterStatus — outcome of one adapter execution."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..facts import Fact


class AdapterStatus(str, Enum):
    OK = "ok"
    SKIPPED_TOOL_NOT_FOUND = "skipped:tool_not_found"
    SKIPPED_VERSION_MISMATCH = "skipped:version_mismatch"
    FAILED = "failed"


@dataclasses.dataclass(frozen=True, slots=True)
class AdapterResult:
    adapter_name: str
    status: AdapterStatus
    facts: tuple[Fact, ...]
    error: str | None = None
    tool_version: str | None = None  # detected version, None when not applicable
