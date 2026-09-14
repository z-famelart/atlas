"""Hotspots stage — runs the scoring engine for the CLI pipeline."""

from __future__ import annotations

from ..cli.types import PipelineContext, Stage, StageRunResult
from .scorer import compute_hotspots


class _HotspotsStage:
    name = "hotspots"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        try:
            repo_id = str(ctx.repository_path.resolve())
            facts = compute_hotspots(ctx.store, repo_id, ctx.run_id)
            if facts:
                ctx.store.insert_facts(facts)
            return StageRunResult(name=self.name, status="ok", facts_produced=len(facts))
        except Exception as exc:  # noqa: BLE001
            return StageRunResult(name=self.name, status="failed", facts_produced=0, detail=str(exc))


STAGE: Stage = _HotspotsStage()
