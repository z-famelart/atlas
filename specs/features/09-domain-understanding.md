# Feature 09 — Domain understanding

## Depends on

Feature 01 (Facts & Evidence model), Feature 06 (Hotspots — for file selection), Feature 07 (LLM orchestration framework).

## Goal

Deterministically select a bounded, relevant slice of the repository, then run it through the LLM to synthesize business concepts, workflows, and glossary — per **Décidé Q87, Q92–Q93, Q85** (partially) — while never sending the repository wholesale to the LLM.

## Scope

### Deterministic file selection (Décidé Q87, Q93)

The selector is **not** LLM-driven. It reuses Feature 06's hotspot/centrality scores directly: the top-N files by combined hotspot score, plus files identified as entrypoints (from Feature 05's graph facts), form the candidate set. This is the concrete mechanism that satisfies **Décidé Q93** ("comment évitons-nous d'envoyer tout le repository au LLM") — selection is bounded by construction, not by a post-hoc truncation of a larger set.

### Test selection (Proposition Q88)

Tests covering the selected files (via a test→code mapping where determinable) plus tests whose path/name suggests a business workflow (simple naming heuristic, deterministic pattern matching — not LLM). Included as part of the same bounded candidate set, not a separate unbounded pass.

### Budget enforcement (Décidé Q86, Q100)

The candidate set (files + tests + their content) is handed to Feature 07's `StructuredPrompt` mechanism, which enforces the token budget for this call-site category. This feature does not implement its own truncation logic — it relies entirely on Feature 07's budget contract and must gracefully accept a `not_analyzed: budget_exceeded` outcome for this section without special-casing it.

### Synthesis output (Décidé Q92, from Product Brief §4.3)

An LLM call (Feature 07 contract) returning structured facts for:
- business concepts (`type=business_concept`, `provenance=hypothesis`)
- workflows (`type=business_workflow`, `provenance=hypothesis`)
- glossary terms (`type=glossary_term`, `provenance=hypothesis`)

Every entry carries `fact_ids` (Feature 07's mandatory-citation contract) pointing at the specific files/tests in the candidate set that motivated it (**Décidé Q92**: "comment conservons-nous les preuves" — same evidence-preservation mechanism as everything else in this project, not a bespoke one for this feature).

### Secrets check before LLM send (Décidé Q165, forward-looking)

**Not built in this feature** (see Explicitly out of scope) but this feature's selector must be structured so a secrets-scanning pass can be inserted between "candidate set selected" and "sent to Feature 07" without restructuring the selection logic — i.e., selection produces an intermediate `list[CandidateContent]` object rather than calling the LLM inline.

## Explicitly out of scope for this feature

- State machine / event extraction (Q90/Q91, P1, not decided in detail — Proposition only) — not built here; this feature covers concepts/workflows/glossary only.
- Actor extraction (Capability Matrix Q99, P1) — not in this feature.
- Multi-provider LLM selection logic — already handled generically by Feature 07; this feature just calls it.
- Secrets scanning itself (**Proposition Q165**, not decided) — noted above as a seam to leave open, not to implement.
- Documentation-drift detection (Q84/Capability Matrix §14, P1) — separate concern, not in this feature.

## Acceptance criteria

- Selector produces a bounded `list[CandidateContent]` from hotspot scores (Feature 06) + entrypoints (Feature 05) + test mapping, with a configurable `top_n` — no code path that can select "everything."
- A test proves that increasing repository size does not unboundedly increase the candidate set (selection is capped by `top_n`, not proportional to repo size).
- Synthesis call uses Feature 07's `StructuredPrompt`/citation contract; a test with a fake provider proves citations are validated against the candidate set's underlying facts exactly as in Feature 08.
- Result facts (`business_concept`, `business_workflow`, `glossary_term`) are `provenance=hypothesis` with valid `fact_ids`.
- `uv run pytest` and `uv run ruff check .` pass.
