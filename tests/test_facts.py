"""Tests for Feature 01 — Facts & Evidence model."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.facts import (
    SCHEMA_VERSION,
    CommitRef,
    Entity,
    EntityRef,
    EntityType,
    Evidence,
    ExternalRef,
    Fact,
    FactStatus,
    FactStore,
    FileRef,
    LineRef,
    RelationType,
    SchemaVersionError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_evidence(kind: str = "file") -> Evidence:
    ref: FileRef | CommitRef
    if kind == "file":
        ref = FileRef(repository_id="repo-1", path="src/main.py")
    else:
        ref = CommitRef(repository_id="repo-1", commit_hash="abc123" * 6 + "ab")
    return Evidence(
        kind=kind,  # type: ignore[arg-type]
        ref=ref,
        source_analyzer="test-analyzer",
        retrieved_at=_TS,
    )


def _make_fact(
    fact_id: str = "fact-1",
    created_at: datetime = _TS,
    run_id: str = "run-1",
) -> Fact:
    return Fact(
        id=fact_id,
        type="file_exists",
        subject=EntityRef(type=EntityType.FILE, id="src/main.py"),
        evidence=(_make_evidence(),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test-analyzer",
        created_at=created_at,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


@pytest.fixture
def store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.db")


# ---------------------------------------------------------------------------
# Immutability — frozen=True enforcement
# ---------------------------------------------------------------------------


def test_fact_frozen():
    fact = _make_fact()
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.type = "changed"  # type: ignore[misc]


def test_evidence_frozen():
    ev = _make_evidence()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.kind = "commit"  # type: ignore[misc]


def test_entity_ref_frozen():
    ref = EntityRef(type=EntityType.FILE, id="src/foo.py")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Closed types — slots=True enforcement
# ---------------------------------------------------------------------------


def test_fact_slots_closed():
    # frozen=True+slots=True raises AttributeError or TypeError depending on CPython version.
    fact = _make_fact()
    with pytest.raises((AttributeError, TypeError)):
        fact.nonexistent_field = "boom"  # type: ignore[attr-defined]


def test_evidence_slots_closed():
    ev = _make_evidence()
    with pytest.raises((AttributeError, TypeError)):
        ev.nonexistent_field = "boom"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Defensive copy — mutating source list must not affect Fact.evidence
# ---------------------------------------------------------------------------


def test_fact_evidence_defensive_copy():
    ev = _make_evidence()
    ev_list = [ev]
    fact = Fact(
        id="f1",
        type="file_exists",
        subject=EntityRef(type=EntityType.FILE, id="x"),
        evidence=ev_list,  # type: ignore[arg-type]  # pass a list
        provenance="observed",
        confidence=1.0,
        source_analyzer="test",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id="r1",
    )
    ev_list.append(_make_evidence("commit"))
    ev_list.clear()

    assert len(fact.evidence) == 1
    assert fact.evidence[0] is ev


def test_fact_evidence_is_tuple():
    assert isinstance(_make_fact().evidence, tuple)


# ---------------------------------------------------------------------------
# Entity defensive copy
# ---------------------------------------------------------------------------


def test_entity_attributes_defensive_copy():
    attrs: dict = {"lang": "python"}
    entity = Entity(type=EntityType.FILE, id="src/x.py", attributes=attrs)
    attrs["lang"] = "mutated"
    assert entity.attributes["lang"] == "python"


# ---------------------------------------------------------------------------
# FactStore — basic insert + query
# ---------------------------------------------------------------------------


def test_store_insert_and_query_by_type(store: FactStore):
    store.insert_facts([_make_fact()])
    results = list(store.query_facts(type="file_exists"))
    assert len(results) == 1
    assert results[0].type == "file_exists"


def test_store_insert_and_query_by_subject(store: FactStore):
    store.insert_facts([_make_fact()])
    subject = EntityRef(type=EntityType.FILE, id="src/main.py")
    results = list(store.query_facts(subject=subject))
    assert len(results) == 1
    assert results[0].subject == subject


def test_store_insert_and_query_by_run_id(store: FactStore):
    store.insert_facts([_make_fact(fact_id="f1", run_id="run-A")])
    store.insert_facts([_make_fact(fact_id="f2", run_id="run-B")])
    results = list(store.query_facts(run_id="run-A"))
    assert len(results) == 1
    assert results[0].run_id == "run-A"


def test_store_insert_and_query_by_provenance(store: FactStore):
    store.insert_facts([_make_fact()])
    assert len(list(store.query_facts(provenance="observed"))) == 1
    assert len(list(store.query_facts(provenance="computed"))) == 0


def test_store_query_no_filter_returns_all(store: FactStore):
    store.insert_facts([_make_fact("f1"), _make_fact("f2")])
    assert len(list(store.query_facts())) == 2


def test_latest_run_id_empty_store(store: FactStore):
    assert store.latest_run_id() is None


def test_latest_run_id_picks_greatest_created_at(store: FactStore):
    older = datetime(2024, 1, 1, tzinfo=UTC)
    newer = datetime(2024, 6, 1, tzinfo=UTC)
    store.insert_facts([_make_fact("f1", created_at=older, run_id="run-old")])
    store.insert_facts([_make_fact("f2", created_at=newer, run_id="run-new")])
    assert store.latest_run_id() == "run-new"


# ---------------------------------------------------------------------------
# FactStore — evidence round-trip
# ---------------------------------------------------------------------------


def test_store_evidence_round_trip(store: FactStore):
    ev = Evidence(
        kind="line",
        ref=LineRef(
            repository_id="repo-1",
            path="src/main.py",
            line_start=42,
            commit_hash="deadbeef" * 5,
            line_end=55,
        ),
        source_analyzer="linter",
        retrieved_at=_TS,
    )
    fact = Fact(
        id="f-line",
        type="complexity_high",
        subject=EntityRef(type=EntityType.FILE, id="src/main.py"),
        evidence=(ev,),
        provenance="computed",
        confidence=0.9,
        source_analyzer="linter",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id="r1",
    )
    store.insert_facts([fact])
    results = list(store.query_facts())
    assert len(results) == 1
    restored = results[0]
    assert restored.evidence[0].kind == "line"
    assert restored.evidence[0].ref == ev.ref


# ---------------------------------------------------------------------------
# FactStore — relation fact round-trip (predicate + object)
# ---------------------------------------------------------------------------


def test_store_relation_fact_round_trip(store: FactStore):
    fact = Fact(
        id="f-rel",
        type="depends_on",
        subject=EntityRef(type=EntityType.FILE, id="src/a.py"),
        predicate="depends_on",
        object=EntityRef(type=EntityType.FILE, id="src/b.py"),
        evidence=(_make_evidence(),),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id="r1",
    )
    store.insert_facts([fact])
    results = list(store.query_facts())
    r = results[0]
    assert r.predicate == "depends_on"
    assert r.object == EntityRef(type=EntityType.FILE, id="src/b.py")


# ---------------------------------------------------------------------------
# FactStore — no update-by-id (insert same id raises)
# ---------------------------------------------------------------------------


def test_store_no_update_by_id(store: FactStore):
    store.insert_facts([_make_fact("dup-id")])
    with pytest.raises(Exception):  # noqa: B017 — any DB integrity error
        store.insert_facts([_make_fact("dup-id")])


# ---------------------------------------------------------------------------
# FactStore — close/reopen round-trip (recomputability)
# ---------------------------------------------------------------------------


def test_store_reopen_round_trip(tmp_path: Path):
    db_path = tmp_path / "facts.db"

    store1 = FactStore(db_path)
    store1.insert_facts([_make_fact()])
    store1.close()

    store2 = FactStore(db_path)
    results = list(store2.query_facts())
    store2.close()

    assert len(results) == 1
    assert results[0].id == "fact-1"
    assert results[0].type == "file_exists"


# ---------------------------------------------------------------------------
# FactStore — deterministic ordering
# ---------------------------------------------------------------------------


def test_query_facts_deterministic_order(store: FactStore):
    f1 = _make_fact("f1", created_at=datetime(2024, 1, 1, tzinfo=UTC))
    f2 = _make_fact("f2", created_at=datetime(2024, 1, 3, tzinfo=UTC))
    f3 = _make_fact("f3", created_at=datetime(2024, 1, 2, tzinfo=UTC))
    store.insert_facts([f3, f2, f1])

    ids = [f.id for f in store.query_facts()]
    assert ids == ["f1", "f3", "f2"]


def test_query_facts_deterministic_order_after_reopen(tmp_path: Path):
    db_path = tmp_path / "facts.db"
    f1 = _make_fact("f1", created_at=datetime(2024, 1, 1, tzinfo=UTC))
    f2 = _make_fact("f2", created_at=datetime(2024, 1, 3, tzinfo=UTC))
    f3 = _make_fact("f3", created_at=datetime(2024, 1, 2, tzinfo=UTC))

    s = FactStore(db_path)
    s.insert_facts([f3, f2, f1])
    s.close()

    s2 = FactStore(db_path)
    ids = [f.id for f in s2.query_facts()]
    s2.close()
    assert ids == ["f1", "f3", "f2"]


def test_query_facts_same_created_at_order_by_id(store: FactStore):
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    store.insert_facts([_make_fact("z-fact", ts), _make_fact("a-fact", ts)])
    ids = [f.id for f in store.query_facts()]
    assert ids == ["a-fact", "z-fact"]


# ---------------------------------------------------------------------------
# FactStore — entity operations
# ---------------------------------------------------------------------------


def test_store_insert_and_get_entity(store: FactStore):
    entity = Entity(
        type=EntityType.FILE,
        id="src/main.py",
        attributes={"language": "python", "loc": 200},
        repository_id="repo-1",
    )
    store.insert_entities([entity])
    ref = EntityRef(type=EntityType.FILE, id="src/main.py")
    retrieved = store.get_entity(ref)
    assert retrieved is not None
    assert retrieved.type == EntityType.FILE
    assert retrieved.attributes["language"] == "python"
    assert retrieved.repository_id == "repo-1"


def test_store_get_entity_missing(store: FactStore):
    ref = EntityRef(type=EntityType.FILE, id="nonexistent")
    assert store.get_entity(ref) is None


# ---------------------------------------------------------------------------
# FactStore — delete_run (test/debug cleanup)
# ---------------------------------------------------------------------------


def test_store_delete_run(store: FactStore):
    store.insert_facts([_make_fact("f1", run_id="run-A"), _make_fact("f2", run_id="run-B")])
    store.delete_run("run-A")
    results = list(store.query_facts())
    assert len(results) == 1
    assert results[0].run_id == "run-B"


# ---------------------------------------------------------------------------
# FactStore — schema version mismatch
# ---------------------------------------------------------------------------


def test_store_schema_version_mismatch(tmp_path: Path):
    from sqlalchemy import text

    db_path = tmp_path / "facts.db"
    s = FactStore(db_path)
    with s._engine.connect() as conn:
        conn.execute(text("UPDATE schema_meta SET value = '99.0' WHERE key = 'schema_version'"))
        conn.commit()
    s.close()

    with pytest.raises(SchemaVersionError):
        FactStore(db_path)


# ---------------------------------------------------------------------------
# Unknown / FactStatus values are representable
# ---------------------------------------------------------------------------


def test_fact_status_values_representable(store: FactStore):
    for status in FactStatus:
        fact = Fact(
            id=f"status-{status.name}",
            type="status_fact",
            subject=EntityRef(type=EntityType.SYSTEM, id="sys-1"),
            evidence=(_make_evidence(),),
            provenance="observed",
            confidence=0.0,
            source_analyzer="test",
            created_at=_TS,
            schema_version=SCHEMA_VERSION,
            run_id="r-status",
            value=status.value,
        )
        store.insert_facts([fact])

    results = list(store.query_facts(type="status_fact"))
    values = {r.value for r in results}
    assert values == {s.value for s in FactStatus}


# ---------------------------------------------------------------------------
# EntityType / RelationType coverage
# ---------------------------------------------------------------------------


def test_all_entity_types_valid():
    expected = {
        "System", "Environment", "Repository", "Project", "Directory",
        "File", "Symbol", "Commit", "Contributor", "Service",
        "Database", "Queue", "ExternalSource", "Tool", "Document",
    }
    assert {e.value for e in EntityType} == expected


def test_all_relation_types_valid():
    expected = {
        "depends_on", "calls", "imports", "inherits_from", "contains",
        "belongs_to", "changed_in", "authored_by", "deployed_by",
        "communicates_with", "documents", "tests",
    }
    assert {r.value for r in RelationType} == expected


# ---------------------------------------------------------------------------
# ExternalRef — no sensitive content stored
# ---------------------------------------------------------------------------


def test_external_ref_round_trip(store: FactStore):
    ev = Evidence(
        kind="external",
        ref=ExternalRef(
            source_type="github",
            identifier="anthropics/anthropic-sdk-python",
            url="https://github.com/anthropics/anthropic-sdk-python",
        ),
        source_analyzer="docs-crawler",
        retrieved_at=_TS,
    )
    fact = Fact(
        id="f-ext",
        type="external_dependency",
        subject=EntityRef(type=EntityType.REPOSITORY, id="repo-1"),
        evidence=(ev,),
        provenance="observed",
        confidence=1.0,
        source_analyzer="docs-crawler",
        created_at=_TS,
        schema_version=SCHEMA_VERSION,
        run_id="r1",
    )
    store.insert_facts([fact])
    results = list(store.query_facts())
    assert results[0].evidence[0].ref == ev.ref


# ---------------------------------------------------------------------------
# Snapshot test
# ---------------------------------------------------------------------------

_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "facts_snapshot.json"

_SNAPSHOT_FACT = Fact(
    id="snapshot-fact-1",
    type="file_exists",
    subject=EntityRef(type=EntityType.FILE, id="src/main.py"),
    predicate=None,
    object=None,
    value=None,
    evidence=(
        Evidence(
            kind="file",
            ref=FileRef(repository_id="repo-snapshot", path="src/main.py"),
            source_analyzer="fs-adapter",
            retrieved_at=datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC),
        ),
    ),
    provenance="observed",
    confidence=1.0,
    source_analyzer="fs-adapter",
    created_at=datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC),
    schema_version=SCHEMA_VERSION,
    run_id="snapshot-run",
)

_SNAPSHOT_ENTITY = Entity(
    type=EntityType.FILE,
    id="src/main.py",
    attributes={"language": "python", "loc": 150},
    repository_id="repo-snapshot",
)


class _DatetimeEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def test_snapshot_matches():
    """Serialized shape must exactly match the checked-in snapshot.

    Fail = the data model changed. Update the snapshot deliberately
    alongside the spec change — never auto-update it silently.
    """
    current = {
        "fact": dataclasses.asdict(_SNAPSHOT_FACT),
        "entity": dataclasses.asdict(_SNAPSHOT_ENTITY),
    }
    current_json = json.dumps(current, sort_keys=True, indent=2, cls=_DatetimeEncoder)

    if not _SNAPSHOT_PATH.exists():
        _SNAPSHOT_PATH.write_text(current_json)
        pytest.skip("Snapshot created — re-run to validate.")

    assert current_json == _SNAPSHOT_PATH.read_text(), (
        "Serialized shape differs from snapshot. "
        "Update tests/snapshots/facts_snapshot.json alongside the spec change."
    )
