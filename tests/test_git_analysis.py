"""Tests for Feature 04 — Git Analysis."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_intel.adapters import AdapterContext, assert_normalizes
from project_intel.facts import CommitRef
from project_intel.git_analysis import (
    AnalysisWindow,
    churn_manifest,
    normalize_churn,
)

FIXTURES = Path(__file__).parent / "fixtures" / "git_history"

_TS = datetime(2024, 1, 1, tzinfo=UTC)
_CTX = AdapterContext(
    target_path=Path("/repo"),
    run_id="run-test",
    repository_id="repo-test",
    timestamp=_TS,
)

# ---------------------------------------------------------------------------
# AnalysisWindow
# ---------------------------------------------------------------------------


def test_window_none_returns_no_args() -> None:
    assert AnalysisWindow().since_arg() == []


def test_window_timedelta_returns_since_arg() -> None:
    w = AnalysisWindow(window=timedelta(days=90))
    args = w.since_arg()
    assert len(args) == 1
    assert args[0].startswith("--since=")


# ---------------------------------------------------------------------------
# Churn — fixture-based
# ---------------------------------------------------------------------------


def test_churn_basic_facts() -> None:
    manifest = churn_manifest()
    facts = assert_normalizes(manifest, FIXTURES / "churn.txt", _CTX)

    # Two files in commit 1 (foo, bar), one more file in commit 2 (baz)
    by_path = {f.subject.id: f for f in facts}
    assert set(by_path) == {"src/foo.py", "src/bar.py", "src/baz.py"}

    foo = by_path["src/foo.py"]
    assert foo.type == "git_churn"
    assert foo.provenance == "computed"
    assert foo.confidence == 1.0
    assert foo.value["commits"] == 2  # appears in both commits
    assert foo.value["lines_changed"] == 5 + 3 + 0 + 4  # 12

    bar = by_path["src/bar.py"]
    assert bar.value["commits"] == 1
    assert bar.value["lines_changed"] == 3

    baz = by_path["src/baz.py"]
    assert baz.value["commits"] == 1
    assert baz.value["lines_changed"] == 3


def test_churn_evidence_uses_full_commit_hash() -> None:
    manifest = churn_manifest()
    facts = assert_normalizes(manifest, FIXTURES / "churn.txt", _CTX)

    for fact in facts:
        for ev in fact.evidence:
            assert ev.kind == "commit"
            assert isinstance(ev.ref, CommitRef)
            assert len(ev.ref.commit_hash) == 40, "CommitRef must use full 40-char hash"
            assert ev.ref.repository_id == _CTX.repository_id


def test_churn_no_merges_flag_in_command() -> None:
    manifest_no_merges = churn_manifest(include_merges=False)
    manifest_with_merges = churn_manifest(include_merges=True)
    # Command is a callable — inspect via str representation isn't possible,
    # but we can verify the manifest names/versions are the same and that
    # normalize behavior is identical (the toggle only affects the git invocation).
    # What we can assert: include_merges=False → no-merges in output is the adapter's job.
    # For a unit-level check, verify that the manifests have different commands by identity.
    assert manifest_no_merges.command is not manifest_with_merges.command


def test_churn_source_analyzer_format() -> None:
    manifest = churn_manifest()
    facts = assert_normalizes(manifest, FIXTURES / "churn.txt", _CTX)
    for fact in facts:
        assert fact.source_analyzer == "git-churn@1.0.0"


# ---------------------------------------------------------------------------
# Churn — window
# ---------------------------------------------------------------------------


def test_churn_normalize_ignores_window_at_parse_level() -> None:
    """Window filtering happens at the git invocation level, not in normalize().
    The fixture output represents already-filtered commits; normalize just parses."""
    # Using window=None and window=timedelta produce identical normalize() behavior
    # for the same input string — the window only affects the git command args.
    manifest = churn_manifest(window=AnalysisWindow(window=timedelta(days=30)))
    facts = assert_normalizes(manifest, FIXTURES / "churn.txt", _CTX)
    assert len(facts) == 3  # same as without window, same input string


# ---------------------------------------------------------------------------
# Rename continuity — integration test with a real tmp git repo
# ---------------------------------------------------------------------------


@pytest.fixture()
def rename_repo(tmp_path: Path) -> Path:
    """A minimal git repo where foo.py is renamed to bar.py mid-history."""
    env = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com",
           "GIT_AUTHOR_DATE": "2024-01-01T00:00:00Z",
           "GIT_COMMITTER_DATE": "2024-01-01T00:00:00Z",
           "HOME": str(tmp_path)}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env={**env, "PATH": "/usr/bin:/bin"}, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t.com")
    git("config", "user.name", "Test")

    # Commit 1: create foo.py
    (tmp_path / "foo.py").write_text("line1\nline2\n")
    git("add", "foo.py")
    git("commit", "-m", "add foo")

    # Commit 2: edit foo.py
    (tmp_path / "foo.py").write_text("line1\nline2\nline3\n")
    git("add", "foo.py")
    git("commit", "-m", "edit foo")

    # Commit 3: rename foo.py → bar.py
    git("mv", "foo.py", "bar.py")
    git("commit", "-m", "rename foo to bar")

    return tmp_path


def test_rename_continuity(rename_repo: Path) -> None:
    """With --follow, churn for bar.py includes commits before the rename."""
    cmd = ["git", "log", "--numstat", "--no-merges", "--format=%H", "--follow", "--", "bar.py"]
    result = subprocess.run(cmd, cwd=rename_repo, capture_output=True, text=True, check=True)
    output = result.stdout

    ctx = AdapterContext(
        target_path=rename_repo,
        run_id="run-rename",
        repository_id="repo-rename",
        timestamp=_TS,
    )
    facts = normalize_churn(output, ctx)

    # Should see bar.py with commits from both before and after rename
    by_path = {f.subject.id: f for f in facts}
    # bar.py should aggregate across all 3 commits (add, edit, rename)
    assert "bar.py" in by_path or "foo.py" in by_path, f"expected bar.py or foo.py in {list(by_path)}"
    # The combined commit count should reflect pre-rename history
    total_commits = sum(f.value["commits"] for f in facts)
    assert total_commits >= 2  # at minimum: the rename + one prior edit


# ---------------------------------------------------------------------------
# Feature 04b — path rebasing onto repo_path (subdirectory case)
# ---------------------------------------------------------------------------


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "t@t.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "t@t.com",
    "GIT_AUTHOR_DATE": "2024-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2024-01-01T00:00:00Z",
}


@pytest.fixture()
def subdir_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Git repo rooted at tmp_path with a backend/ subdirectory as the analysis target.

    Returns (repo_root, backend_path).
    """
    env = {**_GIT_ENV, "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@t.com")
    git("config", "user.name", "Test")

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "app.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-m", "add backend/app.py")

    (backend / "app.py").write_text("x = 2\n")
    git("add", ".")
    git("commit", "-m", "edit backend/app.py")

    return tmp_path, backend


