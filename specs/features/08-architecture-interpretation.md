# Feature 08 — Architecture interpretation

## Depends on

Feature 01 (Facts & Evidence model), Feature 05 (Code graph), Feature 07 (LLM orchestration framework).

## Goal

Produce named, sourced, confidence-scored architectural hypotheses from the observed graph, per **Décidé Q76–Q83**. This is the first feature whose output is explicitly `hypothesis`-provenance, not `observed`/`computed`.

## Scope

### Observed architecture (Décidé Q76)

Not LLM work: a set of `provenance=computed` facts already available from Feature 05 — layer/community structure from directory conventions and dependency direction, boundary candidates from community detection. This feature reads these facts; it does not add new computation on top of Feature 05's output beyond what's needed to package them as the LLM call's bounded input.

### Interpreted architecture (Décidé Q77–Q80)

An LLM call (via Feature 07) that takes the observed-architecture facts as bounded input and returns a structured response naming a pattern (from a starter catalogue — see below) with:
- `pattern: str`
- `confidence: float` (Décidé Q83, enforced by Feature 07's schema contract)
- `fact_ids: list[str]` citing the observed facts that support it (Décidé Q80, enforced by Feature 07's citation validator)

Result facts are stored with `provenance=hypothesis` (Décidé Q45) — never `observed`/`computed`.

### Pattern catalogue (Proposition Q78)

A small starter list (layered/N-tier, hexagonal/ports-adapters, microservices, modular monolith, event-driven, MVC/MVVM) passed to the LLM as allowed values, with an explicit escape hatch: the model may return `pattern: "uncatalogued"` plus a free-text `pattern_description` rather than being forced into a poor-fit label. This keeps the catalogue extensible without a code change every time a new pattern name is needed.

### Multiple competing hypotheses (Décidé Q82)

Uses Feature 07's multi-hypothesis schema shape directly — the response schema for this feature is `hypotheses: list[ArchitectureHypothesis]`, not a single best-guess field. When the observed graph is ambiguous, more than one entry is expected and both are surfaced, each with its own confidence.

### Hallucination guard (Décidé Q81)

Entirely delegated to Feature 07: this feature supplies the fact ids available for citation as part of the bounded input; Feature 07's citation validator rejects any response citing ids outside that set. This feature adds no separate validation logic of its own.

## CLI stage registration (Feature 06b)

This feature exposes a module-level `STAGE: Stage` object (name `"architecture"`) per [06b](06b-minimal-cli.md)'s contract. Its `run()` reads `PipelineContext.llm_provider` — if `None` (LLM disabled, per Feature 07's no-op provider), the stage reports `status=skipped` with the same `not_analyzed: llm_failed` outcome its own spec already requires for a disabled/failed LLM, rather than erroring. Registering it is one import + one entry in `STAGE_REGISTRY`, placed after `code_graph` since it reads that stage's output.

## Explicitly out of scope for this feature

- Comparing declared (documentation) vs. observed architecture (**Proposition Q84**, P1, not decided in detail) — this feature only interprets the observed graph, it does not read or extract a "declared" architecture from documentation.
- Boundary-violation detection (Capability Matrix P1) — not part of this feature's scope; it interprets structure, it doesn't flag deviations from an interpreted structure.
- Content selection for LLM input — this feature's input is graph facts (already bounded/structured by Feature 05), not a general file/document selection problem; that selection logic (relevant to Domain Understanding) is a separate concern.

## Acceptance criteria

- Reads observed/computed graph facts from the `FactStore` and packages them as Feature 07's `StructuredPrompt` input.
- Response schema supports multiple hypotheses, each with `pattern` (from the catalogue, or `uncatalogued` + description), `confidence`, and `fact_ids`.
- Every stored result fact has `provenance=hypothesis`.
- A test using a fake `LLMProvider` (per Feature 07's test harness) proves: a response citing a real fact id is accepted and stored; a response citing a fake id is rejected via Feature 07's validator and surfaces as `not_analyzed: llm_failed` for this feature, not silently corrected.
- A test with LLM disabled (Feature 07's no-op provider) proves the rest of the pipeline still completes, with this feature's section marked `not_analyzed`.
- A `STAGE` object registered in `STAGE_REGISTRY` (after `code_graph`) runs this feature end-to-end via `project-intel analyze` (Feature 06b), including the LLM-disabled degrade path.
- `uv run pytest` and `uv run ruff check .` pass.
