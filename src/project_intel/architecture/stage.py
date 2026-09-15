"""Architecture interpretation stage — Feature 08."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..cli.types import PipelineContext, Stage, StageRunResult
from ..facts.model import Fact
from ..facts.store import SCHEMA_VERSION
from ..llm.orchestrator import LLMOrchestrator
from ..llm.types import BudgetConfig
from .analyzer import build_prompt, collect_graph_facts
from .schema import ArchitectureHypothesis, ArchitectureResponse, normalize_pattern


def _hypothesis_to_fact(
    hyp: ArchitectureHypothesis,
    run_id: str,
    repository_id: str,
    now: datetime,
) -> Fact:
    from ..facts.enums import EntityType
    from ..facts.model import EntityRef

    pattern, pattern_description = normalize_pattern(hyp.pattern, hyp.pattern_description)

    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:architecture:{hyp.pattern}:{hyp.confidence}")),
        type="architecture_hypothesis",
        subject=EntityRef(EntityType.REPOSITORY, repository_id),
        value={
            "pattern": pattern,
            "confidence": hyp.confidence,
            "fact_ids": hyp.fact_ids,
            "pattern_description": pattern_description,
        },
        provenance="hypothesis",
        confidence=hyp.confidence,
        source_analyzer="architecture_interpreter@1.0",
        evidence=(),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


class _ArchitectureStage:
    name = "architecture"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        if ctx.llm_provider is None:
            return StageRunResult(
                name=self.name, status="skipped", facts_produced=0,
                detail="not_analyzed: llm_provider not configured",
            )

        try:
            graph_facts = collect_graph_facts(ctx.store)
            if not graph_facts:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail="not_analyzed: no graph facts available",
                )

            cache_path = ctx.repository_path / ".atlas-cache" / "llm_cache.sqlite"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            orchestrator = LLMOrchestrator.create(
                ctx.llm_provider, ctx.store, cache_path,
                budget_config=BudgetConfig.unlimited(),
            )

            prompt = build_prompt(graph_facts)
            result = orchestrator.complete(prompt, ArchitectureResponse)

            if result.status != "ok" or result.value is None:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail=f"not_analyzed: {result.reason}",
                )

            repo_id = str(ctx.repository_path.resolve())
            now = datetime.now(UTC)
            facts = [
                _hypothesis_to_fact(hyp, ctx.run_id, repo_id, now)
                for hyp in result.value.hypotheses
            ]
            if facts:
                ctx.store.insert_facts(facts)
            return StageRunResult(name=self.name, status="ok", facts_produced=len(facts))

        except Exception as exc:  # noqa: BLE001
            return StageRunResult(
                name=self.name, status="failed", facts_produced=0, detail=str(exc)
            )


STAGE: Stage = _ArchitectureStage()
