"""Typed schemas for `Fact.value` dicts — Feature 01b.

One frozen/slotted dataclass per fact type, matching each producer's real
`value={...}` construction exactly (see specs/features/01b-fact-value-schemas.md
for the audit this is built from). Each dataclass has a matching accessor
function that raises `TypeError` if `fact.value`'s keys don't match the
schema exactly — this replaces the silent-fallback failure mode of
`fact.value.get("wrong_key", default)`.

`imports`, `calls`, `inherits_from`, and `depends_on` facts carry no `value`
(the relation itself, via `predicate`/`object`, is the payload) and so have
no schema here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Fact

# ── Discovery (Feature 01/02) ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TechnologyDetectedValue:
    category: str
    name: str


@dataclass(frozen=True, slots=True)
class DocumentDetectedValue:
    role: str


@dataclass(frozen=True, slots=True)
class GitRepositoryDetectedValue:
    git_dir: str


@dataclass(frozen=True, slots=True)
class LanguageDetectedValue:
    language: str
    loc: int
    total_lines: int


# ── Git analysis (Feature 04) ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GitChurnValue:
    commits: int
    lines_changed: int


@dataclass(frozen=True, slots=True)
class GitOwnershipValue:
    top_author: str
    top_pct: float
    authors: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class FileAgeValue:
    days_since_modified: int
    last_modified: str


@dataclass(frozen=True, slots=True)
class FileRoleValue:
    role: str


@dataclass(frozen=True, slots=True)
class GitCouplingValue:
    co_changes: int
    coupling_pct: float
    is_test_pair: bool
    cross_boundary: bool


# ── Hotspots (Feature 05) ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ComplexityValue:
    score: float
    nloc: int


@dataclass(frozen=True, slots=True)
class HotspotScoreValue:
    combined: float
    components_available: str
    components: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HotspotSubScoreValue:
    """Value shape of `hotspot_<name>_score` facts (dynamic type name, one
    per component in ("complexity", "size", "centrality", "churn"))."""

    raw: float
    normalized: float
    weight: float


# ── Code graph, file-level (Feature 05) ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CentralityValue:
    in_degree: float
    out_degree: float


@dataclass(frozen=True, slots=True)
class CommunityValue:
    community_id: int


@dataclass(frozen=True, slots=True)
class DependencyCycleValue:
    cycle_members: list[str]


# ── Code graph, aggregated/module-level (Feature 05) ─────────────────────────


@dataclass(frozen=True, slots=True)
class AggregatedCentralityValue:
    mean_in_degree: float
    mean_out_degree: float
    file_count: int


@dataclass(frozen=True, slots=True)
class AggregatedCommunityValue:
    community_ids: list[int]
    file_count: int


@dataclass(frozen=True, slots=True)
class AggregatedDependencyCycleValue:
    cycle_members: list[str]
    file_count: int


# ── Code graph, symbols (graphify provider) ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class SymbolDefinedValue:
    name: str
    kind: str
    file: str


# ── CLI (Feature 06c) ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StageRunResultValue:
    stage: str
    status: str
    facts_produced: int
    detail: str | None


# ── Architecture (Feature 08) ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ArchitectureHypothesisValue:
    pattern: str
    confidence: float
    fact_ids: list[str]
    pattern_description: str | None


# ── Domain understanding (Feature 09) ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BusinessConceptValue:
    name: str
    description: str
    fact_ids: list[str]


@dataclass(frozen=True, slots=True)
class BusinessWorkflowValue:
    name: str
    description: str
    fact_ids: list[str]


@dataclass(frozen=True, slots=True)
class GlossaryTermValue:
    term: str
    definition: str
    fact_ids: list[str]


# ── Onboarding path (Feature 10) ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OnboardingPathValue:
    entry_points: list[dict[str, Any]]
    recommended_workflow: dict[str, Any]
    avoid_initially: list[dict[str, Any]]
    time_boxed_understanding: dict[str, Any]
    open_questions: list[str]
    confidence: float
    fact_ids: list[str]


# ── Accessors ─────────────────────────────────────────────────────────────
# Each raises TypeError if fact.value's keys don't match the schema exactly.


def technology_detected_value(fact: Fact) -> TechnologyDetectedValue:
    return TechnologyDetectedValue(**(fact.value or {}))


def document_detected_value(fact: Fact) -> DocumentDetectedValue:
    return DocumentDetectedValue(**(fact.value or {}))


def git_repository_detected_value(fact: Fact) -> GitRepositoryDetectedValue:
    return GitRepositoryDetectedValue(**(fact.value or {}))


def language_detected_value(fact: Fact) -> LanguageDetectedValue:
    return LanguageDetectedValue(**(fact.value or {}))


def git_churn_value(fact: Fact) -> GitChurnValue:
    return GitChurnValue(**(fact.value or {}))


def git_ownership_value(fact: Fact) -> GitOwnershipValue:
    return GitOwnershipValue(**(fact.value or {}))


def file_age_value(fact: Fact) -> FileAgeValue:
    return FileAgeValue(**(fact.value or {}))


def file_role_value(fact: Fact) -> FileRoleValue:
    return FileRoleValue(**(fact.value or {}))


def git_coupling_value(fact: Fact) -> GitCouplingValue:
    return GitCouplingValue(**(fact.value or {}))


def complexity_value(fact: Fact) -> ComplexityValue:
    return ComplexityValue(**(fact.value or {}))


def hotspot_score_value(fact: Fact) -> HotspotScoreValue:
    return HotspotScoreValue(**(fact.value or {}))


def hotspot_sub_score_value(fact: Fact) -> HotspotSubScoreValue:
    """Accessor for `hotspot_<name>_score` facts (dynamic type name)."""
    return HotspotSubScoreValue(**(fact.value or {}))


def centrality_value(fact: Fact) -> CentralityValue:
    return CentralityValue(**(fact.value or {}))


def community_value(fact: Fact) -> CommunityValue:
    return CommunityValue(**(fact.value or {}))


def dependency_cycle_value(fact: Fact) -> DependencyCycleValue:
    return DependencyCycleValue(**(fact.value or {}))


def aggregated_centrality_value(fact: Fact) -> AggregatedCentralityValue:
    return AggregatedCentralityValue(**(fact.value or {}))


def aggregated_community_value(fact: Fact) -> AggregatedCommunityValue:
    return AggregatedCommunityValue(**(fact.value or {}))


def aggregated_dependency_cycle_value(fact: Fact) -> AggregatedDependencyCycleValue:
    return AggregatedDependencyCycleValue(**(fact.value or {}))


def symbol_defined_value(fact: Fact) -> SymbolDefinedValue:
    return SymbolDefinedValue(**(fact.value or {}))


def stage_run_result_value(fact: Fact) -> StageRunResultValue:
    return StageRunResultValue(**(fact.value or {}))


def architecture_hypothesis_value(fact: Fact) -> ArchitectureHypothesisValue:
    return ArchitectureHypothesisValue(**(fact.value or {}))


def business_concept_value(fact: Fact) -> BusinessConceptValue:
    return BusinessConceptValue(**(fact.value or {}))


def business_workflow_value(fact: Fact) -> BusinessWorkflowValue:
    return BusinessWorkflowValue(**(fact.value or {}))


def glossary_term_value(fact: Fact) -> GlossaryTermValue:
    return GlossaryTermValue(**(fact.value or {}))


def onboarding_path_value(fact: Fact) -> OnboardingPathValue:
    return OnboardingPathValue(**(fact.value or {}))
