# Feature 10 — Onboarding path

## Depends on

Feature 01 (Facts & Evidence model), Feature 05 (Code graph), Feature 06 (Hotspots), Feature 07 (LLM orchestration framework), Feature 08 (Architecture interpretation), Feature 09 (Domain understanding).

## Goal

Synthesize a recommended entry path into the codebase — what to read first, what workflow to follow, what to avoid initially — per the Capability Matrix §16 and the Product Brief's third framing question ("où dois-je regarder en priorité"). This is the last of the three P0 LLM features (alongside Features 08 and 09); it is the one that ties their outputs together rather than reading raw code itself.

## Scope

### Input is synthesis-of-syntheses, not raw content (consistent with Décidé Q93/Q87)

This feature's LLM input is **not** a fresh file/content selection — it's the already-bounded, already-cited outputs of Features 05/06/08/09 (graph entrypoints, hotspot rankings, architecture hypotheses, domain workflows). This keeps it cheap and naturally within budget (Feature 07's budget contract still applies, but the input is inherently small since it's facts-about-facts, not file content).

### Output shape

An LLM call (Feature 07 contract) returning:
- `entry_points: list[{component, fact_ids, rationale}]` — what to look at first, citing hotspot/graph facts.
- `recommended_workflow: {description, fact_ids}` — reuses a Feature 09 workflow fact where one exists, rather than inventing a new one.
- `avoid_initially: list[{component, fact_ids, rationale}]` — e.g. high-complexity, low-centrality areas irrelevant to a first pass.
- `time_boxed_understanding: {thirty_minutes: str, two_hours: str}` — directly matching the Capability Matrix's "que peut-on comprendre en 30 min / 2h" questions.
- `open_questions: list[str]` — explicit unresolved items, which is itself a form of **Décidé "never pretend to know"**: the onboarding path must be able to say what it *doesn't* know, not just what it recommends.

All narrative fields carry `fact_ids` and `confidence` per Feature 07's standard schema contract (same mandatory-citation and hallucination-guard mechanism as Features 08/09 — no new validation logic needed here).

### Result facts

`Fact(type=onboarding_path, subject=Repository|System, value=<the shape above>, provenance=hypothesis)`.

## Explicitly out of scope for this feature

- Any new deterministic computation — this feature is purely a synthesis layer over facts already produced by Features 05/06/08/09; if a needed signal doesn't exist yet in the `FactStore`, that signal belongs in an earlier feature, not bolted on here.
- Per-component onboarding queries scoped to "where do I start to understand X specifically" (Capability Matrix Q151, listed under MCP) — this feature produces the whole-repository/system path; a component-scoped variant is the MCP server feature's concern (it reuses this feature's underlying facts/mechanism, per **Décidé Q151**, but isn't built here).
- Any UI/report rendering of the path — HTML report feature, later.

## Acceptance criteria

- Input assembly pulls only already-stored facts (from Features 05/06/08/09) via the `FactStore` — a test proves this feature makes no direct filesystem/adapter calls of its own.
- Response schema matches the shape above, including the mandatory `open_questions` field.
- A test with a fake `LLMProvider` proves citation validation behaves identically to Features 08/09 (same Feature 07 mechanism, no feature-specific reimplementation).
- A test where an upstream feature (e.g. Architecture interpretation) is `not_analyzed` proves this feature still produces a path using only the available inputs, with `confidence` reflecting the reduced evidence rather than failing outright.
- `uv run pytest` and `uv run ruff check .` pass.
