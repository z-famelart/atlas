# Feature 06 — Hotspots

## Depends on

Feature 01 (Facts & Evidence model), Feature 04 (Git analysis), Feature 05 (Code graph). Also needs a complexity metric, which per **Décidé Q71** comes from an existing tool via the Feature 02 adapter contract — this feature includes that one adapter since no earlier feature covers it.

## Goal

Combine complexity, size, graph centrality, and Git churn into an explainable, decomposable hotspot score, per **Décidé Q64/Q69–Q75**.

## Scope

### Complexity adapter (Décidé Q71)

One adapter (Feature 02 contract) wrapping an existing complexity tool (cyclomatic/cognitive complexity per language availability), producing `Fact(type=complexity, subject=File|Symbol, value=<score>, provenance=observed)`.

### Score components (Décidé Q64, Q69, Q70, Q71)

Exactly four components for the MVP score, each read from facts already in the `FactStore` (no re-computation of underlying data):
- complexity (this feature's new adapter)
- size / LOC (from Feature 03 Discovery's language/LOC facts)
- graph centrality (from Feature 05)
- Git churn (from Feature 04)

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

If a component is unavailable for a given file (e.g. no complexity tool for that language, or the file has no Git history because it's untracked), that component is **excluded from the combination** and explicitly flagged as missing in the decomposition — never silently treated as zero. A file with fewer available components is marked as such (e.g. `components_available: 3/4`) so the report/MCP layer can surface that the score is based on partial data.

### Weights (Décidé Q65)

Weights are configurable, with defined defaults; this feature must accept a `HotspotWeights` config object rather than hard-coding weight constants inside the scoring function.

## Explicitly out of scope for this feature

- Adaptive/context-sensitive weighting (**Proposition Q66**, not decided) — fixed default weights only, no adaptive logic.
- Runtime-data component (**Proposition Q72**, P1, not decided) — do not add a fifth component; the score is explicitly four-component for MVP and must be structured so a fifth can be added later without reshaping the fact type.
- Any LLM-based "why is this a hotspot" narrative — the Capability Matrix marks that cell as LLM (P0), but it consumes this feature's decomposed facts; producing the narrative is part of a later synthesis feature, not this one.

## Acceptance criteria

- Complexity adapter implemented and contract-tested per Feature 02.
- Scoring function reads complexity/size/centrality/churn facts from the `FactStore` (no direct coupling to Features 04/05 internals beyond their fact output) and produces decomposed `hotspot_score` facts.
- Normalization is local-distribution-based and size is log-normalized; a test with one artificially huge, otherwise-unremarkable file confirms it does not dominate the ranking.
- A test with a file missing one component (e.g. no Git history) confirms that component is flagged absent, not treated as zero, and the combined score is computed from the remaining components.
- Weights are configurable via a passed-in config object, with a documented default.
- `uv run pytest` and `uv run ruff check .` pass.
