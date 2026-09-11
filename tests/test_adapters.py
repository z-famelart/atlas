"""Tests for Feature 02 — Adapter framework."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from project_intel.adapters import (
    AdapterContext,
    AdapterManifest,
    AdapterStatus,
    assert_normalizes,
    run_adapters,
)
from project_intel.facts import (
    SCHEMA_VERSION,
    EntityRef,
    EntityType,
    Evidence,
    Fact,
    ToolOutputRef,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"

_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _make_context(tmp_path: Path) -> AdapterContext:
    return AdapterContext(
        target_path=tmp_path,
        run_id="run-test",
        repository_id="repo-test",
        timestamp=_TS,
    )


def _file_count_normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
    """Trivial example adapter: parses {"file_count": N} and emits one Fact."""
    data = json.loads(raw)
    analyzer = "file-counter@1.0.0"
    return [
        Fact(
            id=f"file-count-{ctx.run_id}",
            type="file_count",
            subject=EntityRef(type=EntityType.REPOSITORY, id=ctx.repository_id),
            evidence=(
                Evidence(
                    kind="tool_output",
                    ref=ToolOutputRef(source_analyzer=analyzer, raw_ref="file_count"),
                    source_analyzer=analyzer,
                    retrieved_at=ctx.timestamp,
                ),
            ),
            provenance="observed",
            confidence=1.0,
            source_analyzer=analyzer,
            created_at=ctx.timestamp,
            schema_version=SCHEMA_VERSION,
            run_id=ctx.run_id,
            value=data["file_count"],
        )
    ]


def _make_file_counter(
    min_version: str | None = None,
    max_version: str | None = None,
) -> AdapterManifest:
    return AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="discovery",
        normalize=_file_count_normalize,
        command=lambda ctx: (FIXTURES / "file_count.json").read_text(),
        min_version=min_version,
        max_version=max_version,
    )


# ---------------------------------------------------------------------------
# AdapterManifest — source_analyzer_id
# ---------------------------------------------------------------------------


def test_source_analyzer_id():
    m = _make_file_counter()
    assert m.source_analyzer_id == "file-counter@1.0.0"


# ---------------------------------------------------------------------------
# Presence check — CLI adapter with missing binary
# ---------------------------------------------------------------------------


def test_missing_binary_returns_skipped(tmp_path: Path):
    manifest = AdapterManifest(
        name="ghost-tool",
        version="1.0.0",
        category="test",
        normalize=lambda raw, ctx: [],
        command=["__nonexistent_binary_xyz__"],
        install_hint="brew install ghost-tool",
    )
    ctx = _make_context(tmp_path)
    results = run_adapters([manifest], ctx)

    assert len(results) == 1
    r = results[0]
    assert r.status == AdapterStatus.SKIPPED_TOOL_NOT_FOUND
    assert r.facts == ()
    assert r.error is not None
    assert "brew install ghost-tool" in r.error


# ---------------------------------------------------------------------------
# Version check — out-of-range → skipped:version_mismatch
# ---------------------------------------------------------------------------


def test_version_too_old_returns_skipped(tmp_path: Path):
    ctx = _make_context(tmp_path)
    manifest = AdapterManifest(
        name="versioned-tool",
        version="1.0.0",
        category="test",
        normalize=lambda raw, ctx: [],
        command=["python3"],  # python3 is always present
        min_version="999.0.0",  # impossibly high minimum
    )
    results = run_adapters([manifest], ctx)

    assert len(results) == 1
    assert results[0].status == AdapterStatus.SKIPPED_VERSION_MISMATCH


def test_version_too_new_returns_skipped(tmp_path: Path):
    ctx = _make_context(tmp_path)
    manifest = AdapterManifest(
        name="versioned-tool",
        version="1.0.0",
        category="test",
        normalize=lambda raw, ctx: [],
        command=["python3"],
        max_version="0.0.1",  # impossibly low maximum
    )
    results = run_adapters([manifest], ctx)

    assert len(results) == 1
    assert results[0].status == AdapterStatus.SKIPPED_VERSION_MISMATCH


def test_version_in_range_proceeds(tmp_path: Path):
    """A version constraint that matches does not block execution."""
    ctx = _make_context(tmp_path)
    manifest = AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="test",
        normalize=_file_count_normalize,
        command=["python3"],  # present; will succeed presence check
        min_version="1.0.0",  # python3 is definitely >= 1.0
        max_version="999.0.0",
    )
    # We patch _detect_version so the test doesn't depend on the installed python3 version format.
    with (
        patch("project_intel.adapters.runner._detect_version", return_value="3.12.0"),
        patch(
            "project_intel.adapters.runner._invoke",
            return_value='{"file_count": 5, "directory_count": 1}',
        ),
    ):
        results = run_adapters([manifest], ctx)

    assert results[0].status == AdapterStatus.OK


# ---------------------------------------------------------------------------
# Failure isolation — one adapter crashing must not abort siblings
# ---------------------------------------------------------------------------


def _crashing_normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
    raise RuntimeError("boom")


def test_failing_adapter_does_not_abort_siblings(tmp_path: Path):
    ctx = _make_context(tmp_path)
    crashing = AdapterManifest(
        name="crasher",
        version="1.0.0",
        category="test",
        normalize=_crashing_normalize,
        command=lambda _: "{}",
    )
    healthy = _make_file_counter()

    results = run_adapters([crashing, healthy], ctx)
    by_name = {r.adapter_name: r for r in results}

    assert by_name["crasher"].status == AdapterStatus.FAILED
    assert by_name["crasher"].error == "boom"
    assert by_name["crasher"].facts == ()
    assert by_name["healthy" if "healthy" in by_name else "file-counter"].status == AdapterStatus.OK


def test_failing_adapter_status_and_siblings_ok(tmp_path: Path):
    """Three adapters: one crashes, two succeed — all three results are returned."""
    ctx = _make_context(tmp_path)
    adapters = [
        _make_file_counter(),
        AdapterManifest(
            name="crasher",
            version="1.0.0",
            category="test",
            normalize=_crashing_normalize,
            command=lambda _: "{}",
        ),
        AdapterManifest(
            name="file-counter-2",
            version="1.0.0",
            category="discovery",
            normalize=_file_count_normalize,
            command=lambda ctx: (FIXTURES / "file_count.json").read_text(),
        ),
    ]
    results = run_adapters(adapters, ctx)
    assert len(results) == 3

    statuses = {r.adapter_name: r.status for r in results}
    assert statuses["crasher"] == AdapterStatus.FAILED
    assert statuses["file-counter"] == AdapterStatus.OK
    assert statuses["file-counter-2"] == AdapterStatus.OK


# ---------------------------------------------------------------------------
# Successful run — source_analyzer stamp, provenance, evidence
# ---------------------------------------------------------------------------


def test_successful_adapter_facts_carry_correct_stamp(tmp_path: Path):
    ctx = _make_context(tmp_path)
    results = run_adapters([_make_file_counter()], ctx)

    assert results[0].status == AdapterStatus.OK
    facts = results[0].facts
    assert len(facts) == 1
    fact = facts[0]

    assert fact.source_analyzer == "file-counter@1.0.0"
    assert fact.provenance == "observed"
    assert len(fact.evidence) > 0
    assert fact.run_id == ctx.run_id


def test_successful_adapter_returns_all_facts(tmp_path: Path):
    ctx = _make_context(tmp_path)
    results = run_adapters([_make_file_counter()], ctx)
    assert results[0].facts[0].value == 42


# ---------------------------------------------------------------------------
# Pure-Python adapter (callable command)
# ---------------------------------------------------------------------------


def test_pure_python_adapter(tmp_path: Path):
    """A callable command (no binary) always passes presence check."""
    ctx = _make_context(tmp_path)
    manifest = AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="discovery",
        normalize=_file_count_normalize,
        command=lambda _: '{"file_count": 7, "directory_count": 2}',
    )
    results = run_adapters([manifest], ctx)
    assert results[0].status == AdapterStatus.OK
    assert results[0].facts[0].value == 7


def test_pure_python_adapter_no_version_check(tmp_path: Path):
    """Version constraints are silently ignored for pure-Python adapters."""
    ctx = _make_context(tmp_path)
    manifest = AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="discovery",
        normalize=_file_count_normalize,
        command=lambda _: '{"file_count": 1, "directory_count": 0}',
        min_version="999.0.0",  # would block a CLI adapter; ignored here
    )
    results = run_adapters([manifest], ctx)
    assert results[0].status == AdapterStatus.OK


# ---------------------------------------------------------------------------
# run_adapters returns one result per adapter
# ---------------------------------------------------------------------------


def test_run_adapters_result_count(tmp_path: Path):
    ctx = _make_context(tmp_path)
    manifests = [_make_file_counter(), _make_file_counter()]
    manifests[1] = AdapterManifest(
        name="file-counter-b",
        version="1.0.0",
        category="discovery",
        normalize=_file_count_normalize,
        command=lambda ctx: (FIXTURES / "file_count.json").read_text(),
    )
    results = run_adapters(manifests, ctx)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Contract test helper — assert_normalizes
# ---------------------------------------------------------------------------


def test_assert_normalizes_passes_for_valid_adapter(tmp_path: Path):
    ctx = _make_context(tmp_path)
    facts = assert_normalizes(_make_file_counter(), FIXTURES / "file_count.json", ctx)
    assert len(facts) == 1
    assert facts[0].type == "file_count"
    assert facts[0].value == 42


def test_assert_normalizes_checks_source_analyzer(tmp_path: Path):
    """assert_normalizes must fail if normalize() returns wrong source_analyzer."""
    ctx = _make_context(tmp_path)

    def bad_normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
        data = json.loads(raw)
        return [
            Fact(
                id="bad",
                type="file_count",
                subject=EntityRef(type=EntityType.REPOSITORY, id=ctx.repository_id),
                evidence=(
                    Evidence(
                        kind="tool_output",
                        ref=ToolOutputRef(source_analyzer="wrong@0.0.0", raw_ref="x"),
                        source_analyzer="wrong@0.0.0",
                        retrieved_at=ctx.timestamp,
                    ),
                ),
                provenance="observed",
                confidence=1.0,
                source_analyzer="wrong@0.0.0",  # does NOT match manifest
                created_at=ctx.timestamp,
                schema_version=SCHEMA_VERSION,
                run_id=ctx.run_id,
                value=data["file_count"],
            )
        ]

    manifest = AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="discovery",
        normalize=bad_normalize,
        command=lambda _: "",
    )
    with pytest.raises(AssertionError, match="source_analyzer"):
        assert_normalizes(manifest, FIXTURES / "file_count.json", ctx)


def test_assert_normalizes_checks_evidence(tmp_path: Path):
    ctx = _make_context(tmp_path)

    def no_evidence_normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
        return [
            Fact(
                id="no-ev",
                type="file_count",
                subject=EntityRef(type=EntityType.REPOSITORY, id=ctx.repository_id),
                evidence=(),  # empty — violates contract
                provenance="observed",
                confidence=1.0,
                source_analyzer="file-counter@1.0.0",
                created_at=ctx.timestamp,
                schema_version=SCHEMA_VERSION,
                run_id=ctx.run_id,
                value=0,
            )
        ]

    manifest = AdapterManifest(
        name="file-counter",
        version="1.0.0",
        category="discovery",
        normalize=no_evidence_normalize,
        command=lambda _: "",
    )
    with pytest.raises(AssertionError, match="evidence"):
        assert_normalizes(manifest, FIXTURES / "file_count.json", ctx)


def test_assert_normalizes_with_expected_facts(tmp_path: Path):
    ctx = _make_context(tmp_path)
    m = _make_file_counter()
    expected = m.normalize((FIXTURES / "file_count.json").read_text(), ctx)
    # Calling with matching expected_facts must not raise.
    assert_normalizes(m, FIXTURES / "file_count.json", ctx, expected_facts=expected)


def test_assert_normalizes_expected_facts_mismatch(tmp_path: Path):
    ctx = _make_context(tmp_path)
    m = _make_file_counter()
    wrong_expected = []  # empty — won't match the one fact produced
    with pytest.raises(AssertionError):
        assert_normalizes(m, FIXTURES / "file_count.json", ctx, expected_facts=wrong_expected)
