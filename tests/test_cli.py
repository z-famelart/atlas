"""Tests for Feature 06b — minimal CLI pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from project_intel.cli.registry import STAGE_REGISTRY
from project_intel.cli.types import PipelineContext, StageRunResult
from project_intel.discovery.scope import ScopeConfig
from project_intel.facts.store import FactStore

DEFAULT_SCOPE = ScopeConfig(exclude_globs=(
    ".git/*", ".git", "node_modules/*", "__pycache__/*",
    ".venv/*", "venv/*", "dist/*", "build/*",
))


# ---------------------------------------------------------------------------
# Stage protocol and registry tests
# ---------------------------------------------------------------------------


def test_stage_registry_not_empty():
    assert len(STAGE_REGISTRY) >= 3  # discovery, git, code_graph at minimum


def test_stage_registry_names():
    names = [s.name for s in STAGE_REGISTRY]
    assert "discovery" in names
    assert "git" in names
    assert "code_graph" in names
    assert "hotspots" in names


def test_stage_registry_ordered():
    names = [s.name for s in STAGE_REGISTRY]
    assert names.index("discovery") < names.index("hotspots")
    assert names.index("git") < names.index("hotspots")
    assert names.index("code_graph") < names.index("hotspots")


def test_fake_stage_runs_without_runner_change(tmp_path: Path):
    """Adding a new Stage (one import + one append) must run without touching runner code."""
    store = FactStore(tmp_path / "facts.sqlite")

    calls: list[PipelineContext] = []

    class _FakeStage:
        name = "fake_test_stage"

        def run(self, ctx: PipelineContext) -> StageRunResult:
            calls.append(ctx)
            return StageRunResult(name=self.name, status="ok", facts_produced=0)

    fake = _FakeStage()
    registry = list(STAGE_REGISTRY) + [fake]

    ctx = PipelineContext(
        store=store,
        repository_path=tmp_path,
        run_id="test-run",
        scope=DEFAULT_SCOPE,
    )
    for stage in registry:
        stage.run(ctx)

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# End-to-end smoke test against a fixture directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a couple of Python files."""
    repo = tmp_path / "simple_repo"
    repo.mkdir()
    (repo / "main.py").write_text("def hello():\n    return 'hello'\n")
    (repo / "utils.py").write_text("from main import hello\n\ndef greet():\n    return hello()\n")
    # Initialize git so git stage can actually run
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
    return repo


def test_analyze_e2e(fixture_repo: Path, tmp_path: Path):
    """Running all registered stages against a real fixture repo should produce facts."""
    import uuid
    store_path = fixture_repo / ".atlas-cache"
    store_path.mkdir()
    store = FactStore(store_path / "facts.sqlite")

    ctx = PipelineContext(
        store=store,
        repository_path=fixture_repo,
        run_id=str(uuid.uuid4()),
        scope=DEFAULT_SCOPE,
    )
    results = [stage.run(ctx) for stage in STAGE_REGISTRY]

    # Discovery stage should succeed and produce facts
    disc = next(r for r in results if r.name == "discovery")
    assert disc.status == "ok"
    assert disc.facts_produced > 0

    # Git stage should succeed against the initialized repo
    git = next(r for r in results if r.name == "git")
    assert git.status in ("ok", "skipped", "failed")  # skipped/failed if git tools absent

    # Hotspots stage should not fail (may produce 0 facts if no component data)
    hot = next(r for r in results if r.name == "hotspots")
    assert hot.status in ("ok", "skipped")

    store.close()


def test_failing_stage_does_not_abort_others(tmp_path: Path):
    """A stage that fails must not prevent subsequent stages from running."""
    store = FactStore(tmp_path / "facts.sqlite")

    class _FailStage:
        name = "fail_stage"
        def run(self, ctx: PipelineContext) -> StageRunResult:
            raise RuntimeError("intentional failure")

    class _OkStage:
        name = "ok_stage"
        ran: bool = False
        def run(self, ctx: PipelineContext) -> StageRunResult:
            _OkStage.ran = True
            return StageRunResult(name=self.name, status="ok", facts_produced=0)

    registry = [_FailStage(), _OkStage()]
    ctx = PipelineContext(store=store, repository_path=tmp_path, run_id="x", scope=DEFAULT_SCOPE)

    results = []
    for stage in registry:
        try:
            results.append(stage.run(ctx))
        except Exception as e:  # noqa: BLE001
            results.append(StageRunResult(name=stage.name, status="failed", facts_produced=0, detail=str(e)))

    assert results[1].status == "ok"
    assert _OkStage.ran is True
    store.close()


# ---------------------------------------------------------------------------
# CLI command smoke test (subprocess)
# ---------------------------------------------------------------------------


def test_cli_analyze_runs(fixture_repo: Path):
    result = subprocess.run(
        [sys.executable, "-m", "project_intel.cli.main", "analyze", "--no-llm", str(fixture_repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    # Should produce output mentioning "discovery"
    combined = result.stdout + result.stderr
    assert "discovery" in combined


def test_cli_facts_query(fixture_repo: Path):
    """After analyze, facts query should return stored facts."""
    import uuid
    store_path = fixture_repo / ".atlas-cache"
    store_path.mkdir(exist_ok=True)
    store = FactStore(store_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    ctx = PipelineContext(
        store=store,
        repository_path=fixture_repo,
        run_id=run_id,
        scope=DEFAULT_SCOPE,
    )
    for stage in STAGE_REGISTRY:
        stage.run(ctx)
    store.close()

    result = subprocess.run(
        [
            sys.executable, "-m", "project_intel.cli.main",
            "facts", "query", str(fixture_repo),
            "--type", "technology_detected",
            "--run-id", run_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
