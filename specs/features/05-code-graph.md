# Feature 05 — Code graph

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework). **Part B** additionally depends on Feature 02b (MVP scope decision) being resolved.

## Goal

Extract the structural code graph (symbols, imports, calls, inheritance) via an existing graph tool, and compute the transverse graph metrics (centrality, communities, cycles) internally, per **Décidé Q51/Q52/Q56/Q57/Q59/Q62**. Splits cleanly along the "existing tool vs. internal computation" line the Product Brief draws for this whole category.

This feature is split into two parts, buildable independently:

- **Part A — `GraphProvider` interface + internal calculations.** Language-agnostic: the protocol, the multi-level aggregation, and the centrality/community/cycle computations all operate on whatever graph facts already exist in the `FactStore`, regardless of which language produced them. Buildable now.
- **Part B — Concrete `GraphProvider` implementation.** Requires a target language/tool chosen via Feature 02b. **Do not implement Part B until Feature 02b is resolved** — see the rule in [02b](02b-mvp-scope-decision.md). If you reach this spec before that's resolved, implement Part A in full (including its tests, using a hand-authored fixture set of graph facts rather than a real extracted graph — see Part A acceptance criteria), stop, and follow Feature 02b's instructions before touching Part B.

## Part A — `GraphProvider` interface + internal calculations (buildable now)

### `GraphProvider` interface (Décidé Q51, Q53, Q55)

Structural extraction (symbols, `imports`, `calls`, `inherits_from` — the standard relations from Feature 01, **Décidé Q56**) is never re-parsed in-house. It comes from a `GraphProvider` abstraction wrapping an existing graph/AST tool:

```python
class GraphProvider(Protocol):
    def extract(self, repository: Repository, scope: ScopeConfig) -> list[Fact]: ...
```

Each concrete provider translates its tool's native output into Feature 01's standard entity/relation facts (`provenance=observed`) — normalization is the provider's responsibility, not the consumer's (**Décidé Q55**). This part ships the protocol only; the one concrete provider Design Decisions §E calls for is Part B, gated by Feature 02b (which tool it wraps depends on which language(s) Feature 02b picks). Adding further providers later is Q183 (extensibility), not part of this feature either way.

### Multi-level graph (Décidé Q59)

The graph must be queryable at three levels: `system` (repositories/services), `module/directory`, `file/symbol`. This feature implements level-based aggregation over the raw file/symbol-level facts a provider returns — a `module` node is derived by grouping file nodes by directory, a `system` node by grouping repositories per `belongs_to` facts. No separate extraction pass per level; aggregation is computed from the same underlying facts. This aggregation logic only reads generic Feature 01 facts (`contains`, `belongs_to`) — it has no dependency on which `GraphProvider` produced them, so it's fully testable against hand-authored fixture facts without a real provider.

### Internal calculations (Décidé Q52, Q60–Q62)

Computed **after** extraction, over the graph facts already in the `FactStore`, using existing graph-algorithm libraries rather than hand-rolled algorithms:

- **Centrality** — degree centrality (in/out) as the baseline metric.
- **Communities** — standard community-detection algorithm (e.g. Louvain) over the module/file-level dependency graph.
- **Cycles** — standard cycle detection (e.g. Tarjan/SCC) over the dependency graph.

All three are `Fact(type=..., subject=<node>, value=..., provenance=computed)` — never LLM-derived (**Décidé Q99**: this whole category is explicitly reserved for deterministic/internal computation, not an LLM agent). Like the aggregation above, these calculations only consume standard Feature 01 relation facts (`depends_on`/`calls`/etc.) already in the store — they have no dependency on which language/provider produced those facts, so they are fully buildable and testable now using synthetic fixture graphs.

### Provenance distinction (Décidé Q57)

Extracted relations (`imports`, `calls`, etc.) are `provenance=observed`. Computed relations/metrics (centrality, community membership, cycle membership) are `provenance=computed`. This feature must not blur the two — a consumer (Hotspots, HTML report, MCP) relies on this distinction being correct at the source.

## Part B — Concrete `GraphProvider` implementation (gated on Feature 02b)

One concrete `GraphProvider` wrapping the graph/AST tool chosen in Feature 02b, via the Feature 02 adapter contract, for the language(s) chosen there. Its job is purely translation: native tool output → Feature 01 entity/relation facts. No new calculation logic belongs here — Part A's aggregation and centrality/community/cycle computations already consume whatever this provider produces, unchanged.

## Explicitly out of scope for this feature

- Boundary inference ("quels sont les boundaries probables" — marked 🟡/partially-LLM in the Capability Matrix, and **Décidé Q76/Q77** puts named-pattern interpretation in the later Architecture Interpretation feature) — this feature produces the observed/computed graph only, not architectural interpretation.
- Entrypoint detection beyond what the graph provider surfaces natively — framework-specific entrypoint heuristics are not decided in detail (Capability Matrix marks it 🟡) and are not built here.
- Query pagination/streaming for very large graphs (**Proposition Q58**, not decided) — this feature can assume in-memory computation is acceptable for MVP-sized inputs; do not build a streaming engine speculatively.
- A second `GraphProvider` implementation — extensibility mechanism only, no second provider required now.
- MCP-facing bounded graph queries — Feature "MCP server" (later), not this one.
- Part B before Feature 02b is resolved — see above.

## Acceptance criteria

### Part A

- `GraphProvider` protocol defined (no concrete implementation required for this part to be considered done).
- Module- and system-level nodes are derived by aggregation, demonstrated by a test that feeds hand-authored fixture facts (no real provider needed) and checks a file-level fact rolls up correctly to its module and system ancestors.
- Centrality, community, and cycle detection implemented via existing libraries, each emitting `provenance=computed` facts with correct evidence (referencing the underlying graph facts they were computed from), tested against hand-authored fixture graphs.
- A fixture graph with a known cycle (A→B→C→A) is correctly detected.
- `uv run pytest` and `uv run ruff check .` pass.

### Part B (only after Feature 02b is resolved)

- One concrete implementation of `GraphProvider` wrapping the tool chosen in Feature 02b via the Feature 02 adapter contract, with a fixture-based contract test.
- Extraction facts (`imports`/`calls`/`inherits_from`/`contains`) are `provenance=observed` with symbol-level evidence per Feature 01.
- Running Part A's aggregation and calculations against this provider's real output (on a small real fixture repository in the chosen language) produces the same shapes verified by Part A's synthetic-fixture tests — proving the two parts compose correctly.
- `uv run pytest` and `uv run ruff check .` pass.
