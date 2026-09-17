"""Tests for Feature 12 — MCP server query primitives."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.mcp_server import create_server, queries
from project_intel.mcp_server.server import _db_path, _missing, _open_store

_RUN = "test-run"
_REPO = "test-repo"


def _now() -> datetime:
    return datetime.now(UTC)


def _ev(file_id: str) -> Evidence:
    return Evidence(
        kind="file",
        ref=FileRef(repository_id=_REPO, path=file_id),
        source_analyzer="test",
        retrieved_at=_now(),
    )


def _fact(
    store: FactStore,
    fact_type: str,
    subject_id: str,
    value=None,
    object_id: str | None = None,
    provenance: str = "computed",
    confidence: float = 1.0,
    run_id: str = _RUN,
) -> Fact:
    f = Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(EntityType.FILE, subject_id),
        object=EntityRef(EntityType.FILE, object_id) if object_id else None,
        value=value,
        provenance=provenance,  # type: ignore[arg-type]
        confidence=confidence,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        evidence=(_ev(subject_id),),
    )
    store.insert_facts([f])
    return f


@pytest.fixture()
def store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


# ---------------------------------------------------------------------------
# get_component
# ---------------------------------------------------------------------------


def test_get_component_exact(store: FactStore) -> None:
    _fact(store, "language_detected", "src/app.py", value={"language": "Python"})
    result = queries.get_component(store, "src/app.py")
    assert result is not None
    assert result["id"] == "src/app.py"


def test_get_component_suffix(store: FactStore) -> None:
    _fact(store, "language_detected", "src/app.py", value={})
    result = queries.get_component(store, "app.py")
    assert result is not None
    assert result["id"] == "src/app.py"


def test_get_component_not_found(store: FactStore) -> None:
    assert queries.get_component(store, "nonexistent.py") is None


# ---------------------------------------------------------------------------
# get_dependencies / get_dependents
# ---------------------------------------------------------------------------


def test_get_dependencies_basic(store: FactStore) -> None:
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    _fact(store, "calls", "src/a.py", object_id="src/c.py")
    deps = queries.get_dependencies(store, "src/a.py")
    targets = {d["object"]["id"] for d in deps}
    assert targets == {"src/b.py", "src/c.py"}


def test_get_dependents_basic(store: FactStore) -> None:
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    _fact(store, "imports", "src/c.py", object_id="src/b.py")
    deps = queries.get_dependents(store, "src/b.py")
    sources = {d["subject"]["id"] for d in deps}
    assert sources == {"src/a.py", "src/c.py"}


def test_get_dependencies_cap_50(store: FactStore) -> None:
    for i in range(100):
        _fact(store, "imports", "src/hub.py", object_id=f"src/dep_{i}.py")
    result = queries.get_dependencies(store, "src/hub.py", limit=100)
    assert len(result) <= 50


def test_get_dependents_cap_50(store: FactStore) -> None:
    for i in range(100):
        _fact(store, "imports", f"src/dep_{i}.py", object_id="src/hub.py")
    result = queries.get_dependents(store, "src/hub.py", limit=100)
    assert len(result) <= 50


# ---------------------------------------------------------------------------
# find_workflow
# ---------------------------------------------------------------------------


def test_find_workflow_match(store: FactStore) -> None:
    _fact(store, "business_workflow", "auth", value={"name": "user authentication", "steps": ["login"]})
    result = queries.find_workflow(store, "authentication")
    assert len(result) == 1


def test_find_workflow_no_match(store: FactStore) -> None:
    _fact(store, "business_workflow", "auth", value={"name": "user authentication"})
    assert queries.find_workflow(store, "payment") == []


def test_find_workflow_cap_20(store: FactStore) -> None:
    for i in range(40):
        _fact(store, "business_workflow", f"wf_{i}", value={"name": f"workflow {i}"})
    result = queries.find_workflow(store, "workflow", limit=40)
    assert len(result) <= 20


# ---------------------------------------------------------------------------
# get_hotspots
# ---------------------------------------------------------------------------


def test_get_hotspots_sorted(store: FactStore) -> None:
    _fact(store, "hotspot_score", "src/a.py", value={"combined": 0.9})
    _fact(store, "hotspot_score", "src/b.py", value={"combined": 0.3})
    _fact(store, "hotspot_score", "src/c.py", value={"combined": 0.6})
    result = queries.get_hotspots(store, top_n=10)
    scores = [r["value"]["combined"] for r in result]
    assert scores == sorted(scores, reverse=True)


def test_get_hotspots_cap_50(store: FactStore) -> None:
    for i in range(100):
        _fact(store, "hotspot_score", f"src/f_{i}.py", value={"combined": float(i) / 100})
    result = queries.get_hotspots(store, top_n=100)
    assert len(result) <= 50


def test_get_hotspots_component_filter(store: FactStore) -> None:
    _fact(store, "hotspot_score", "src/auth/login.py", value={"combined": 0.9})
    _fact(store, "hotspot_score", "src/billing/pay.py", value={"combined": 0.8})
    result = queries.get_hotspots(store, top_n=10, component="auth")
    assert all("auth" in r["subject"]["id"] for r in result)


# ---------------------------------------------------------------------------
# Provenance/confidence/evidence survive through get_hotspots
# ---------------------------------------------------------------------------


def test_get_hotspots_provenance_survives(store: FactStore) -> None:
    """Provenance, confidence, and evidence shape must survive end-to-end."""
    _fact(
        store,
        "hotspot_score",
        "src/a.py",
        value={"combined": 0.7, "complexity_score": 0.5},
        provenance="computed",
        confidence=0.85,
    )
    result = queries.get_hotspots(store, top_n=5)
    assert len(result) == 1
    r = result[0]
    assert r["provenance"] == "computed"
    assert r["confidence"] == 0.85
    assert len(r["evidence"]) == 1
    assert r["evidence"][0]["kind"] == "file"


# ---------------------------------------------------------------------------
# get_path
# ---------------------------------------------------------------------------


def test_get_path_direct(store: FactStore) -> None:
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    result = queries.get_path(store, "src/a.py", "src/b.py")
    assert result["found"] is True
    assert result["path"] == ["src/a.py", "src/b.py"]


def test_get_path_indirect(store: FactStore) -> None:
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    _fact(store, "imports", "src/b.py", object_id="src/c.py")
    result = queries.get_path(store, "src/a.py", "src/c.py")
    assert result["found"] is True
    assert result["path"] == ["src/a.py", "src/b.py", "src/c.py"]


def test_get_path_not_found(store: FactStore) -> None:
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    result = queries.get_path(store, "src/a.py", "src/z.py")
    assert result["found"] is False
    assert result["reason"] == "no path within bound"


def test_get_path_depth_limit(store: FactStore) -> None:
    """A chain longer than max_depth must return 'no path within bound'."""
    # Build a chain: a -> b -> c -> d -> e -> f (length 5 hops)
    chain = [f"src/node_{i}.py" for i in range(7)]
    for i in range(len(chain) - 1):
        _fact(store, "imports", chain[i], object_id=chain[i + 1])
    # With max_depth=3, path from chain[0] to chain[6] (6 hops) must not be found
    result = queries.get_path(store, chain[0], chain[6], max_depth=3)
    assert result["found"] is False
    assert result["reason"] == "no path within bound"


def test_get_path_depth_cap_10(store: FactStore) -> None:
    """max_depth > 10 is silently capped to 10."""
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    result = queries.get_path(store, "src/a.py", "src/b.py", max_depth=999)
    assert result["found"] is True  # still works, just capped


# ---------------------------------------------------------------------------
# No mutation: every primitive leaves the store unchanged
# ---------------------------------------------------------------------------


def _count_facts(store: FactStore) -> int:
    return sum(1 for _ in store.query_facts())


def test_no_mutation(store: FactStore, tmp_path: Path) -> None:
    """Every primitive must be read-only — store fact count unchanged after all calls."""
    _fact(store, "hotspot_score", "src/a.py", value={"combined": 0.5})
    _fact(store, "imports", "src/a.py", object_id="src/b.py")
    _fact(store, "business_workflow", "wf1", value={"name": "auth workflow"})
    _fact(store, "language_detected", "src/a.py", value={"language": "Python"})

    before = _count_facts(store)

    queries.get_component(store, "src/a.py")
    queries.get_dependencies(store, "src/a.py")
    queries.get_dependents(store, "src/b.py")
    queries.find_workflow(store, "auth")
    queries.get_hotspots(store, top_n=10)
    queries.get_path(store, "src/a.py", "src/b.py")
    queries.where_to_start(store)

    assert _count_facts(store) == before


# ---------------------------------------------------------------------------
# Server can be instantiated independently (no CLI process)
# ---------------------------------------------------------------------------


def test_create_server() -> None:
    """Global server instantiates with no arguments and lists all 8 tools."""
    import asyncio

    server = create_server()

    async def _list() -> list[str]:
        result = await server.list_tools()
        return [t.name for t in result]

    tool_names = asyncio.run(_list())
    expected = {
        "get_component",
        "get_dependencies",
        "get_dependents",
        "find_workflow",
        "get_hotspots",
        "get_path",
        "where_to_start",
        "get_insights",
    }
    assert expected == set(tool_names)


# ---------------------------------------------------------------------------
# Global server helpers: db_path derivation, open_store, missing-store error
# ---------------------------------------------------------------------------


def test_db_path_derivation(tmp_path: Path) -> None:
    """db_path is always <repo_path>/.atlas-cache/facts.sqlite."""
    result = _db_path(str(tmp_path))
    assert result == tmp_path / ".atlas-cache" / "facts.sqlite"


def test_open_store_missing_returns_none(tmp_path: Path) -> None:
    """_open_store returns None when no facts.sqlite exists at the derived path."""
    assert _open_store(str(tmp_path)) is None


def test_open_store_returns_store_when_present(tmp_path: Path) -> None:
    """_open_store opens a FactStore when the database exists."""
    db = tmp_path / ".atlas-cache" / "facts.sqlite"
    db.parent.mkdir()
    FactStore(db).close()  # create the file

    store = _open_store(str(tmp_path))
    assert store is not None
    store.close()


def test_missing_store_error_json(tmp_path: Path) -> None:
    """Missing store returns structured JSON with expected_path and hint."""
    import json as _json

    err = _json.loads(_missing(str(tmp_path)))
    assert err["error"] == "no facts store found"
    assert str(tmp_path / ".atlas-cache" / "facts.sqlite") in err["expected_path"]
    assert "atlas analyze" in err["hint"]


def test_multi_repo_isolation(tmp_path: Path) -> None:
    """Two different repo_paths open their own store independently."""
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    for repo in (repo_a, repo_b):
        (repo / ".atlas-cache").mkdir(parents=True)

    store_a = FactStore(repo_a / ".atlas-cache" / "facts.sqlite")
    store_b = FactStore(repo_b / ".atlas-cache" / "facts.sqlite")
    _fact(store_a, "hotspot_score", "src/only_in_a.py", value={"combined": 0.9})
    _fact(store_b, "hotspot_score", "src/only_in_b.py", value={"combined": 0.8})
    store_a.close()
    store_b.close()

    opened_a = _open_store(str(repo_a))
    opened_b = _open_store(str(repo_b))
    assert opened_a is not None and opened_b is not None

    hotspots_a = queries.get_hotspots(opened_a, top_n=5)
    hotspots_b = queries.get_hotspots(opened_b, top_n=5)
    opened_a.close()
    opened_b.close()

    ids_a = {r["subject"]["id"] for r in hotspots_a}
    ids_b = {r["subject"]["id"] for r in hotspots_b}
    assert ids_a == {"src/only_in_a.py"}
    assert ids_b == {"src/only_in_b.py"}


# ---------------------------------------------------------------------------
# where_to_start fallback
# ---------------------------------------------------------------------------


def test_where_to_start_fallback(store: FactStore) -> None:
    _fact(store, "hotspot_score", "src/a.py", value={"combined": 0.9})
    _fact(store, "centrality", "src/b.py", value={"in_degree": 0.8, "out_degree": 0.1})
    result = queries.where_to_start(store)
    assert len(result) > 0


def test_where_to_start_uses_onboarding_path(store: FactStore) -> None:
    _fact(store, "onboarding_path", "system", value={"step": 1, "component": "src/a.py"})
    result = queries.where_to_start(store)
    assert any(r["type"] == "onboarding_path" for r in result)


# ---------------------------------------------------------------------------
# Run scoping (Feature 12c) — defaults to latest run, explicit run_id honored
# ---------------------------------------------------------------------------


def _older() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


def _newer() -> datetime:
    return datetime(2024, 6, 1, tzinfo=UTC)


def _fact_at(
    store: FactStore,
    fact_type: str,
    subject_id: str,
    created_at: datetime,
    run_id: str,
    value=None,
    object_id: str | None = None,
) -> Fact:
    f = Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(EntityType.FILE, subject_id),
        object=EntityRef(EntityType.FILE, object_id) if object_id else None,
        value=value,
        provenance="computed",  # type: ignore[arg-type]
        confidence=1.0,
        source_analyzer="test",
        created_at=created_at,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        evidence=(_ev(subject_id),),
    )
    store.insert_facts([f])
    return f


def test_get_hotspots_defaults_to_latest_run(store: FactStore) -> None:
    _fact_at(store, "hotspot_score", "src/a.py", _older(), "run-old", value={"combined": 0.9})
    _fact_at(store, "hotspot_score", "src/a.py", _newer(), "run-new", value={"combined": 0.4})
    result = queries.get_hotspots(store, top_n=10)
    assert len(result) == 1
    assert result[0]["run_id"] == "run-new"
    assert result[0]["value"]["combined"] == 0.4


def test_get_hotspots_explicit_run_id(store: FactStore) -> None:
    _fact_at(store, "hotspot_score", "src/a.py", _older(), "run-old", value={"combined": 0.9})
    _fact_at(store, "hotspot_score", "src/a.py", _newer(), "run-new", value={"combined": 0.4})
    result = queries.get_hotspots(store, top_n=10, run_id="run-old")
    assert len(result) == 1
    assert result[0]["run_id"] == "run-old"
    assert result[0]["value"]["combined"] == 0.9


def test_get_dependencies_defaults_to_latest_run(store: FactStore) -> None:
    _fact_at(store, "imports", "src/a.py", _older(), "run-old", object_id="src/old_dep.py")
    _fact_at(store, "imports", "src/a.py", _newer(), "run-new", object_id="src/new_dep.py")
    result = queries.get_dependencies(store, "src/a.py")
    assert {r["object"]["id"] for r in result} == {"src/new_dep.py"}


def test_where_to_start_fallback_uses_one_resolved_run_id(store: FactStore) -> None:
    _fact_at(store, "hotspot_score", "src/a.py", _older(), "run-old", value={"combined": 0.9})
    _fact_at(store, "centrality", "src/b.py", _older(), "run-old", value={"in_degree": 0.8})
    _fact_at(store, "hotspot_score", "src/c.py", _newer(), "run-new", value={"combined": 0.7})
    _fact_at(store, "centrality", "src/d.py", _newer(), "run-new", value={"in_degree": 0.6})

    result = queries.where_to_start(store)
    run_ids = {r["run_id"] for r in result}
    assert run_ids == {"run-new"}
