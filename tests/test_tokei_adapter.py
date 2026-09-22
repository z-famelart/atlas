"""Tests for Feature 03 Part B — tokei language/LOC adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_intel.adapters import AdapterContext, assert_normalizes
from project_intel.discovery import TOKEI_MANIFEST

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "tokei_output.json"

_TS = datetime(2024, 1, 1, tzinfo=UTC)
_REPO_ROOT = Path("/repo")


def _ctx() -> AdapterContext:
    return AdapterContext(
        target_path=_REPO_ROOT,
        run_id="run-tokei-test",
        repository_id="repo-test",
        timestamp=_TS,
    )


def test_python_file_detected() -> None:
    facts = assert_normalizes(TOKEI_MANIFEST, FIXTURE, _ctx())
    py_facts = [f for f in facts if f.value and f.value.get("language") == "Python"]
    assert len(py_facts) == 2
    main = next(f for f in py_facts if "main.py" in f.subject.id)
    assert main.value["loc"] == 120
    assert main.value["total_lines"] == 133


def test_all_detected_languages_emitted() -> None:
    """Discovery reports every language tokei finds, not just the code-graph MVP
    scope (Q193) — code_graph.metrics.compute_coverage_gap needs the full picture
    to detect what's outside that scope instead of it being silently dropped here."""
    facts = assert_normalizes(TOKEI_MANIFEST, FIXTURE, _ctx())
    languages = {f.value["language"] for f in facts if f.value}
    assert "C++" in languages


def test_absolute_path_converted_to_relative() -> None:
    facts = assert_normalizes(TOKEI_MANIFEST, FIXTURE, _ctx())
    for fact in facts:
        assert not Path(fact.subject.id).is_absolute(), (
            f"Expected relative path, got: {fact.subject.id!r}"
        )
    paths = {f.subject.id for f in facts}
    assert "src/main.py" in paths
    assert "src/app.ts" in paths


def test_source_analyzer_version() -> None:
    facts = assert_normalizes(TOKEI_MANIFEST, FIXTURE, _ctx())
    assert all(f.source_analyzer == "tokei@1.0" for f in facts)


def test_provenance_and_confidence() -> None:
    facts = assert_normalizes(TOKEI_MANIFEST, FIXTURE, _ctx())
    assert facts, "expected at least one fact"
    for fact in facts:
        assert fact.provenance == "observed"
        assert fact.confidence == 1.0
