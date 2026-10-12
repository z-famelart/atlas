"""Tests for Feature 06 Part A — hotspot scoring engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.hotspots.scorer import _percentile_rank, compute_hotspots
from project_intel.hotspots.weights import HotspotWeights

_RUN_ID = "test-run"
_REPO_ID = "test-repo"


def _now() -> datetime:
    return datetime.now(UTC)


def _file_fact(
    store: FactStore,
    fact_type: str,
    file_id: str,
    value: dict,
    run_id: str = _RUN_ID,
) -> None:
    ev = Evidence(
        kind="file",
        ref=FileRef(repository_id=_REPO_ID, path=file_id),
        source_analyzer="test",
        retrieved_at=_now(),
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
            created_at=_now(),
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            evidence=(ev,),
        )
    ])


@pytest.fixture()
def store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


# ---------------------------------------------------------------------------
# Normalization unit tests
# ---------------------------------------------------------------------------


def test_percentile_rank_single():
    assert _percentile_rank([42.0]) == [0.5]


def test_percentile_rank_two():
    ranks = _percentile_rank([1.0, 2.0])
    assert ranks[0] < ranks[1]
    assert ranks[0] == pytest.approx(0.0)
    assert ranks[1] == pytest.approx(1.0)


def test_percentile_rank_ties():
    ranks = _percentile_rank([5.0, 5.0, 5.0])
    assert all(r == pytest.approx(0.5) for r in ranks)


def test_percentile_rank_monotone():
    vals = [10.0, 30.0, 20.0, 5.0]
    ranks = _percentile_rank(vals)
    # rank of 30 > rank of 20 > rank of 10 > rank of 5
    assert ranks[1] > ranks[2] > ranks[0] > ranks[3]


# ---------------------------------------------------------------------------
# Scoring engine tests
# ---------------------------------------------------------------------------


def test_no_facts_returns_empty(store: FactStore):
    assert compute_hotspots(store, _REPO_ID, _RUN_ID) == []


def test_three_component_score(store: FactStore):
    """File with size + centrality + churn → valid 3/4 score."""
    _file_fact(store, "language_detected", "src/a.py", {"loc": 100, "language": "Python"})
    _file_fact(store, "centrality", "src/a.py", {"in_degree": 0.8, "out_degree": 0.2})
    _file_fact(store, "git_churn", "src/a.py", {"commits": 20, "lines_changed": 500})

    facts = compute_hotspots(store, _REPO_ID, _RUN_ID)
    score_fact = next(f for f in facts if f.type == "hotspot_score")

    assert score_fact.value["components_available"] == "3/4"
    assert score_fact.value["components"]["complexity"]["present"] is False
    assert score_fact.value["components"]["size"]["present"] is True
    assert 0.0 <= score_fact.value["combined"] <= 1.0


def test_missing_component_not_zero(store: FactStore):
    """A missing complexity component must not be treated as zero."""
    # Two files: a.py has all three (no complexity); b.py has only churn
    _file_fact(store, "language_detected", "src/a.py", {"loc": 50, "language": "Python"})
    _file_fact(store, "centrality", "src/a.py", {"in_degree": 0.5, "out_degree": 0.1})
    _file_fact(store, "git_churn", "src/a.py", {"commits": 5, "lines_changed": 100})

    _file_fact(store, "git_churn", "src/b.py", {"commits": 1, "lines_changed": 10})

    facts = compute_hotspots(store, _REPO_ID, _RUN_ID)
    by_file = {f.subject.id: f for f in facts if f.type == "hotspot_score"}

    assert by_file["src/a.py"].value["components_available"] == "3/4"
    assert by_file["src/b.py"].value["components_available"] == "1/4"
    # b.py has the lowest churn → rank 0.0; verify it's not treated as zero-component
    assert by_file["src/b.py"].value["components"]["complexity"]["present"] is False
    assert by_file["src/b.py"].value["components"]["churn"]["present"] is True
    # combined is derived only from churn (1 component) — value is rank not raw count
    assert 0.0 <= by_file["src/b.py"].value["combined"] <= 1.0


def test_huge_file_does_not_dominate(store: FactStore):
    """Log-normalization means a single huge file doesn't get score=1.0 purely by LOC."""
    _file_fact(store, "language_detected", "big.py", {"loc": 999_999, "language": "Python"})
    _file_fact(store, "language_detected", "small.py", {"loc": 10, "language": "Python"})
    _file_fact(store, "git_churn", "big.py", {"commits": 1, "lines_changed": 5})
    _file_fact(store, "git_churn", "small.py", {"commits": 50, "lines_changed": 1000})

    facts = compute_hotspots(store, _REPO_ID, _RUN_ID)
    by_file = {f.subject.id: f for f in facts if f.type == "hotspot_score"}

    # small.py has much higher churn; despite big.py's huge LOC, small.py should score higher
    assert by_file["small.py"].value["combined"] > by_file["big.py"].value["combined"]


