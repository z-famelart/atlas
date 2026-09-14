"""Response schema for architecture interpretation — Feature 08."""

from __future__ import annotations

import dataclasses

_CATALOGUE = [
    "layered",
    "hexagonal",
    "microservices",
    "modular_monolith",
    "event_driven",
    "mvc_mvvm",
    "big_ball_of_mud",
    "uncatalogued",
]

CATALOGUE_DESCRIPTION = (
    "Allowed pattern values: " + ", ".join(f'"{p}"' for p in _CATALOGUE) + ". "
    'Use "big_ball_of_mud" when the graph shows ad-hoc coupling, unclear boundaries, or no consistent structure — '
    "do NOT force a clean pattern label onto a messy codebase. "
    'Use "uncatalogued" only for a recognizable pattern not listed above (add pattern_description). '
    "Return multiple hypotheses (one per pattern observed) when different parts of the codebase follow "
    "different patterns — do not collapse mixed evidence into one averaged label."
)


@dataclasses.dataclass
class ArchitectureHypothesis:
    pattern: str
    confidence: float
    fact_ids: list[str]
    pattern_description: str | None = None


@dataclasses.dataclass
class ArchitectureResponse:
    hypotheses: list[ArchitectureHypothesis]
