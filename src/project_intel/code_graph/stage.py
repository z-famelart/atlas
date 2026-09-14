"""Code graph stage — runs graphify (if available) then graph metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from ..adapters.manifest import AdapterContext
from ..adapters.runner import _run_one
from ..cli.types import PipelineContext, Stage, StageRunResult
from .graphify_provider import GraphifyProvider
from .metrics import compute_centrality, detect_communities, detect_cycles


class _CodeGraphStage:
    name = "code_graph"

    def run(self, ctx: PipelineContext) -> StageRunResult:
        repo_id = str(ctx.repository_path.resolve())
        adapter_ctx = AdapterContext(
            target_path=ctx.repository_path,
            run_id=ctx.run_id,
            repository_id=repo_id,
            timestamp=datetime.now(UTC),
        )

        facts = []
        notes = []

        # 1. Graphify provider (may skip if tool not installed)
        provider = GraphifyProvider()
        manifest = provider.manifest()
        result = _run_one(manifest, adapter_ctx)
        if result.facts:
            facts.extend(result.facts)
            ctx.store.insert_facts(list(result.facts))
        if result.error:
            notes.append(f"graphify: {result.error}")

        # 2. Graph metrics — operate on whatever relation facts are now in the store
        for fn in (compute_centrality, detect_communities, detect_cycles):
            try:
                metric_facts = fn(ctx.store, repo_id, ctx.run_id)
                facts.extend(metric_facts)
                if metric_facts:
                    ctx.store.insert_facts(metric_facts)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{fn.__name__}: {exc}")

        detail = "; ".join(notes) if notes else None
        return StageRunResult(
            name=self.name,
            status="ok",
            facts_produced=len(facts),
            detail=detail,
        )


STAGE: Stage = _CodeGraphStage()
