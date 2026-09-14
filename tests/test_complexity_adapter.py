"""Tests for Feature 06 Part B — lizard complexity adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.adapters import AdapterContext, assert_normalizes
from project_intel.facts import EntityType
from project_intel.hotspots.complexity_adapter import lizard_manifest

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
def facts(tmp_path: Path) -> list:
    return assert_normalizes(
        lizard_manifest(),
        FIXTURES / "lizard_output.json",
        _ctx(tmp_path),
    )


# ---------------------------------------------------------------------------
# Contract invariants via assert_normalizes
# ---------------------------------------------------------------------------


def test_contract_invariants(facts):
    assert len(facts) > 0


# ---------------------------------------------------------------------------
# Normalize behaviour
# ---------------------------------------------------------------------------


def test_fact_type(facts):
    assert all(f.type == "complexity" for f in facts)


def test_subject_is_file(facts):
    assert all(f.subject.type == EntityType.FILE for f in facts)


def test_value_has_score(facts):
    assert all("score" in f.value for f in facts)


def test_score_values(facts):
    scores = {f.subject.id: f.value["score"] for f in facts}
    assert scores["src/foo.py"] == pytest.approx(3.5)
    assert scores["src/bar.py"] == pytest.approx(1.0)


def test_empty_file_excluded(facts):
    """Files with no functions and avg_cc == 0 must not produce a fact."""
    ids = {f.subject.id for f in facts}
    assert "src/empty.py" not in ids


def test_provenance_observed(facts):
    assert all(f.provenance == "observed" for f in facts)


def test_source_analyzer(facts):
    assert all(f.source_analyzer == "lizard@1.0" for f in facts)


# ---------------------------------------------------------------------------
# Manifest shape
# ---------------------------------------------------------------------------


def test_manifest_category():
    assert lizard_manifest().category == "complexity"


def test_manifest_command_is_callable():
    assert callable(lizard_manifest().command)


# ---------------------------------------------------------------------------
# Integration test: runs lizard library on a real tiny Python file
# ---------------------------------------------------------------------------


def test_integration_real_lizard(tmp_path: Path):
    """Run the full command+normalize pipeline against a real Python file."""
    lizard = pytest.importorskip("lizard")  # noqa: F841

    (tmp_path / "main.py").write_text(
        "def a(x):\n    if x > 0:\n        return x\n    return -x\n\n"
        "def b():\n    return 1\n"
    )

    manifest = lizard_manifest()
    raw = manifest.command(_ctx(tmp_path))
    import json
    data = json.loads(raw)
    assert len(data) == 1
    assert data[0]["filename"] == "main.py"

    facts = manifest.normalize(raw, _ctx(tmp_path))
    assert len(facts) == 1
    assert facts[0].type == "complexity"
    assert facts[0].subject.id == "main.py"
    # main.py has 2 functions: a (cc=2, if branch), b (cc=1) → average ≈ 1.5
    assert facts[0].value["score"] > 1.0


def test_integration_4_of_4_components(tmp_path: Path):
    """Complexity + size + centrality + churn facts → 4/4 components_available."""
    import uuid
    from datetime import UTC, datetime

    pytest.importorskip("lizard")

    from project_intel.facts import EntityRef, EntityType, Evidence, Fact
    from project_intel.facts.refs import FileRef
    from project_intel.facts.store import SCHEMA_VERSION, FactStore
    from project_intel.hotspots.scorer import compute_hotspots

    store = FactStore(tmp_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    repo_id = "repo-test"
    now = datetime.now(UTC)

    def _make(type_, file_, value):
        return Fact(
            id=str(uuid.uuid4()),
            type=type_,
            subject=EntityRef(EntityType.FILE, file_),
            value=value,
            provenance="observed",
            confidence=1.0,
            source_analyzer="test",
            evidence=(Evidence(kind="file", ref=FileRef(repository_id=repo_id, path=file_), source_analyzer="test", retrieved_at=now),),
            created_at=now,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
        )

    store.insert_facts([
        _make("complexity", "src/a.py", {"score": 3.0}),
        _make("language_detected", "src/a.py", {"loc": 100}),
        _make("centrality", "src/a.py", {"in_degree": 5}),
        _make("git_churn", "src/a.py", {"commits": 10}),
    ])

    hotspots = compute_hotspots(store, repo_id, run_id)
    store.close()

    score_facts = [f for f in hotspots if f.type == "hotspot_score"]
    assert len(score_facts) == 1
    val = score_facts[0].value
    assert val["components_available"] == "4/4"
    assert all(val["components"][c]["present"] for c in ("complexity", "size", "centrality", "churn"))
