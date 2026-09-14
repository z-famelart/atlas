"""Hotspots stage — runs complexity adapter then scoring engine for the CLI pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

from ..adapters.manifest import AdapterContext
from ..adapters.runner import _run_one
from ..cli.types import PipelineContext, Stage, StageRunResult
from .complexity_adapter import lizard_manifest
from .scorer import compute_hotspots


class _HotspotsStage:
    name = "hotspots"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        try:
            repo_id = str(ctx.repository_path.resolve())
            notes: list[str] = []

            # Part B: run complexity adapter first so scorer has all 4 components
            adapter_ctx = AdapterContext(
                target_path=ctx.repository_path,
                run_id=ctx.run_id,
                repository_id=repo_id,
                timestamp=datetime.now(UTC),
            )
            result = _run_one(lizard_manifest(), adapter_ctx)
            complexity_count = 0
            if result.facts:
                ctx.store.insert_facts(list(result.facts))
                complexity_count = len(result.facts)
            if result.error:
                notes.append(f"lizard: {result.error}")

            # Part A: scoring engine
            hotspot_facts = compute_hotspots(ctx.store, repo_id, ctx.run_id)
            if hotspot_facts:
                ctx.store.insert_facts(hotspot_facts)

            total = complexity_count + len(hotspot_facts)
            return StageRunResult(
                name=self.name,
                status="ok",
                facts_produced=total,
                detail="; ".join(notes) or None,
            )
        except Exception as exc:  # noqa: BLE001
            return StageRunResult(name=self.name, status="failed", facts_produced=0, detail=str(exc))


STAGE: Stage = _HotspotsStage()
