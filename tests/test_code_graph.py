"""Tests for Feature 05 Part A: code graph interface and metrics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from project_intel.code_graph import (
    aggregate_to_module,
    compute_centrality,
    compute_coverage_gap,
    detect_communities,
    detect_cycles,
)
from project_intel.facts.enums import EntityType, RelationType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore

REPO = "test-repo"
RUN = "run-1"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _evidence(path: str) -> Evidence:
    return Evidence(
        kind="file",
        ref=FileRef(repository_id=REPO, path=path),
        source_analyzer="test@1.0",
        retrieved_at=_now(),
    )


def _relation_fact(subject: str, predicate: str, obj: str, rel_type: str | None = None) -> Fact:
    """Build a relation fact representing a graph edge or a structural relation."""
    actual_type = rel_type if rel_type is not None else predicate
    return Fact(
        id=str(uuid.uuid4()),
        type=actual_type,
        subject=EntityRef(EntityType.FILE, subject),
        predicate=predicate,
        object=EntityRef(EntityType.FILE, obj),
        value=None,
        evidence=(_evidence(subject),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test@1.0",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=RUN,
    )


def _store_with(*facts: Fact) -> FactStore:
    store = FactStore(":memory:")
    store.insert_facts(list(facts))
    return store


# ---------------------------------------------------------------------------
# Centrality
# ---------------------------------------------------------------------------


def test_centrality_in_out_degrees() -> None:
    """A→B, B→C: B has in_degree=1, out_degree=1; A has out_degree=1, in_degree=0."""
    a_b = _relation_fact("a.py", RelationType.IMPORTS.value, "b.py")
    b_c = _relation_fact("b.py", RelationType.IMPORTS.value, "c.py")
    store = _store_with(a_b, b_c)

    facts = compute_centrality(store, REPO, RUN)

    by_node = {f.subject.id: f for f in facts}
    assert set(by_node) == {"a.py", "b.py", "c.py"}

    # In a 3-node graph, max in-degree is 1, centrality = actual / (n-1) = actual / 2
    assert by_node["a.py"].value["in_degree"] == pytest.approx(0.0)
    assert by_node["a.py"].value["out_degree"] == pytest.approx(0.5)
    assert by_node["b.py"].value["in_degree"] == pytest.approx(0.5)
    assert by_node["b.py"].value["out_degree"] == pytest.approx(0.5)
    assert by_node["c.py"].value["in_degree"] == pytest.approx(0.5)
    assert by_node["c.py"].value["out_degree"] == pytest.approx(0.0)

    for f in facts:
        assert f.provenance == "computed"
        assert f.confidence == 1.0


def test_centrality_empty_store() -> None:
    store = FactStore(":memory:")
    assert compute_centrality(store, REPO, RUN) == []


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------


def test_communities_two_clusters() -> None:
    """Two tight clusters: {a,b} and {c,d} connected by one weak bridge."""
    # Cluster 1: a-b dense
    # Cluster 2: c-d dense
    # Bridge: b→c (weak)
    facts = [
        _relation_fact("a.py", RelationType.IMPORTS.value, "b.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "a.py"),
        _relation_fact("c.py", RelationType.IMPORTS.value, "d.py"),
        _relation_fact("d.py", RelationType.IMPORTS.value, "c.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "c.py"),
    ]
    store = _store_with(*facts)

    result = detect_communities(store, REPO, RUN)

    by_node = {f.subject.id: f.value["community_id"] for f in result}
    assert set(by_node) == {"a.py", "b.py", "c.py", "d.py"}

    # a and b must share the same community; c and d must share the same community
    assert by_node["a.py"] == by_node["b.py"]
    assert by_node["c.py"] == by_node["d.py"]
    # The two clusters must be in different communities
    assert by_node["a.py"] != by_node["c.py"]


def test_communities_provenance() -> None:
    facts = [_relation_fact("x.py", RelationType.CALLS.value, "y.py")]
    store = _store_with(*facts)
    result = detect_communities(store, REPO, RUN)
    assert all(f.provenance == "computed" for f in result)


# ---------------------------------------------------------------------------
# Cycle detection (REQUIRED)
# ---------------------------------------------------------------------------


def test_cycle_detection_simple_cycle() -> None:
    """A→B→C→A must produce dependency_cycle facts for all three nodes."""
    facts = [
        _relation_fact("a.py", RelationType.IMPORTS.value, "b.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "c.py"),
        _relation_fact("c.py", RelationType.IMPORTS.value, "a.py"),
    ]
    store = _store_with(*facts)

    result = detect_cycles(store, REPO, RUN)

    assert len(result) == 3
    nodes = {f.subject.id for f in result}
    assert nodes == {"a.py", "b.py", "c.py"}
    for f in result:
        assert f.type == "dependency_cycle"
        assert f.provenance == "computed"
        assert sorted(f.value["cycle_members"]) == ["a.py", "b.py", "c.py"]


def test_cycle_detection_no_cycle() -> None:
    """A→B→C (DAG) must produce no dependency_cycle facts."""
    facts = [
        _relation_fact("a.py", RelationType.IMPORTS.value, "b.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "c.py"),
    ]
    store = _store_with(*facts)
    assert detect_cycles(store, REPO, RUN) == []


def test_cycle_detection_mixed() -> None:
    """One cycle (A→B→A) and one non-cycle node C. Only A and B should appear."""
    facts = [
        _relation_fact("a.py", RelationType.IMPORTS.value, "b.py"),
        _relation_fact("b.py", RelationType.IMPORTS.value, "a.py"),
        _relation_fact("a.py", RelationType.IMPORTS.value, "c.py"),
    ]
    store = _store_with(*facts)
    result = detect_cycles(store, REPO, RUN)
    nodes = {f.subject.id for f in result}
    assert nodes == {"a.py", "b.py"}
    assert "c.py" not in nodes


# ---------------------------------------------------------------------------
# Aggregation
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
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=RUN,
    )


def _belongs_to_fact(file_path: str, dir_path: str) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type=RelationType.BELONGS_TO.value,
        subject=EntityRef(EntityType.FILE, file_path),
        predicate=RelationType.BELONGS_TO.value,
        object=EntityRef(EntityType.DIRECTORY, dir_path),
        value=None,
        evidence=(_evidence(file_path),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test@1.0",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=RUN,
    )


def test_aggregate_to_module_centrality() -> None:
    """Two files in same directory should produce one aggregated module-level fact."""
    c1 = _centrality_fact("src/a.py", 0.5, 0.2)
    c2 = _centrality_fact("src/b.py", 0.3, 0.8)
    b1 = _belongs_to_fact("src/a.py", "src/")
    b2 = _belongs_to_fact("src/b.py", "src/")

    store = _store_with(b1, b2)
    result = aggregate_to_module([c1, c2], store, "module")

    assert len(result) == 1
    agg = result[0]
    assert agg.subject.type == EntityType.DIRECTORY
    assert agg.subject.id == "src/"
    assert agg.type == "centrality"
    assert agg.provenance == "computed"
    assert agg.value["file_count"] == 2
    assert agg.value["mean_in_degree"] == pytest.approx((0.5 + 0.3) / 2)
    assert agg.value["mean_out_degree"] == pytest.approx((0.2 + 0.8) / 2)


def test_aggregate_to_system_level() -> None:
    """System-level aggregation groups everything under '.' root."""
    c1 = _centrality_fact("a.py", 0.4, 0.6)
    c2 = _centrality_fact("b.py", 0.2, 0.4)

    store = FactStore(":memory:")
    result = aggregate_to_module([c1, c2], store, "system")

    assert len(result) == 1
    agg = result[0]
    assert agg.subject.type == EntityType.SYSTEM
    assert agg.subject.id == "."
    assert agg.value["file_count"] == 2


def test_aggregate_invalid_level() -> None:
    store = FactStore(":memory:")
    with pytest.raises(ValueError, match="level must be"):
        aggregate_to_module([], store, "invalid")


# ---------------------------------------------------------------------------
# Coverage gap (Q193 MVP scope vs. actually-detected languages)
# ---------------------------------------------------------------------------


def _language_fact(path: str, language: str, loc: int) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="language_detected",
        subject=EntityRef(EntityType.FILE, path),
        value={"language": language, "loc": loc, "total_lines": loc},
        evidence=(_evidence(path),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="tokei@1.0",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=RUN,
    )


def test_coverage_gap_empty_store() -> None:
    store = FactStore(":memory:")
    assert compute_coverage_gap(store, REPO, RUN) == []


def test_coverage_gap_full_mvp_coverage() -> None:
    """All LOC in MVP languages → no out-of-scope languages, ratio 1.0."""
    store = _store_with(_language_fact("a.py", "Python", 100))
    result = compute_coverage_gap(store, REPO, RUN)
    assert len(result) == 1
    assert result[0].value["out_of_scope_languages"] == {}
    assert result[0].value["coverage_ratio"] == pytest.approx(1.0)
    assert result[0].provenance == "computed"


def test_coverage_gap_reports_excluded_language() -> None:
    """A language outside Q193 (e.g. Elixir) must surface as an explicit gap,
    not silently vanish — Product Brief principle 5 (never pretend to know)."""
    store = _store_with(
        _language_fact("a.py", "Python", 300),
        _language_fact("b.ex", "Elixir", 100),
    )
    result = compute_coverage_gap(store, REPO, RUN)
    assert len(result) == 1
    value = result[0].value
    assert value["in_scope_loc"] == 300
    assert value["out_of_scope_loc"] == 100
    assert value["out_of_scope_languages"] == {"Elixir": 100}
    assert value["coverage_ratio"] == pytest.approx(0.75)
    assert result[0].subject == EntityRef(EntityType.REPOSITORY, REPO)


def test_coverage_gap_php_now_in_scope() -> None:
    """PHP is part of the MVP scope now (Q193 extended) — must count as in-scope."""
    store = _store_with(_language_fact("a.php", "PHP", 50))
    result = compute_coverage_gap(store, REPO, RUN)
    assert result[0].value["out_of_scope_languages"] == {}
    assert result[0].value["in_scope_loc"] == 50


def test_coverage_gap_vue_in_scope() -> None:
    """Vue is part of the scope too (lizard's VueReader, graphify's extract_vue)."""
    store = _store_with(_language_fact("a.vue", "Vue", 40))
    result = compute_coverage_gap(store, REPO, RUN)
    assert result[0].value["out_of_scope_languages"] == {}
    assert result[0].value["in_scope_loc"] == 40
