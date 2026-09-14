"""Onboarding path synthesis stage — Feature 10."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..cli.types import PipelineContext, Stage, StageRunResult
from ..facts.enums import EntityType
from ..facts.model import EntityRef, Fact
from ..facts.store import SCHEMA_VERSION
from ..llm.orchestrator import LLMOrchestrator
from ..llm.types import BudgetConfig
from .analyzer import build_prompt, collect_input_facts
from .schema import OnboardingPathResponse

_ANALYZER = "onboarding_path@1.0"


def _path_to_fact(
    response: OnboardingPathResponse,
    run_id: str,
    repo_id: str,
    now: datetime,
) -> Fact:
    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:onboarding_path")),
        type="onboarding_path",
        subject=EntityRef(EntityType.REPOSITORY, repo_id),
        value={
            "entry_points": [
                {"component": e.component, "fact_ids": e.fact_ids, "rationale": e.rationale}
                for e in response.entry_points
            ],
            "recommended_workflow": {
                "description": response.recommended_workflow.description,
                "fact_ids": response.recommended_workflow.fact_ids,
            },
            "avoid_initially": [
                {"component": a.component, "fact_ids": a.fact_ids, "rationale": a.rationale}
                for a in response.avoid_initially
            ],
            "time_boxed_understanding": {
                "thirty_minutes": response.time_boxed_understanding.thirty_minutes,
                "two_hours": response.time_boxed_understanding.two_hours,
            },
            "open_questions": response.open_questions,
            "confidence": response.confidence,
            "fact_ids": response.fact_ids,
        },
        provenance="hypothesis",
        confidence=response.confidence,
        source_analyzer=_ANALYZER,
        evidence=(),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


class _OnboardingStage:
    name = "onboarding"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        if ctx.llm_provider is None:
            return StageRunResult(
                name=self.name, status="skipped", facts_produced=0,
                detail="not_analyzed: llm_provider not configured",
            )

        try:
            input_facts = collect_input_facts(ctx.store)
            if not input_facts:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail="not_analyzed: no input facts available from upstream stages",
                )

            cache_path = ctx.repository_path / ".atlas-cache" / "llm_cache.sqlite"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            orchestrator = LLMOrchestrator.create(
                ctx.llm_provider, ctx.store, cache_path,
                budget_config=BudgetConfig.unlimited(),
            )

            prompt = build_prompt(input_facts)
            result = orchestrator.complete(prompt, OnboardingPathResponse)

            if result.status != "ok" or result.value is None:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail=f"not_analyzed: {result.reason}",
                )

            repo_id = str(ctx.repository_path.resolve())
            now = datetime.now(UTC)
            fact = _path_to_fact(result.value, ctx.run_id, repo_id, now)
            ctx.store.insert_facts([fact])
            return StageRunResult(name=self.name, status="ok", facts_produced=1)

        except Exception as exc:  # noqa: BLE001
            return StageRunResult(
                name=self.name, status="failed", facts_produced=0, detail=str(exc)
            )


STAGE: Stage = _OnboardingStage()
