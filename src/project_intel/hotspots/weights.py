"""HotspotWeights — configurable per-component weights for the scoring engine."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class HotspotWeights:
    complexity: float = 1.0
    size: float = 0.5
    centrality: float = 1.0
    churn: float = 1.0
