"""Tests for Feature 05B — graphify concrete GraphProvider."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.adapters import AdapterContext, assert_normalizes
from project_intel.code_graph import GraphifyProvider
from project_intel.facts import EntityType, RelationType

FIXTURES = Path(__file__).parent / "fixtures"
_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _ctx(tmp_path: Path) -> AdapterContext:
    return AdapterContext(
        target_path=tmp_path,
        run_id="run-test",
        repository_id="repo-test",
        timestamp=_TS,
    )


@pytest.fixture()
def provider() -> GraphifyProvider:
    return GraphifyProvider()


@pytest.fixture()
def facts(provider: GraphifyProvider, tmp_path: Path) -> list:
    return assert_normalizes(
        provider.manifest(),
        FIXTURES / "graphify_output.json",
        _ctx(tmp_path),
    )


# ---------------------------------------------------------------------------
# Contract invariants (source_analyzer, evidence, run_id) — via assert_normalizes
# ---------------------------------------------------------------------------


def test_contract_invariants(facts):
    """assert_normalizes already checks source_analyzer, evidence, run_id."""
    assert len(facts) > 0


# ---------------------------------------------------------------------------
# Node → symbol_defined
# ---------------------------------------------------------------------------


def test_node_emits_symbol_defined(facts):
    symbol_facts = [f for f in facts if f.type == "symbol_defined"]
    ids = {f.subject.id for f in symbol_facts}
    assert "src/foo.py::MyClass" in ids
    assert "src/bar.py::helper" in ids


def test_symbol_fact_has_symbol_ref_evidence(facts):
    f = next(f for f in facts if f.subject.id == "src/foo.py::MyClass")
    ev = f.evidence[0]
    assert ev.kind == "symbol"
    assert ev.ref.symbol_id == "src/foo.py::MyClass"
    assert ev.ref.path == "src/foo.py"
    assert ev.ref.repository_id == "repo-test"


def test_symbol_fact_value(facts):
    f = next(f for f in facts if f.subject.id == "src/foo.py::MyClass")
    assert f.value == {"name": "MyClass", "kind": "class"}


# ---------------------------------------------------------------------------
# imports edge → RelationType.IMPORTS
# ---------------------------------------------------------------------------


def test_imports_edge_emits_relation(facts):
    rel = [f for f in facts if f.type == "relation" and f.predicate == RelationType.IMPORTS]
    assert len(rel) == 1
    assert rel[0].subject == (
        rel[0].subject.__class__(EntityType.FILE, "src/foo.py")
    )
    assert rel[0].object.id == "src/bar.py"


def test_imports_fact_has_file_ref_evidence(facts):
    rel = next(f for f in facts if f.type == "relation" and f.predicate == RelationType.IMPORTS)
    ev = rel.evidence[0]
    assert ev.kind == "file"
    assert ev.ref.path == "src/foo.py"


# ---------------------------------------------------------------------------
# calls edge → RelationType.CALLS
# ---------------------------------------------------------------------------


def test_calls_edge_emits_relation(facts):
    rel = [f for f in facts if f.type == "relation" and f.predicate == RelationType.CALLS]
    assert len(rel) == 1
    assert rel[0].subject.id == "src/foo.py::MyClass"
    assert rel[0].object.id == "src/bar.py::helper"


# ---------------------------------------------------------------------------
# provenance = "observed" on all facts
# ---------------------------------------------------------------------------


def test_all_facts_observed(facts):
    assert all(f.provenance == "observed" for f in facts)


# ---------------------------------------------------------------------------
# source_analyzer = "graphify@1.0" on all facts
# ---------------------------------------------------------------------------


def test_all_facts_source_analyzer(facts):
    assert all(f.source_analyzer == "graphify@1.0" for f in facts)


# ---------------------------------------------------------------------------
# Files outside MVP language list are not emitted
# ---------------------------------------------------------------------------


def test_non_mvp_file_excluded(facts):
    """docs/README.txt node must not appear (not a supported extension)."""
    ids = {f.subject.id for f in facts}
    assert "docs/README.txt::nothing" not in ids


def test_rust_file_included(facts):
    """src/baz.rs is in the MVP list — its node must be emitted."""
    ids = {f.subject.id for f in facts}
    assert "src/baz.rs::baz_fn" in ids


# ---------------------------------------------------------------------------
# manifest() shape
# ---------------------------------------------------------------------------


def test_manifest_category(provider: GraphifyProvider):
    assert provider.manifest().category == "code_graph"


def test_manifest_source_analyzer_id(provider: GraphifyProvider):
    assert provider.manifest().source_analyzer_id == "graphify@1.0"
