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
    "uncatalogued",
]

CATALOGUE_DESCRIPTION = (
    "Allowed pattern values: " + ", ".join(f'"{p}"' for p in _CATALOGUE[:-1]) + ". "
    'Use "uncatalogued" when none of the above fits and fill pattern_description with a short label.'
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
