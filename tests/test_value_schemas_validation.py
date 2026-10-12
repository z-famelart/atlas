"""Feature 01b — validation test: real producer output vs. registered schema.

For every fact type with a registered schema in facts/value_schemas.py AND an
existing producer test fixture/harness, run the real producer and assert the
resulting `value` dict's keys match the schema's dataclass fields exactly (no
more, no less). This is what would catch a producer-side rename at commit
time, before any consumer had a chance to silently misread it.

Reuses the same fixtures/setup each producing feature's own tests already
use (see tests/test_discovery.py, test_git_analysis.py, test_hotspots.py,
test_complexity_adapter.py, test_code_graph.py, test_graphify_provider.py,
test_stage_run_persistence.py, test_architecture.py, test_domain.py,
test_onboarding.py).
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.adapters import AdapterContext, assert_normalizes
from project_intel.architecture.schema import ArchitectureHypothesis
from project_intel.architecture.stage import _hypothesis_to_fact
from project_intel.cli.main import _run_stage_safe
from project_intel.cli.types import PipelineContext, StageRunResult
from project_intel.code_graph import (
    GraphifyProvider,
    aggregate_to_module,
    compute_centrality,
    detect_communities,
    detect_cycles,
)
from project_intel.discovery import run_discovery
from project_intel.discovery.git_detector import GIT_MANIFEST
from project_intel.discovery.scope import ScopeConfig as DiscoveryScopeConfig
from project_intel.domain.schema import BusinessConcept, BusinessWorkflow, GlossaryTerm
from project_intel.domain.stage import _concept_to_fact, _glossary_to_fact, _workflow_to_fact
from project_intel.facts import EntityRef, EntityType, Evidence, Fact, RelationType
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.facts.value_schemas import (
    AggregatedCentralityValue,
    AggregatedCommunityValue,
    AggregatedDependencyCycleValue,
    ArchitectureHypothesisValue,
    BusinessConceptValue,
    BusinessWorkflowValue,
    CentralityValue,
    CommunityValue,
    ComplexityValue,
    DependencyCycleValue,
    DocumentDetectedValue,
    GitChurnValue,
    GitRepositoryDetectedValue,
    GlossaryTermValue,
    HotspotScoreValue,
    HotspotSubScoreValue,
    OnboardingPathValue,
    StageRunResultValue,
    SymbolDefinedValue,
    TechnologyDetectedValue,
)
from project_intel.git_analysis import churn_manifest
from project_intel.hotspots.complexity_adapter import lizard_manifest
from project_intel.hotspots.scorer import compute_hotspots
from project_intel.onboarding.schema import (
    AvoidItem,
    EntryPoint,
    OnboardingPathResponse,
    TimeBoxed,
    WorkflowRef,
)
from project_intel.onboarding.stage import _path_to_fact

FIXTURES = Path(__file__).parent / "fixtures"
_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _assert_keys_match(fact: Fact, schema: type) -> None:
    expected = {f.name for f in dataclasses.fields(schema)}
    actual = set((fact.value or {}).keys())
    assert actual == expected, (
        f"fact type {fact.type!r} value keys {actual} != schema {schema.__name__} fields {expected}"
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_SAMPLE_REPO = FIXTURES / "sample_repo"


def test_technology_detected_matches_schema():
    result = run_discovery(
        root=_SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-01",
        timestamp=_TS,
    )
    tech_facts = [f for f in result.facts if f.type == "technology_detected"]
    assert tech_facts
    for f in tech_facts:
        _assert_keys_match(f, TechnologyDetectedValue)


def test_document_detected_matches_schema():
    result = run_discovery(
        root=_SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-01",
        timestamp=_TS,
    )
    doc_facts = [f for f in result.facts if f.type == "document_detected"]
    assert doc_facts
    for f in doc_facts:
        _assert_keys_match(f, DocumentDetectedValue)


def test_git_repository_detected_matches_schema():
    ctx = AdapterContext(
        target_path=_SAMPLE_REPO,
        run_id="test-run-01",
        repository_id="repo-test",
        timestamp=_TS,
    )
    facts = assert_normalizes(GIT_MANIFEST, FIXTURES / "git_detector" / "rev_parse_output.txt", ctx)
    assert facts
    for f in facts:
        _assert_keys_match(f, GitRepositoryDetectedValue)


# ---------------------------------------------------------------------------
# Git analysis
# ---------------------------------------------------------------------------

_GIT_FIXTURES = FIXTURES / "git_history"
_GIT_CTX = AdapterContext(
    target_path=Path("/repo"),
    run_id="run-test",
    repository_id="repo-test",
    timestamp=_TS,
)


def test_git_churn_matches_schema():
    facts = assert_normalizes(churn_manifest(), _GIT_FIXTURES / "churn.txt", _GIT_CTX)
    assert facts
    for f in facts:
        _assert_keys_match(f, GitChurnValue)


# ---------------------------------------------------------------------------
# Complexity (lizard adapter)
# ---------------------------------------------------------------------------


def test_complexity_matches_schema(tmp_path: Path):
    ctx = AdapterContext(
        target_path=tmp_path, run_id="run-test", repository_id="repo-test", timestamp=_TS
    )
    facts = assert_normalizes(lizard_manifest(), FIXTURES / "lizard_output.json", ctx)
    assert facts
    for f in facts:
        _assert_keys_match(f, ComplexityValue)


# ---------------------------------------------------------------------------
# Hotspots
# ---------------------------------------------------------------------------

_REPO_ID = "test-repo"
_RUN_ID = "test-run"


def _file_fact(store: FactStore, fact_type: str, file_id: str, value: dict) -> None:
    ev = Evidence(
        kind="file",
        ref=FileRef(repository_id=_REPO_ID, path=file_id),
        source_analyzer="test",
        retrieved_at=_TS,
    )
    store.insert_facts([
        Fact(
            id=str(uuid.uuid4()),
            type=fact_type,
            subject=EntityRef(EntityType.FILE, file_id),
            value=value,
            provenance="observed",
            confidence=1.0,
            source_analyzer="test",
            created_at=_TS,
            schema_version=SCHEMA_VERSION,
            run_id=_RUN_ID,
            evidence=(ev,),
        )
    ])


def test_hotspot_score_and_sub_score_match_schema(tmp_path: Path):
    store = FactStore(tmp_path / "facts.sqlite")
    _file_fact(store, "language_detected", "src/a.py", {"loc": 100, "language": "Python"})
    _file_fact(store, "centrality", "src/a.py", {"in_degree": 0.8, "out_degree": 0.2})
    _file_fact(store, "git_churn", "src/a.py", {"commits": 20, "lines_changed": 500})

    facts = compute_hotspots(store, _REPO_ID, _RUN_ID)
    store.close()

    score_facts = [f for f in facts if f.type == "hotspot_score"]
    assert score_facts
    for f in score_facts:
        _assert_keys_match(f, HotspotScoreValue)

    sub_score_facts = [f for f in facts if f.type.startswith("hotspot_") and f.type.endswith("_score") and f.type != "hotspot_score"]
    assert sub_score_facts
    for f in sub_score_facts:
        _assert_keys_match(f, HotspotSubScoreValue)


# ---------------------------------------------------------------------------
# Code graph — file-level
# ---------------------------------------------------------------------------

_REPO = "test-repo"
_RUN = "run-1"


def _evidence(path: str) -> Evidence:
    return Evidence(
        kind="file",
        ref=FileRef(repository_id=_REPO, path=path),
        source_analyzer="test@1.0",
        retrieved_at=_TS,
    )


def _relation_fact(subject: str, predicate: str, obj: str) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type=predicate,
        subject=EntityRef(EntityType.FILE, subject),
        predicate=predicate,
        object=EntityRef(EntityType.FILE, obj),
        value=None,
        evidence=(_evidence(subject),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test@1.0",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def _store_with(*facts: Fact) -> FactStore:
    store = FactStore(":memory:")
    store.insert_facts(list(facts))
    return store


def test_centrality_matches_schema():
    a_b = _relation_fact("a.py", RelationType.IMPORTS.value, "b.py")
    b_c = _relation_fact("b.py", RelationType.IMPORTS.value, "c.py")
    store = _store_with(a_b, b_c)
    facts = compute_centrality(store, _REPO, _RUN)
    assert facts
    for f in facts:
        _assert_keys_match(f, CentralityValue)


def test_community_matches_schema():
    a_b = _relation_fact("a.py", RelationType.IMPORTS.value, "b.py")
    store = _store_with(a_b)
    facts = detect_communities(store, _REPO, _RUN)
    assert facts
    for f in facts:
        _assert_keys_match(f, CommunityValue)


def test_dependency_cycle_matches_schema():
    facts_in = [
        _relation_fact("a.py", RelationType.IMPORTS.value, "b.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "a.py"),
    ]
    store = _store_with(*facts_in)
    result = detect_cycles(store, _REPO, _RUN)
    assert result
    for f in result:
        _assert_keys_match(f, DependencyCycleValue)


# ---------------------------------------------------------------------------
# Code graph — aggregated/module-level
# ---------------------------------------------------------------------------


def _centrality_fact(node: str, in_deg: float, out_deg: float) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="centrality",
        subject=EntityRef(EntityType.FILE, node),
        value={"in_degree": in_deg, "out_degree": out_deg},
        evidence=(_evidence(node),),
        provenance="computed",
        confidence=1.0,
        source_analyzer="code_graph_metrics@1.0",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def test_aggregated_centrality_matches_schema():
    c1 = _centrality_fact("a.py", 0.4, 0.6)
    c2 = _centrality_fact("b.py", 0.2, 0.4)
    store = FactStore(":memory:")
    result = aggregate_to_module([c1, c2], store, "system")
    assert result
    for f in result:
        _assert_keys_match(f, AggregatedCentralityValue)


def _community_fact(node: str, community_id: int) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="community",
        subject=EntityRef(EntityType.FILE, node),
        value={"community_id": community_id},
        evidence=(_evidence(node),),
        provenance="computed",
        confidence=1.0,
        source_analyzer="code_graph_metrics@1.0",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def test_aggregated_community_matches_schema():
    c1 = _community_fact("a.py", 0)
    c2 = _community_fact("b.py", 1)
    store = FactStore(":memory:")
    result = aggregate_to_module([c1, c2], store, "system")
    assert result
    for f in result:
        _assert_keys_match(f, AggregatedCommunityValue)


def _cycle_fact(node: str, members: list[str]) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="dependency_cycle",
        subject=EntityRef(EntityType.FILE, node),
        value={"cycle_members": members},
        evidence=(_evidence(node),),
        provenance="computed",
        confidence=1.0,
        source_analyzer="code_graph_metrics@1.0",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def test_aggregated_dependency_cycle_matches_schema():
    c1 = _cycle_fact("a.py", ["a.py", "b.py"])
    store = FactStore(":memory:")
    result = aggregate_to_module([c1], store, "system")
    assert result
    for f in result:
        _assert_keys_match(f, AggregatedDependencyCycleValue)


# ---------------------------------------------------------------------------
# Graphify provider — symbol_defined
# ---------------------------------------------------------------------------


def test_symbol_defined_matches_schema(tmp_path: Path):
    ctx = AdapterContext(
        target_path=tmp_path, run_id="run-test", repository_id="repo-test", timestamp=_TS
    )
    provider = GraphifyProvider()
    facts = assert_normalizes(provider.manifest(), FIXTURES / "graphify_output.json", ctx)
    symbol_facts = [f for f in facts if f.type == "symbol_defined"]
    assert symbol_facts
    for f in symbol_facts:
        _assert_keys_match(f, SymbolDefinedValue)


# ---------------------------------------------------------------------------
# CLI — stage_run_result
# ---------------------------------------------------------------------------


def test_stage_run_result_matches_schema(tmp_path: Path):
    store = FactStore(tmp_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id, scope=DiscoveryScopeConfig()
    )

    class _FakeStage:
        name = "fake_stage"

        def run(self, ctx: PipelineContext) -> StageRunResult:
            return StageRunResult(name=self.name, status="ok", facts_produced=0, detail=None)

    _run_stage_safe(_FakeStage(), ctx)
    facts = list(store.query_facts(type="stage_run_result", run_id=run_id))
    store.close()
    assert facts
    for f in facts:
        _assert_keys_match(f, StageRunResultValue)


# ---------------------------------------------------------------------------
# Architecture — architecture_hypothesis (pure fact-construction helper)
# ---------------------------------------------------------------------------


def test_architecture_hypothesis_matches_schema():
    hyp = ArchitectureHypothesis(
        pattern="layered", confidence=0.8, fact_ids=["f1"], pattern_description=None
    )
    fact = _hypothesis_to_fact(hyp, run_id="run-1", repository_id="repo-1", now=_TS)
    _assert_keys_match(fact, ArchitectureHypothesisValue)

    hyp_with_desc = ArchitectureHypothesis(
        pattern="uncatalogued", confidence=0.5, fact_ids=[], pattern_description="something odd"
    )
    fact2 = _hypothesis_to_fact(hyp_with_desc, run_id="run-1", repository_id="repo-1", now=_TS)
    _assert_keys_match(fact2, ArchitectureHypothesisValue)


# ---------------------------------------------------------------------------
# Domain — business_concept, business_workflow, glossary_term
# ---------------------------------------------------------------------------


def test_domain_facts_match_schema():
    concept = BusinessConcept(name="Order", description="An order.", fact_ids=["f1"])
    workflow = BusinessWorkflow(name="Checkout", description="Checkout flow.", fact_ids=["f2"])
    glossary = GlossaryTerm(term="SKU", definition="Stock keeping unit.", fact_ids=["f3"])

    concept_fact = _concept_to_fact(concept, run_id="run-1", repo_id="repo-1", now=_TS)
    workflow_fact = _workflow_to_fact(workflow, run_id="run-1", repo_id="repo-1", now=_TS)
    glossary_fact = _glossary_to_fact(glossary, run_id="run-1", repo_id="repo-1", now=_TS)

    _assert_keys_match(concept_fact, BusinessConceptValue)
    _assert_keys_match(workflow_fact, BusinessWorkflowValue)
    _assert_keys_match(glossary_fact, GlossaryTermValue)


# ---------------------------------------------------------------------------
# Onboarding — onboarding_path (pure fact-construction helper)
# ---------------------------------------------------------------------------


def test_onboarding_path_matches_schema():
    response = OnboardingPathResponse(
        entry_points=[EntryPoint(component="api", fact_ids=["f1"], rationale="entrypoint")],
        recommended_workflow=WorkflowRef(description="Read the API layer first.", fact_ids=["f1"]),
        avoid_initially=[AvoidItem(component="legacy", fact_ids=[], rationale="deprecated")],
        time_boxed_understanding=TimeBoxed(thirty_minutes="skim api/", two_hours="read tests too"),
        open_questions=["What owns billing?"],
        confidence=0.6,
        fact_ids=["f1"],
    )
    fact = _path_to_fact(response, run_id="run-1", repo_id="repo-1", now=_TS)
    _assert_keys_match(fact, OnboardingPathValue)
