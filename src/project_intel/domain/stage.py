"""Domain understanding stage — Feature 09."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..cli.types import PipelineContext, Stage, StageRunResult
from ..facts.enums import EntityType
from ..facts.model import EntityRef, Fact
from ..facts.store import SCHEMA_VERSION
from ..llm.orchestrator import LLMOrchestrator
from ..llm.types import BudgetConfig
from .analyzer import build_prompt
from .schema import BusinessConcept, BusinessWorkflow, DomainResponse, GlossaryTerm
from .selector import CandidateContent, select_candidates

_ANALYZER = "domain_understanding@1.0"


def _concept_to_fact(item: BusinessConcept, run_id: str, repo_id: str, now: datetime) -> Fact:
    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:business_concept:{item.name}")),
        type="business_concept",
        subject=EntityRef(EntityType.REPOSITORY, repo_id),
        value={"name": item.name, "description": item.description, "fact_ids": item.fact_ids},
        provenance="hypothesis",
        confidence=0.7,
        source_analyzer=_ANALYZER,
        evidence=(),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


def _workflow_to_fact(item: BusinessWorkflow, run_id: str, repo_id: str, now: datetime) -> Fact:
    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:business_workflow:{item.name}")),
        type="business_workflow",
        subject=EntityRef(EntityType.REPOSITORY, repo_id),
        value={"name": item.name, "description": item.description, "fact_ids": item.fact_ids},
        provenance="hypothesis",
        confidence=0.7,
        source_analyzer=_ANALYZER,
        evidence=(),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


def _glossary_to_fact(item: GlossaryTerm, run_id: str, repo_id: str, now: datetime) -> Fact:
    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:glossary_term:{item.term}")),
        type="glossary_term",
        subject=EntityRef(EntityType.REPOSITORY, repo_id),
        value={"term": item.term, "definition": item.definition, "fact_ids": item.fact_ids},
        provenance="hypothesis",
        confidence=0.7,
        source_analyzer=_ANALYZER,
        evidence=(),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


class _DomainStage:
    name = "domain"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        if ctx.llm_provider is None:
            return StageRunResult(
                name=self.name, status="skipped", facts_produced=0,
                detail="not_analyzed: llm_provider not configured",
            )

        try:
            candidates: list[CandidateContent] = select_candidates(
                ctx.store, ctx.repository_path, run_id=ctx.run_id
            )
            if not candidates:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail="not_analyzed: no candidate files selected",
                )

            cache_path = ctx.repository_path / ".atlas-cache" / "llm_cache.sqlite"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            orchestrator = LLMOrchestrator.create(
                ctx.llm_provider, ctx.store, cache_path,
                budget_config=BudgetConfig.unlimited(),
            )

            prompt = build_prompt(candidates)
            result = orchestrator.complete(prompt, DomainResponse)

            if result.status != "ok" or result.value is None:
                return StageRunResult(
                    name=self.name, status="skipped", facts_produced=0,
                    detail=f"not_analyzed: {result.reason}",
                )

            repo_id = str(ctx.repository_path.resolve())
            now = datetime.now(UTC)
            facts: list[Fact] = []
            for c in result.value.concepts:
                facts.append(_concept_to_fact(c, ctx.run_id, repo_id, now))
            for w in result.value.workflows:
                facts.append(_workflow_to_fact(w, ctx.run_id, repo_id, now))
            for g in result.value.glossary:
                facts.append(_glossary_to_fact(g, ctx.run_id, repo_id, now))

            if facts:
                ctx.store.insert_facts(facts)
            return StageRunResult(name=self.name, status="ok", facts_produced=len(facts))

        except Exception as exc:  # noqa: BLE001
            return StageRunResult(
                name=self.name, status="failed", facts_produced=0, detail=str(exc)
            )


STAGE: Stage = _DomainStage()
