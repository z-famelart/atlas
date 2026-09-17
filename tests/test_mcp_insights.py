"""Tests for Feature 12d — type-scoped run resolution and get_insights."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Fact
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.mcp_server import create_server, queries

_FULL = datetime(2024, 1, 1, tzinfo=UTC)
_PARTIAL = datetime(2024, 6, 1, tzinfo=UTC)


def _add(
    store: FactStore,
    fact_type: str,
    subject_id: str,
    run_id: str,
    created_at: datetime,
    value=None,
    object_id: str | None = None,
    confidence: float = 1.0,
    subject_type: EntityType = EntityType.FILE,
) -> None:
    store.insert_facts([
        Fact(
            id=str(uuid.uuid4()),
            type=fact_type,
            subject=EntityRef(subject_type, subject_id),
            object=EntityRef(EntityType.FILE, object_id) if object_id else None,
            value=value,
            provenance="computed",  # type: ignore[arg-type]
            confidence=confidence,
            source_analyzer="test",
            created_at=created_at,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            evidence=(),
        )
    ])


def _insight(store: FactStore, fact_type: str, run_id: str, created_at: datetime, value, conf=0.7):
    _add(store, fact_type, "repo", run_id, created_at, value, confidence=conf,
         subject_type=EntityType.REPOSITORY)


@pytest.fixture()
def store(tmp_path: Path) -> FactStore:
    """A full run followed by `atlas analyze --only architecture`."""
    s = FactStore(tmp_path / "facts.sqlite")
    _add(s, "language_detected", "src/app.py", "full", _FULL, {"language": "Python"})
    _add(s, "hotspot_score", "src/app.py", "full", _FULL, {"combined": 0.8})
    _add(s, "centrality", "src/app.py", "full", _FULL, {"in_degree": 3})
    _add(s, "imports", "src/app.py", "full", _FULL, object_id="src/db.py")
    _insight(s, "business_concept", "full", _FULL, {"name": "Order"})
    _insight(s, "architecture_hypothesis", "full", _FULL, {"pattern": "old"}, conf=0.5)
    _insight(s, "architecture_hypothesis", "arch", _PARTIAL, {"pattern": "layered"}, conf=0.6)
    _insight(s, "architecture_hypothesis", "arch", _PARTIAL, {"pattern": "mvc"}, conf=0.9)
    return s


# --- §2.2: a partial run no longer hides earlier facts ----------------------


def test_queries_survive_partial_run(store: FactStore) -> None:
    assert [h["run_id"] for h in queries.get_hotspots(store)] == ["full"]
    assert [d["object"]["id"] for d in queries.get_dependencies(store, "src/app.py")] == ["src/db.py"]
    assert [d["subject"]["id"] for d in queries.get_dependents(store, "src/db.py")] == ["src/app.py"]
    assert queries.get_path(store, "src/app.py", "src/db.py")["found"] is True
    assert {r["type"] for r in queries.where_to_start(store)} == {"hotspot_score", "centrality"}
    comp = queries.get_component(store, "app.py")
    assert comp is not None and comp["id"] == "src/app.py"
    assert {f["type"] for f in comp["facts"]} == {"language_detected", "hotspot_score", "centrality", "imports"}


def test_get_component_takes_each_type_from_its_latest_run(store: FactStore) -> None:
    _add(store, "hotspot_score", "src/app.py", "hot2", _PARTIAL, {"combined": 0.1})
    comp = queries.get_component(store, "src/app.py")
    assert comp is not None
    by_type = {f["type"]: f["run_id"] for f in comp["facts"]}
    assert by_type["hotspot_score"] == "hot2"
    assert by_type["language_detected"] == "full"
    assert sum(f["type"] == "hotspot_score" for f in comp["facts"]) == 1


def test_get_component_explicit_run_is_exact(store: FactStore) -> None:
    assert queries.get_component(store, "src/app.py", run_id="arch") is None
    comp = queries.get_component(store, "src/app.py", run_id="full")
    assert comp is not None and all(f["run_id"] == "full" for f in comp["facts"])


def test_find_subject_id_exact_wins_and_underscore_is_literal(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "f.sqlite")
    _add(s, "language_detected", "pkg/app.py", "r", _FULL)
    _add(s, "language_detected", "app.py", "r", _FULL)
    _add(s, "language_detected", "src/aXb.py", "r", _FULL)
    assert s.find_subject_id(EntityType.FILE, "APP.py") == "app.py"
    assert s.find_subject_id(EntityType.FILE, "a_b.py") is None
    assert s.find_subject_id(EntityType.REPOSITORY, "app.py") is None


# --- §2.3: get_insights -----------------------------------------------------


def test_get_insights_architecture_latest_run_by_confidence(store: FactStore) -> None:
    result = queries.get_insights(store, "architecture")
    assert [r["value"]["pattern"] for r in result] == ["mvc", "layered"]
    assert result[0]["subject"] == {"type": "Repository", "id": "repo"}


def test_get_insights_falls_back_to_run_that_has_the_kind(store: FactStore) -> None:
    assert [r["run_id"] for r in queries.get_insights(store, "concepts")] == ["full"]
    assert queries.get_insights(store, "glossary") == []


def test_get_insights_explicit_run_and_limit(store: FactStore) -> None:
    assert [r["value"]["pattern"] for r in queries.get_insights(store, "architecture", run_id="full")] == ["old"]
    assert len(queries.get_insights(store, "architecture", limit=1)) == 1
    for i in range(60):
        _insight(store, "glossary_term", "full", _FULL, {"term": f"t{i}"})
    assert len(queries.get_insights(store, "glossary", limit=500)) == 50


def test_get_insights_unknown_kind(store: FactStore) -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        queries.get_insights(store, "hotspots")


def test_get_insights_tool_returns_error_json_for_unknown_kind(tmp_path: Path) -> None:
    (tmp_path / ".atlas-cache").mkdir()
    FactStore(tmp_path / ".atlas-cache" / "facts.sqlite").close()
    server = create_server()
    out = asyncio.run(server.call_tool("get_insights", {"repo_path": str(tmp_path), "kind": "nope"}))
    assert "unknown kind" in json.dumps(out, default=str)
