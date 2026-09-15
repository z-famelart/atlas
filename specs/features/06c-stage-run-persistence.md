# Feature 06c — Persist stage run outcomes as facts

## Why this is a separate feature, not a rewrite of Feature 06b/13

Feature 06b (minimal CLI, `Stage`/`PipelineContext`/`StageRunResult`/`STAGE_REGISTRY`) and Feature 13 (full CLI, the actual runner loop) are **already implemented**. Per the [regeneration contract](README.md#regeneration-contract), this feature does not change `StageRunResult`'s shape or the `Stage` protocol — it adds one small, purely additive step to the runner loop: **persist** each `StageRunResult` it already produces, instead of only printing it and discarding it.

This exists because of a concrete gap found while diagnosing why the HTML report showed "Not analyzed" for Architecture/Domain on a real run (`atlas-report-f93202e8...html` against ggshield): the underlying stage (`architecture/stage.py`) *does* compute a precise reason — `StageRunResult(status="skipped", detail="not_analyzed: llm_failed")`, since Ollama's citation validation rejected the response — but that `detail` string only ever reaches the terminal via Feature 13's live progress display. Nothing durable records it. A report (or MCP query, or anything else) generated after the fact has no way to know *why* a section came up empty this run, only that it did.

## Depends on

Feature 06b (`Stage`, `PipelineContext`, `StageRunResult` — unchanged) and Feature 01 (Facts & Evidence model — this feature reuses the existing `Fact`/`FactStore` machinery, no new store mechanism). Feature 13 (the actual runner loop that calls `stage.run(ctx)` in order) is where this feature's one hook is added.

## Goal

Every `StageRunResult` a stage returns is written to the `FactStore` as a fact, so any later consumer — the HTML report (see [11c](11c-report-fidelity-fixes.md)), the MCP server, a future dashboard — can answer "what happened to stage X in run Y" without re-running anything or grepping old terminal output.

## Scope

### `stage_run_result` fact type

After each `stage.run(ctx)` call in the runner loop (Feature 13's `analyze` command, same loop that already drives the live progress display), insert one fact:

```python
Fact(
    type="stage_run_result",
    subject=EntityRef(EntityType.REPOSITORY, repository_id),
    value={
        "stage": result.name,
        "status": result.status,        # "ok" | "skipped" | "failed", unchanged vocabulary
        "facts_produced": result.facts_produced,
        "detail": result.detail,        # already-computed reason string, e.g. "not_analyzed: llm_failed"
    },
    provenance="computed",
    confidence=1.0,
    source_analyzer="cli.runner@1.0",
    evidence=(),
    run_id=ctx.run_id,
)
```

One fact per stage per run — not per adapter call, not per retry. This is bookkeeping about the run itself, not new evidence about the repository, but it fits the existing `Fact` model exactly (typed value, `provenance=computed`, queryable by `type`/`run_id` like anything else) rather than inventing a second, parallel storage mechanism.

### No change to the runner's control flow

This is purely an additional `store.insert_facts([...])` call after each stage completes — it does not change failure isolation, does not change what's printed to the console, does not change `STAGE_REGISTRY` iteration order, and does not make a stage's own `run()` responsible for this (the runner does it once, generically, for every stage — a stage's own code is completely unaware this happens, exactly like 06b's original design already keeps stages unaware of how their result gets displayed).

## Explicitly out of scope for this feature

- Changing `StageRunResult`, `Stage`, or `PipelineContext` — all reused exactly as shipped.
- Any new query method on `FactStore` — `query_facts(type="stage_run_result", run_id=...)` (or without `run_id` for cross-run lookups, per [11c](11c-report-fidelity-fixes.md)) already works with the existing interface.
- Consuming these facts anywhere — that's [11c](11c-report-fidelity-fixes.md)'s job (the HTML report) and, later, anything else that wants them. This feature only produces them.
- Retrying a failed/skipped stage automatically, or any change to why a stage fails — purely a persistence addition, not a reliability fix.

## Acceptance criteria

- Running `atlas analyze` produces exactly one `stage_run_result` fact per registered stage per run, queryable via `store.query_facts(type="stage_run_result", run_id=<that run>)`.
- A stage that returns `status="skipped", detail="not_analyzed: llm_failed"` (simulated via a fake failing `LLMProvider`, same test harness Feature 07/08 already use) produces a `stage_run_result` fact whose `value["detail"]` contains that exact string.
- A stage that raises and is caught by the runner's existing failure-isolation (`status="failed"`) still produces a `stage_run_result` fact for that stage — persistence happens even when the stage itself errors, since the runner (not the stage) is responsible for the insert.
- `uv run pytest` and `uv run ruff check .` pass.
