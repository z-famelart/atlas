# Feature 05 — Code graph

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework).

## Goal

Extract the structural code graph (symbols, imports, calls, inheritance) via an existing graph tool, and compute the transverse graph metrics (centrality, communities, cycles) internally, per **Décidé Q51/Q52/Q56/Q57/Q59/Q62**. Splits cleanly along the "existing tool vs. internal computation" line the Product Brief draws for this whole category.

## Scope

### `GraphProvider` interface (Décidé Q51, Q53, Q55)

Structural extraction (symbols, `imports`, `calls`, `inherits_from` — the standard relations from Feature 01, **Décidé Q56**) is never re-parsed in-house. It comes from a `GraphProvider` abstraction wrapping an existing graph/AST tool:

```python
class GraphProvider(Protocol):
    def extract(self, repository: Repository, scope: ScopeConfig) -> list[Fact]: ...
```

Each concrete provider translates its tool's native output into Feature 01's standard entity/relation facts (`provenance=observed`) — normalization is the provider's responsibility, not the consumer's (**Décidé Q55**). This feature ships the interface plus **one** concrete provider (wrapping whatever graph tool is chosen as the MVP default — left as an implementation choice consistent with Design Decisions §E, not re-litigated here); adding further providers later is Q183 (extensibility), not part of this feature.

### Multi-level graph (Décidé Q59)

The graph must be queryable at three levels: `system` (repositories/services), `module/directory`, `file/symbol`. This feature implements level-based aggregation over the raw file/symbol-level facts the provider returns — a `module` node is derived by grouping file nodes by directory, a `system` node by grouping repositories per `belongs_to` facts. No separate extraction pass per level; aggregation is computed from the same underlying facts.

### Internal calculations (Décidé Q52, Q60–Q62)

Computed **after** extraction, over the graph facts already in the `FactStore`, using existing graph-algorithm libraries rather than hand-rolled algorithms:

- **Centrality** — degree centrality (in/out) as the baseline metric.
- **Communities** — standard community-detection algorithm (e.g. Louvain) over the module/file-level dependency graph.
- **Cycles** — standard cycle detection (e.g. Tarjan/SCC) over the dependency graph.

All three are `Fact(type=..., subject=<node>, value=..., provenance=computed)` — never LLM-derived (**Décidé Q99**: this whole category is explicitly reserved for deterministic/internal computation, not an LLM agent).

### Provenance distinction (Décidé Q57)

Extracted relations (`imports`, `calls`, etc.) are `provenance=observed`. Computed relations/metrics (centrality, community membership, cycle membership) are `provenance=computed`. This feature must not blur the two — a consumer (Hotspots, HTML report, MCP) relies on this distinction being correct at the source.

## Explicitly out of scope for this feature

- Boundary inference ("quels sont les boundaries probables" — marked 🟡/partially-LLM in the Capability Matrix, and **Décidé Q76/Q77** puts named-pattern interpretation in the later Architecture Interpretation feature) — this feature produces the observed/computed graph only, not architectural interpretation.
- Entrypoint detection beyond what the graph provider surfaces natively — framework-specific entrypoint heuristics are not decided in detail (Capability Matrix marks it 🟡) and are not built here.
- Query pagination/streaming for very large graphs (**Proposition Q58**, not decided) — this feature can assume in-memory computation is acceptable for MVP-sized inputs; do not build a streaming engine speculatively.
- A second `GraphProvider` implementation — extensibility mechanism only, no second provider required now.
- MCP-facing bounded graph queries — Feature “MCP server” (later), not this one.

## Acceptance criteria

- `GraphProvider` protocol defined; one concrete implementation wrapping a real external graph/AST tool via the Feature 02 adapter contract, with a fixture-based contract test.
- Extraction facts (`imports`/`calls`/`inherits_from`/`contains`) are `provenance=observed` with symbol-level evidence per Feature 01.
- Module- and system-level nodes are derived by aggregation, demonstrated by a test that checks a file-level fact rolls up correctly to its module and system ancestors.
- Centrality, community, and cycle detection implemented via existing libraries, each emitting `provenance=computed` facts with correct evidence (referencing the underlying graph facts they were computed from).
- A test fixture with a known cycle (A→B→C→A) is correctly detected.
- `uv run pytest` and `uv run ruff check .` pass.
