"""Discovery stage — wraps run_discovery() for the CLI pipeline."""

from __future__ import annotations

from ..cli.types import PipelineContext, Stage, StageRunResult
from .runner import run_discovery


class _DiscoveryStage:
    name = "discovery"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        try:
            repo_id = str(ctx.repository_path.resolve())
            result = run_discovery(ctx.repository_path, repo_id, ctx.run_id, ctx.scope)
            ctx.store.insert_facts(result.facts)
            return StageRunResult(name=self.name, status="ok", facts_produced=len(result.facts))
        except Exception as exc:  # noqa: BLE001
            return StageRunResult(name=self.name, status="failed", facts_produced=0, detail=str(exc))


STAGE: Stage = _DiscoveryStage()
