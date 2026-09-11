"""AnalysisWindow — optional time-bounded window for git history queries."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta


@dataclasses.dataclass(frozen=True, slots=True)
class AnalysisWindow:
    window: timedelta | None = None  # None = full history

    def since_arg(self) -> list[str]:
        if self.window is None:
            return []
        cutoff = datetime.now(tz=UTC) - self.window
        return [f"--since={cutoff.isoformat()}"]
