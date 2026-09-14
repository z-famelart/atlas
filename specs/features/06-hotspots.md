# Feature 06 — Hotspots

## Depends on

Feature 01 (Facts & Evidence model), Feature 04 (Git analysis), Feature 05 Part A (Code graph — internal calculations; the scoring engine only needs centrality facts to exist in the shape Feature 05 Part A produces, not a real concrete `GraphProvider`). **Part B** additionally depends on Feature 02b (MVP scope decision) being resolved.

## Goal

Combine complexity, size, graph centrality, and Git churn into an explainable, decomposable hotspot score, per **Décidé Q64/Q69–Q75**.

This feature is split into two parts, buildable independently:

- **Part A — Scoring engine.** Normalization, combination, decomposition, missing-data handling, configurable weights. Consumes whatever complexity/size/centrality/churn facts already exist in the `FactStore`, regardless of which language/tool produced them — fully testable against hand-authored fixture facts. Buildable now.
- **Part B — Concrete complexity adapter.** Requires a target language/tool chosen via Feature 02b. **Do not implement Part B until Feature 02b is resolved** — see the rule in [02b](02b-mvp-scope-decision.md). If you reach this spec before that's resolved, implement Part A in full (tested against fixture facts standing in for complexity/size/centrality/churn), stop, and follow Feature 02b's instructions before touching Part B.

## Part A — Scoring engine (buildable now)

### Score components (Décidé Q64, Q69, Q70, Q71)

Exactly four components for the MVP score, each read from facts already in the `FactStore` (no re-computation of underlying data):
- complexity (produced by Part B, once implemented — Part A only needs the fact *shape*, not a live adapter)
- size / LOC (from Feature 03 Part B's language/LOC facts — same caveat)
- graph centrality (from Feature 05 Part A)
- Git churn (from Feature 04)

Because Part A only reads facts by type/shape from the `FactStore`, it can and must be built and tested before Parts B of Features 03/06 exist, using hand-authored fixture facts of the right shape for all four components.

### Normalization (Décidé Q67, Q68)

Each component is normalized to the project's own local distribution (percentile or z-score) **before** weighting — no cross-project comparison, no raw absolute values mixed with normalized ones. Size specifically is log-normalized before combination, precisely to prevent a single enormous file dominating the score purely on line count (**Décidé Q68**) — the spec is explicit that size must never be used as a signal on its own, only combined with the other three.

### Combination & explainability (Décidé Q64, Q73, Q75)

```
Fact(
  type=hotspot_score,
  subject=File,
  value={
    combined: float,
    components: {
      complexity: {raw, normalized, weight},
      size:       {raw, normalized, weight},
      centrality: {raw, normalized, weight},
      churn:      {raw, normalized, weight},
    },
  },
  provenance=computed,
  evidence=[<facts each component was computed from>],
)
```

The decomposition (per-component raw + normalized + weight) is **not optional** — a hotspot fact without it is invalid per **Décidé Q73** ("le hotspot score doit être explicable et décomposable"). Per **Proposition Q75**, this feature also emits the four component sub-scores as independently queryable facts (not just embedded in the combined score), so a consumer can ask for "Git hotspots" alone without recomputing.

### Missing data (Décidé Q74)

If a component is unavailable for a given file (e.g. no complexity tool for that language, or the file has no Git history because it's untracked), that component is **excluded from the combination** and explicitly flagged as missing in the decomposition — never silently treated as zero. A file with fewer available components is marked as such (e.g. `components_available: 3/4`) so the report/MCP layer can surface that the score is based on partial data. This is also what makes Part A independently useful before Part B exists: a repository with no complexity adapter available yet still gets a valid, explicitly `components_available: 3/4` hotspot score from size/centrality/churn alone.

### Weights (Décidé Q65)

Weights are configurable, with defined defaults; this feature must accept a `HotspotWeights` config object rather than hard-coding weight constants inside the scoring function.

## Part B — Concrete complexity adapter (gated on Feature 02b)

### Complexity adapter (Décidé Q71, concrete choice gated by Feature 02b)

One adapter (Feature 02 contract) wrapping an existing complexity tool for the language(s) chosen in Feature 02b (cyclomatic/cognitive complexity), producing `Fact(type=complexity, subject=File|Symbol, value=<score>, provenance=observed)`. Its job is purely translation — Part A's scoring engine already consumes whatever this adapter produces, unchanged.

## CLI stage registration (Feature 06b)

This feature exposes a module-level `STAGE: Stage` object (name `"hotspots"`) per [06b](06b-minimal-cli.md)'s contract, whose `run()` invokes Part A's scoring engine against whatever complexity/size/centrality/churn facts already exist in the store (per Q74's missing-data handling, a partial component set still produces a valid, decomposed score), and Part B's complexity adapter first if implemented. Registering it is one import + one entry in `STAGE_REGISTRY` — no other code in 06b changes. Once registered, this is also the first stage in the list whose ordering matters: it must run after `discovery`, `git`, and `code_graph` in `STAGE_REGISTRY`, since it reads their output.

## Explicitly out of scope for this feature

- Adaptive/context-sensitive weighting (**Proposition Q66**, not decided) — fixed default weights only, no adaptive logic.
- Runtime-data component (**Proposition Q72**, P1, not decided) — do not add a fifth component; the score is explicitly four-component for MVP and must be structured so a fifth can be added later without reshaping the fact type.
- Any LLM-based "why is this a hotspot" narrative — the Capability Matrix marks that cell as LLM (P0), but it consumes this feature's decomposed facts; producing the narrative is part of a later synthesis feature, not this one.
- Part B before Feature 02b is resolved — see above.

## Acceptance criteria

### Part A

- Scoring function reads complexity/size/centrality/churn facts from the `FactStore` by type/shape (no direct coupling to Features 03/04/05 internals) and produces decomposed `hotspot_score` facts, tested against hand-authored fixture facts covering all four components.
- Normalization is local-distribution-based and size is log-normalized; a test with one artificially huge, otherwise-unremarkable file confirms it does not dominate the ranking.
- A test with a file missing one component (e.g. no complexity fact present) confirms that component is flagged absent, not treated as zero, and the combined score is computed from the remaining components with `components_available` set correctly.
- Weights are configurable via a passed-in config object, with a documented default.
- A `STAGE` object registered in `STAGE_REGISTRY` (after `discovery`/`git`/`code_graph`) runs Part A end-to-end (and Part B too, if present) via `project-intel analyze` (Feature 06b).
- `uv run pytest` and `uv run ruff check .` pass.

### Part B (only after Feature 02b is resolved)

- Complexity adapter implemented and contract-tested per Feature 02, for the tool chosen in Feature 02b.
- Running Part A's scoring engine against this adapter's real output (on a small real fixture repository in the chosen language, alongside real size/centrality/churn facts) produces a 4/4-component score — proving the two parts compose correctly.
- `uv run pytest` and `uv run ruff check .` pass.
