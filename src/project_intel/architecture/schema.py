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
    "`pattern` must be exactly one of: " + ", ".join(f'"{p}"' for p in _CATALOGUE) + ". "
    "It is NEVER a file path, a glob (e.g. \"ggshield/verticals/secret/output/secret_*.py\"), or a directory name — "
    "those belong in `fact_ids` (which facts support this hypothesis), not in `pattern`. "
    '`pattern` names the architectural pattern itself, not the files it concerns. '
    'Use "big_ball_of_mud" when the graph shows ad-hoc coupling, unclear boundaries, or no consistent structure — '
    "do NOT force a clean pattern label onto a messy codebase. "
    'If none of the catalogued patterns fit, use pattern="uncatalogued" and put a short free-text label '
    "(not a file listing) in `pattern_description`. "
    "Return multiple hypotheses (one per pattern observed) when different parts of the codebase follow "
    "different patterns — do not collapse mixed evidence into one averaged label."
)


def normalize_pattern(pattern: str, pattern_description: str | None) -> tuple[str, str | None]:
    """Force an out-of-catalogue pattern value to "uncatalogued", preserving the original for debugging."""
    if pattern in _CATALOGUE:
        return pattern, pattern_description
    return "uncatalogued", f"(unrecognized pattern value: '{pattern}')"


@dataclasses.dataclass
class ArchitectureHypothesis:
    pattern: str
    confidence: float
    fact_ids: list[str]
    pattern_description: str | None = None


@dataclasses.dataclass
class ArchitectureResponse:
    hypotheses: list[ArchitectureHypothesis]