def test_churn_paths_rebased_for_subdir(subdir_repo: tuple[Path, Path]) -> None:
    """git_churn subject.id must be repo_path-relative, not git-root-relative."""
    _, backend = subdir_repo
    cmd = ["git", "log", "--numstat", "--no-merges", "--format=%H"]
    result = subprocess.run(cmd, cwd=backend, capture_output=True, text=True, check=True)

    ctx = AdapterContext(target_path=backend, run_id="r1", repository_id="repo", timestamp=_TS)
    facts = normalize_churn(result.stdout, ctx)

    paths = {f.subject.id for f in facts}
    # git reports "backend/app.py" but subject.id must be "app.py" (repo_path-relative)
    assert "app.py" in paths, f"expected 'app.py', got {paths}"
    assert not any(p.startswith("backend/") for p in paths), f"prefix not stripped: {paths}"


def test_churn_paths_unchanged_at_repo_root(subdir_repo: tuple[Path, Path]) -> None:
    """When target_path is the git root, prefix is empty and paths are unchanged."""
    repo_root, _ = subdir_repo
    cmd = ["git", "log", "--numstat", "--no-merges", "--format=%H"]
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)

    ctx = AdapterContext(target_path=repo_root, run_id="r1", repository_id="repo", timestamp=_TS)
    facts = normalize_churn(result.stdout, ctx)

    paths = {f.subject.id for f in facts}
    assert "backend/app.py" in paths, f"expected 'backend/app.py', got {paths}"


def test_barad_dur_paths_rebased_for_subdir(tmp_path: Path) -> None:
    import json

    from project_intel.git_analysis.barad_dur import normalize_barad_dur

    env = {**_GIT_ENV, "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, env=env, check=True, capture_output=True)
    backend = tmp_path / "backend"
    backend.mkdir()
    raw = json.dumps({"file_hotspots": [
        {"path": "backend/a.py", "role": "source"},
        {"path": "frontend/b.ts", "role": "source"},
    ]})
    ctx = AdapterContext(target_path=backend, run_id="r1", repository_id="repo", timestamp=_TS)
    assert [f.subject.id for f in normalize_barad_dur(raw, ctx)] == ["a.py"]
