# Feature 12 — MCP server

## Depends on

Feature 01 (Facts & Evidence model). Like Feature 11, consumes whatever's in the `FactStore` without hard-coupling to a specific upstream feature.

## Goal

Expose the same knowledge as the HTML report to a coding agent via MCP, read-only, bounded, per **Décidé Q142–Q153**.

## Scope

### Read-only, always (Décidé Q153)

Every primitive in this feature is a read from the `FactStore`. No primitive in this feature mutates facts, triggers an adapter, or has any side effect — this is the entire MVP surface (Q154's "trigger new analysis" primitive is explicitly out of scope, see below).

### Primitives (Décidé Q141, Q145–Q151)

- `get_component(name_or_path)` — lookup.
- `get_dependencies(component)` / `get_dependents(component)` — direct graph neighborhood (Feature 05 facts).
- `find_workflow(query)` — search over domain-understanding workflow facts (Feature 09).
- `get_hotspots(top_n?, component?)` — decomposed hotspot facts (Feature 06), same decomposition guarantee as the HTML report (no separate "MCP view" of the score, same fact shape).
- `get_path(component_a, component_b)` — bounded shortest-path query over the graph (Feature 05), with a hard depth/step limit so it can't run unbounded on a huge graph.
- `where_to_start(component?)` — reuses the Onboarding Path feature's facts (Feature 10) when scoped to the whole repository/system; when scoped to a specific component (**Décidé Q151**), this feature applies the same underlying mechanism narrowed to facts related to that component rather than re-deriving a new synthesis.

### Facts, insights, and evidence exposed with provenance intact (Décidé Q142, Q143, Q144)

All three primitives above return facts as they're stored — `provenance`, `confidence`, and `evidence` are never stripped or flattened away for the MCP surface. An agent consuming `get_hotspots` must be able to tell a `computed` score from a `hypothesis` narrative exactly as a human reading the HTML report would (Décidé Q136's distinction is not an HTML-only concern).

### Bounding (Décidé Q152)

Every primitive has a default and maximum result limit (pagination or a hard cap, whichever is a better fit per primitive) — no primitive can return "everything." This is the direct MCP-facing implementation of the non-goal "agent qui explore aveuglément toute la codebase": the agent using this MCP server is bounded by construction, not by convention.

## Explicitly out of scope for this feature

- Triggering a new analysis on demand (**Proposition Q154**, P1, explicitly optional/consent-gated, not decided) — no write/trigger primitive in this feature.
- Any primitive not listed in Q145–Q151 — this feature does not speculatively add extra query shapes beyond what Design Decisions §M enumerates.
- Server transport/hosting details beyond implementing the MCP protocol itself (e.g. how it's packaged for a specific coding agent) — covered by the CLI feature's wiring, not this one.

## Acceptance criteria

- MCP server exposing exactly the primitives listed above, each backed by a `FactStore` query (no adapter invocation, no filesystem access beyond what's already in the store).
- Every primitive enforces a result limit; a test with a large synthetic fact set proves `get_hotspots`/`get_dependencies`/etc. never return more than their documented cap.
- A test proves `provenance`/`confidence`/`evidence` survive end-to-end through at least one primitive (e.g. `get_hotspots` returns the same decomposition shape Feature 06 produced, not a stripped-down summary).
- `get_path` has a documented, enforced max depth and returns a "no path within bound" result rather than searching unboundedly on a fixture graph deliberately constructed to be deep.
- No primitive mutates the `FactStore` — verified by a test that calls every primitive against a store snapshot and asserts the store is byte-identical afterward.
- `uv run pytest` and `uv run ruff check .` pass.
