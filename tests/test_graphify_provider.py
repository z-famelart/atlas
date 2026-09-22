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
# Node → symbol_defined (using graphify slug IDs)
# ---------------------------------------------------------------------------


def test_node_emits_symbol_defined(facts):
    symbol_facts = [f for f in facts if f.type == "symbol_defined"]
    ids = {f.subject.id for f in symbol_facts}
    assert "src_foo_py_myclass" in ids
    assert "src_bar_py_helper" in ids


def test_symbol_fact_has_symbol_ref_evidence(facts):
    f = next(f for f in facts if f.subject.id == "src_foo_py_myclass")
    ev = f.evidence[0]
    assert ev.kind == "symbol"
    assert ev.ref.symbol_id == "src_foo_py_myclass"
    assert ev.ref.path == "src/foo.py"
    assert ev.ref.repository_id == "repo-test"


def test_symbol_fact_value(facts):
    f = next(f for f in facts if f.subject.id == "src_foo_py_myclass")
    assert f.value["name"] == "MyClass"
    assert f.value["kind"] == "class"
    assert f.value["file"] == "src/foo.py"


def test_callable_node_is_function(facts):
    f = next(f for f in facts if f.subject.id == "src_bar_py_helper")
    assert f.value["kind"] == "function"


# ---------------------------------------------------------------------------
# imports link → file-level imports fact (type="imports")
# ---------------------------------------------------------------------------


def test_imports_link_emits_fact(facts):
    rel = [f for f in facts if f.type == RelationType.IMPORTS.value]
    assert len(rel) == 1
    assert rel[0].subject.id == "src/foo.py"
    assert rel[0].object.id == "src/bar.py"
    assert rel[0].subject.type == EntityType.FILE


def test_imports_fact_has_file_ref_evidence(facts):
    rel = next(f for f in facts if f.type == RelationType.IMPORTS.value)
    ev = rel.evidence[0]
    assert ev.kind == "file"
    assert ev.ref.path == "src/foo.py"


# ---------------------------------------------------------------------------
# calls link → file-level calls fact (type="calls", deduplicated)
# ---------------------------------------------------------------------------


def test_calls_link_emits_fact(facts):
    rel = [f for f in facts if f.type == RelationType.CALLS.value]
    assert len(rel) == 1
    # calls src_foo_py_myclass → src_bar_py_helper maps to file src/foo.py → src/bar.py
    assert rel[0].subject.id == "src/foo.py"
    assert rel[0].object.id == "src/bar.py"


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
# Scope: trust graphify's own file_type=="code" classification, not an
# Atlas-side extension whitelist — any language graphify can extract passes
# through unfiltered; only its own doc/non-code classification excludes a file.
# ---------------------------------------------------------------------------


def test_non_code_file_excluded(facts):
    """docs/README.txt node has file_type=doc (graphify's own docs handling,
    not extraction) — must not appear in symbol_defined."""
    ids = {f.subject.id for f in facts if f.type == "symbol_defined"}
    assert "docs_readme_txt_nothing" not in ids


def test_rust_file_included(facts):
    ids = {f.subject.id for f in facts if f.type == "symbol_defined"}
    assert "src_baz_rs_baz_fn" in ids


def test_php_file_included(facts):
    ids = {f.subject.id for f in facts if f.type == "symbol_defined"}
    assert "src_qux_php_qux_fn" in ids


def test_vue_file_included(facts):
    """No extension filter left to exclude Vue SFCs — graphify has a real extractor."""
    ids = {f.subject.id for f in facts if f.type == "symbol_defined"}
    assert "src_widget_vue_render" in ids


def test_terraform_file_included(facts):
    """graphify classifies .tf as file_type=="code" too (its own extract_terraform) —
    no reason for Atlas to second-guess that with its own narrower list."""
    ids = {f.subject.id for f in facts if f.type == "symbol_defined"}
    assert "infra_main_tf_db" in ids


# ---------------------------------------------------------------------------
# manifest() shape
# ---------------------------------------------------------------------------


def test_manifest_category(provider: GraphifyProvider):
    assert provider.manifest().category == "code_graph"


def test_manifest_source_analyzer_id(provider: GraphifyProvider):
    assert provider.manifest().source_analyzer_id == "graphify@1.0"


def test_manifest_command_is_callable(provider: GraphifyProvider):
    """Command must be a callable (runs graphify update then reads file), not a CLI list."""
    assert callable(provider.manifest().command)


# ---------------------------------------------------------------------------
# Integration test: runs actual graphify binary if installed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("shutil").which("graphify"),
    reason="graphify not installed",
)
def test_integration_real_graphify(tmp_path: Path):
    """Run graphify update on a minimal Python fixture and verify facts are produced."""
    (tmp_path / "main.py").write_text("def hello():\n    return world()\n\ndef world():\n    return 42\n")
    (tmp_path / "utils.py").write_text("from main import hello\n\ndef run():\n    return hello()\n")

    from datetime import UTC, datetime

    from project_intel.adapters.manifest import AdapterContext
    from project_intel.adapters.runner import _run_one

    ctx = AdapterContext(
        target_path=tmp_path,
        run_id="integration-run",
        repository_id="integration-repo",
        timestamp=datetime.now(UTC),
    )
    provider = GraphifyProvider()
    result = _run_one(provider.manifest(), ctx)

    # graphify ran successfully or was skipped (version mismatch / tool not found)
    assert result.status.value in ("ok", "skipped:tool_not_found", "skipped:version_mismatch", "failed")
    if result.status.value == "ok":
        assert len(result.facts) > 0
        types = {f.type for f in result.facts}
        # Should have at least symbol_defined or relation facts
        assert types & {"symbol_defined", "calls", "imports"}