def test_sub_score_facts_emitted(store: FactStore):
    """Each present component must produce an independent sub-score fact."""
    _file_fact(store, "language_detected", "x.py", {"loc": 20, "language": "Python"})
    _file_fact(store, "git_churn", "x.py", {"commits": 3, "lines_changed": 30})

    facts = compute_hotspots(store, _REPO_ID, _RUN_ID)
    types = {f.type for f in facts}
    assert "hotspot_size_score" in types
    assert "hotspot_churn_score" in types
    assert "hotspot_complexity_score" not in types  # not present
    assert "hotspot_centrality_score" not in types  # not present


def test_custom_weights(store: FactStore):
    """Higher churn weight should push churn-heavy file to top."""
    _file_fact(store, "language_detected", "a.py", {"loc": 1000, "language": "Python"})
    _file_fact(store, "language_detected", "b.py", {"loc": 10, "language": "Python"})
    _file_fact(store, "git_churn", "a.py", {"commits": 1, "lines_changed": 5})
    _file_fact(store, "git_churn", "b.py", {"commits": 100, "lines_changed": 5000})

    # With default weights: a.py wins on size, b.py wins on churn
    # With churn weight=10 and size weight=0: b.py should win
    high_churn_weights = HotspotWeights(complexity=0, size=0, centrality=0, churn=10)
    facts = compute_hotspots(store, _REPO_ID, _RUN_ID, weights=high_churn_weights)
    by_file = {f.subject.id: f for f in facts if f.type == "hotspot_score"}
    assert by_file["b.py"].value["combined"] > by_file["a.py"].value["combined"]


def test_all_zero_weights_still_produces_score(store: FactStore):
    """Edge case: all weights zero → combined = nan-safe fallback (0.0) or a score."""
    # This tests that we don't divide by zero
    _file_fact(store, "git_churn", "x.py", {"commits": 5, "lines_changed": 10})
    weights = HotspotWeights(complexity=0, size=0, centrality=0, churn=0)
    # Should not raise; combined = 0.0 (0/0 case handled)
    try:
        compute_hotspots(store, _REPO_ID, _RUN_ID, weights=weights)
    except ZeroDivisionError:
        pytest.fail("ZeroDivisionError when all weights are zero")


def test_barad_dur_roles_filter_hotspots() -> None:
    store = FactStore(":memory:")
    for path, role in (("a.vue", "other"), ("pyproject.toml", "config")):
        _file_fact(store, "file_role", path, {"role": role})
        _file_fact(store, "git_churn", path, {"commits": 3, "lines_changed": 3})
    _file_fact(store, "git_churn", "unknown.lock", {"commits": 3, "lines_changed": 3})
    scored = {f.subject.id for f in compute_hotspots(store, _REPO_ID, _RUN_ID) if f.type == "hotspot_score"}
    assert scored == {"a.vue"}
