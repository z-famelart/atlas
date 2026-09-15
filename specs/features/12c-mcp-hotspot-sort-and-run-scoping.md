# Feature 12c — Fix `get_hotspots`' sort key; scope every MCP query to a single run

## Why this is a separate feature, not a rewrite of Feature 12/12b

Features 12 (MCP server) and 12b (global MCP server, `repo_path` per call) are **already implemented**. Per the [regeneration contract](README.md#regeneration-contract), this feature fixes a confirmed bug and adds scoping to `src/project_intel/mcp_server/queries.py`'s existing query functions — it does not change the MCP tool surface's names, or `create_server`'s overall shape from Feature 12b.

## What was actually found (grounding for this spec)

Reported directly by the `atlas-synthesis` agent (Feature 14) while using its own tool: `get_hotspots(top_n=10)` is documented as "sorted by combined_score" but returned facts in raw insertion order — it omitted a file at score `0.863` while including several files under `0.65`. Confirmed by reading the code: `queries.get_hotspots` sorts with `(f.value or {}).get("combined_score", 0.0)`, but the real `hotspot_score` fact shape (Feature 06, confirmed against real stored facts earlier this session) uses the key **`combined`**, not `combined_score`. Every fact silently sorts as `0.0`; Python's stable sort then leaves the original (insertion/creation) order untouched. Same bug class already fixed once in Feature 11c's HTML renderer — Feature 12's MCP server has its own, separate copy of the same mistake, never caught because 11c only touched `html_report/renderer.py`.

Investigating further (not reported by the agent, found while reading `queries.py` in full): **no query function in Feature 12/12b takes or applies a `run_id` filter.** Every one of `get_component`, `get_dependencies`, `get_dependents`, `find_workflow`, `get_hotspots`, `get_path`, and `where_to_start` queries `store.query_facts(...)` across the store's **entire history** — every `atlas analyze` run this repository has ever had, all mixed together. This repo alone has ~9 accumulated runs. Two concrete consequences, not just a theoretical concern:

1. For facts that change over time (`hotspot_score`, `centrality`), results can mix values computed at different points in history, with no way to tell which figure came from which run.
2. For facts that don't change when the code hasn't (`imports`/`calls`/`symbol_defined`), every historical run still produces its **own** `Fact` row (IDs are seeded from `run_id`, per Feature 01), so an unscoped query returns near-duplicate rows — the same relation repeated once per historical run. This quietly defeats the `limit`/`top_n` caps Feature 12 already decided are mandatory (Décidé Q152: bounded, not unlimited) — a `limit=20` call can return 20 duplicates of a handful of real relations instead of 20 distinct ones.

## Depends on

Feature 12/12b (MCP server, already implemented — this changes `queries.py`'s function bodies and adds one small parameter to each, not the MCP tool names or `create_server`'s per-call `repo_path` mechanism). Feature 01 (`FactStore`, already implemented — this feature adds one new, purely additive read-only method, `latest_run_id()`, used by the fix below).

## Scope

### Fix `get_hotspots`' sort key (bug fix)

`facts.sort(key=lambda f: (f.value or {}).get("combined_score", 0.0), reverse=True)` → `.get("combined", 0.0)`, matching the real `hotspot_score` shape. No other change to this function's signature or the "sorted by X descending" contract already documented.

### `FactStore.latest_run_id()` (new, small, additive method on Feature 01)

```python
def latest_run_id(self) -> str | None:
    """The run_id of the most recently created fact in this store, or None if empty."""
```

Implemented as a direct, indexed SQL query (`ORDER BY created_at DESC LIMIT 1`, reusing the same `created_at` ordering `query_facts` already relies on) — not a full table scan/load of every fact into memory, which would be the wrong approach given stores in this project routinely hold tens of thousands of facts across many runs. This is the only store-level change in this feature; `query_facts`'s existing signature and behavior are untouched.

### Scope every query function to a single run, defaulting to the latest

Each function in `queries.py` (`get_component`, `get_dependencies`, `get_dependents`, `find_workflow`, `get_hotspots`, `get_path`, `where_to_start`) gains an optional `run_id: str | None = None` parameter. When `None` (the default), the function resolves it via `store.latest_run_id()` once and filters its own `query_facts(...)` calls to that run — using the same `run_id=` filter `query_facts` already supports (Feature 01, unchanged). When a caller passes an explicit `run_id`, that exact run is used instead (e.g. for inspecting a specific historical analysis) — this is not removing capability, it's changing the *default* from "everything, unscoped" to "the most recent run, unless told otherwise."

Each MCP tool wrapper in `server.py` (Feature 12b) gains the same optional `run_id: str | None = None` parameter, passed straight through to its `queries.py` counterpart, and documented in the tool's `description` string (e.g. *"...for the most recent analyze run, or a specific run_id if given."*).

`where_to_start`'s internal call to `get_hotspots` and its own `centrality` query both use the same resolved `run_id`, not two independently-resolved values that could disagree.

## Explicitly out of scope for this feature

- Any change to the MCP tool names, `repo_path`-per-call mechanism, or `create_server`'s overall shape (Feature 12b) — this only adds one optional parameter per tool.
- Any change to `query_facts`'s existing signature/behavior — `latest_run_id()` is a new, separate method.
- Cross-run comparison/history primitives (e.g. "show me how this hotspot changed over time") — out of scope; this feature only fixes "which single run's facts are returned by default," not multi-run analytics.
- A broader audit of other field-mapping mismatches beyond `get_hotspots`' confirmed `combined_score`/`combined` bug — tracked and fixed separately as findings come in, not bundled into this feature's fixed scope.

## Acceptance criteria

- A fixture `FactStore` with `hotspot_score` facts of known, distinct `combined` values proves `get_hotspots` returns them in true descending order — not insertion order.
- `FactStore.latest_run_id()` returns the `run_id` of the fact with the greatest `created_at` in a fixture store with facts from multiple runs; returns `None` for an empty store.
- A fixture store with the same file's `hotspot_score`/`imports` facts recorded under two different `run_id`s (simulating two historical `analyze` runs) proves every query function defaults to returning only the latest run's facts, with no duplicate/stale-run rows — and that passing an explicit `run_id` returns that specific run's facts instead.
- `where_to_start`'s fallback path (no `onboarding_path` facts) uses one consistently-resolved `run_id` for both its internal hotspots and centrality lookups — a test with multi-run fixture data proves they don't silently disagree.
- `uv run pytest` and `uv run ruff check .` pass.
