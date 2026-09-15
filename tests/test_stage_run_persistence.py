"""Tests for Feature 06c — persist stage run outcomes as facts."""

from __future__ import annotations

import uuid
from pathlib import Path

from project_intel.cli.main import _run_stage_safe
from project_intel.cli.registry import STAGE_REGISTRY
from project_intel.cli.types import PipelineContext, StageRunResult
from project_intel.discovery.scope import ScopeConfig
from project_intel.facts.store import FactStore

_SCOPE = ScopeConfig(exclude_globs=(".git/*", ".git"))


def _ctx(tmp_path: Path, store: FactStore, run_id: str) -> PipelineContext:
    return PipelineContext(store=store, repository_path=tmp_path, run_id=run_id, scope=_SCOPE)


def test_one_fact_per_stage_per_run(tmp_path: Path):
    store = FactStore(tmp_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    ctx = _ctx(tmp_path, store, run_id)

    for stage in STAGE_REGISTRY:
        _run_stage_safe(stage, ctx)

    results = list(store.query_facts(type="stage_run_result", run_id=run_id))
    assert len(results) == len(STAGE_REGISTRY)
    assert {r.value["stage"] for r in results} == {s.name for s in STAGE_REGISTRY}
    store.close()


def test_skipped_stage_persists_detail(tmp_path: Path):
    store = FactStore(tmp_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    ctx = _ctx(tmp_path, store, run_id)

    class _SkippedStage:
        name = "fake_llm_stage"

        def run(self, ctx: PipelineContext) -> StageRunResult:
            return StageRunResult(
                name=self.name, status="skipped", facts_produced=0,
                detail="not_analyzed: llm_failed",
            )

    _run_stage_safe(_SkippedStage(), ctx)

    results = list(store.query_facts(type="stage_run_result", run_id=run_id))
    assert len(results) == 1
    assert results[0].value["status"] == "skipped"
    assert "not_analyzed: llm_failed" in results[0].value["detail"]
    store.close()


def test_failed_stage_still_persists(tmp_path: Path):
    store = FactStore(tmp_path / "facts.sqlite")
    run_id = str(uuid.uuid4())
    ctx = _ctx(tmp_path, store, run_id)

    class _RaisingStage:
        name = "fake_failing_stage"

        def run(self, ctx: PipelineContext) -> StageRunResult:
            raise RuntimeError("boom")

    _run_stage_safe(_RaisingStage(), ctx)

    results = list(store.query_facts(type="stage_run_result", run_id=run_id))
    assert len(results) == 1
    assert results[0].value["status"] == "failed"
    assert "boom" in results[0].value["detail"]
    store.close()
