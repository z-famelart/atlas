"""Git analysis stage — runs churn + co-change adapters for the CLI pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from ..adapters.manifest import AdapterContext
from ..adapters.runner import _run_one
from ..cli.types import PipelineContext, Stage, StageRunResult
from .churn import churn_manifest
from .cochange import cochange_manifest


class _GitStage:
    name = "git"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        repo_id = str(ctx.repository_path.resolve())
        adapter_ctx = AdapterContext(
            target_path=ctx.repository_path,
            run_id=ctx.run_id,
            repository_id=repo_id,
            timestamp=datetime.now(UTC),
        )
        facts = []
        errors = []
        for manifest in (churn_manifest(), cochange_manifest()):
            result = _run_one(manifest, adapter_ctx)
            if result.facts:
                facts.extend(result.facts)
            if result.error:
                errors.append(f"{manifest.name}: {result.error}")

        if facts:
            ctx.store.insert_facts(facts)

        if not facts and errors:
            return StageRunResult(
                name=self.name, status="failed", facts_produced=0, detail="; ".join(errors)
            )
        detail = "; ".join(errors) if errors else None
        return StageRunResult(
            name=self.name,
            status="ok",
            facts_produced=len(facts),
            detail=detail,
        )


STAGE: Stage = _GitStage()
