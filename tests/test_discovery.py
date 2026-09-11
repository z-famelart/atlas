"""Tests for Feature 03 Part A: Discovery Framework."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_intel.adapters.manifest import AdapterContext
from project_intel.adapters.testing import assert_normalizes
from project_intel.discovery import (
    ScopeConfig,
    match_signatures,
    run_discovery,
    tag_documents,
    walk_files,
)
from project_intel.discovery.git_detector import GIT_MANIFEST

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_REPO = FIXTURES / "sample_repo"
GIT_FIXTURE = FIXTURES / "git_detector" / "rev_parse_output.txt"

_CTX = AdapterContext(
    target_path=SAMPLE_REPO,
    run_id="test-run-01",
    repository_id="repo-test",
    timestamp=datetime(2024, 1, 1, tzinfo=UTC),
)


# ── Signature matching ────────────────────────────────────────────────────────


def test_signature_detects_maven():
    rel_paths = walk_files(SAMPLE_REPO, ScopeConfig())
    sigs = match_signatures(SAMPLE_REPO, rel_paths)
    names = {s["name"] for s in sigs}
    assert "maven" in names


def test_signature_detects_docker():
    rel_paths = walk_files(SAMPLE_REPO, ScopeConfig())
    sigs = match_signatures(SAMPLE_REPO, rel_paths)
    names = {s["name"] for s in sigs}
    assert "docker" in names


def test_signature_detects_github_actions():
    rel_paths = walk_files(SAMPLE_REPO, ScopeConfig())
    sigs = match_signatures(SAMPLE_REPO, rel_paths)
    names = {s["name"] for s in sigs}
    assert "github-actions" in names


def test_signature_detects_kubernetes():
    rel_paths = walk_files(SAMPLE_REPO, ScopeConfig())
    sigs = match_signatures(SAMPLE_REPO, rel_paths)
    names = {s["name"] for s in sigs}
    assert "kubernetes" in names


# ── Scope exclusion ───────────────────────────────────────────────────────────


def test_scope_exclude_prevents_file_in_output():
    scope = ScopeConfig(exclude_globs=("pom.xml",))
    rel_paths = walk_files(SAMPLE_REPO, scope)
    assert "pom.xml" not in rel_paths


def test_scope_exclude_absent_from_unrecognized():
    """An excluded file must not appear in discovery output at all."""
    scope = ScopeConfig(exclude_globs=("pom.xml",))
    result = run_discovery(
        root=SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-02",
        scope=scope,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    all_paths = {
        fact.subject.id
        for fact in result.facts
        if fact.type == "unrecognized_artifact"
    } | {
        e.ref.path
        for fact in result.facts
        for e in fact.evidence
    }
    assert "pom.xml" not in all_paths


def test_scope_max_depth_limits_walk():
    # depth=0 means only files directly in root (no subdirectories)
    scope = ScopeConfig(max_depth=0)
    rel_paths = walk_files(SAMPLE_REPO, scope)
    for p in rel_paths:
        assert "/" not in p, f"Expected root-only paths, got {p!r}"


# ── Unrecognized artifacts ────────────────────────────────────────────────────


def test_unrecognized_artifact_emitted():
    result = run_discovery(
        root=SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-03",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    unrecognized = [f for f in result.facts if f.type == "unrecognized_artifact"]
    assert len(unrecognized) >= 1, "At least one unrecognized_artifact fact must be emitted"
    # some_binary.bin should be unrecognized
    paths = {f.subject.id for f in unrecognized}
    assert "some_binary.bin" in paths


# ── Git detector contract test ────────────────────────────────────────────────


def test_git_detector_normalize_contract():
    """Uses assert_normalizes() with fixture output — no live git required."""
    facts = assert_normalizes(GIT_MANIFEST, GIT_FIXTURE, _CTX)
    assert len(facts) == 1
    fact = facts[0]
    assert fact.type == "git_repository_detected"
    assert fact.value == {"git_dir": ".git"}


def test_git_detector_empty_output_returns_no_facts():
    facts = GIT_MANIFEST.normalize("", _CTX)
    assert facts == []


# ── Doc enumerator ────────────────────────────────────────────────────────────


def test_doc_enumerator_tags_readme():
    tagged = tag_documents(["README.md", "pom.xml", "some_binary.bin"])
    roles = {d["path"]: d["role"] for d in tagged}
    assert roles.get("README.md") == "readme"
    assert "some_binary.bin" not in roles


def test_doc_enumerator_tags_config():
    tagged = tag_documents(["Dockerfile", "chart.yaml"])
    paths = {d["path"] for d in tagged}
    assert "chart.yaml" in paths


# ── Full pipeline smoke ───────────────────────────────────────────────────────


def test_run_discovery_returns_technology_facts():
    result = run_discovery(
        root=SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-04",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    tech_facts = [f for f in result.facts if f.type == "technology_detected"]
    tech_names = {f.value["name"] for f in tech_facts}
    assert "maven" in tech_names
    assert "docker" in tech_names


def test_run_discovery_all_facts_have_evidence():
    result = run_discovery(
        root=SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-05",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    for fact in result.facts:
        assert len(fact.evidence) > 0, f"Fact {fact.id!r} ({fact.type}) has no evidence"


def test_run_discovery_source_analyzer_stamped():
    result = run_discovery(
        root=SAMPLE_REPO,
        repository_id="repo-test",
        run_id="test-run-06",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    for fact in result.facts:
        assert "@" in fact.source_analyzer, (
            f"Fact {fact.id!r} source_analyzer {fact.source_analyzer!r} missing version"
        )
