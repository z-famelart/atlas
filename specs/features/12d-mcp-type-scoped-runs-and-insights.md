# Feature 12d — Type-scoped run resolution for MCP queries; expose repository-level insights

## Why this is a separate feature, not a rewrite of Feature 12/12b/12c

Features 12 (MCP server), 12b (global server, `repo_path` per call) and 12c (hotspot sort key, run scoping) are **already implemented**. Per the [regeneration contract](README.md#regeneration-contract), this feature changes how `src/project_intel/mcp_server/queries.py` resolves its *default* run, and adds **one** read-only tool. Existing tool names, parameters and `create_server`'s per-call `repo_path` mechanism are unchanged.

## What was actually found (grounding for this spec)

Both problems are documented in `docs/improvement-ideas.md` §2.2 and §2.3.

1. **A partial run hides everything else (§2.2).** Feature 12c made every query default to `store.latest_run_id()` — the run of the most recently created fact of *any* type. `atlas analyze --only architecture` creates a run holding only `architecture_hypothesis` (+ `stage_run_result`) facts, so afterwards `get_hotspots`, `get_component`, `get_dependencies`, `where_to_start`… all return empty although the store still holds those facts from the previous full run. The pipeline stages (Features 09b/10) and the HTML report (Feature 11c) already avoid this with `FactStore.run_id_with(type, preferred)`: "the latest run that actually holds this fact type". The MCP server was the only consumer still resolving the run without a type.
2. **Architecture and domain insights are unreachable (§2.3).** `architecture_hypothesis`, `business_concept` and `glossary_term` facts have the **repository** as subject. `get_component` only matches `FILE` subjects, `find_workflow` only reads `business_workflow`, `where_to_start` only `onboarding_path`. No tool returns them — contrary to Q143 (insights exposed with provenance/confidence intact). The `atlas-synthesis` agent (Feature 14) is told to relay the architecture pattern "if returned"; it never is.

## Depends on

Features 12/12b/12c (MCP server, implemented). Feature 01 (`FactStore`: `latest_run_id(type)`, `run_id_with(type, preferred)` already exist; this feature adds one small read-only method, below). Features 08/09 (producers of the insight facts, implemented).

## Scope

### Type-scoped default run (fixes §2.2)

A private helper in `queries.py`:

```python
def _run(store, fact_type, run_id):
    return run_id if run_id is not None else store.run_id_with(fact_type, None)
```

Each query resolves its default run from the fact type it actually reads:

| Query | Fact type used to resolve the run |
|---|---|
| `get_dependencies`, `get_dependents`, `get_path` | `imports` (code-graph stage; `calls` comes from the same run) |
| `find_workflow` | `business_workflow` |
| `get_hotspots` | `hotspot_score` |
| `where_to_start` | `onboarding_path`; its fallback resolves `hotspot_score` and `centrality` each by type |
| `get_component` | **per fact type** — see below |

**An explicit `run_id` stays exact** (12c's contract): passing `run_id` returns that run's facts or nothing, never a silent substitute from another run. `run_id_with`'s "fall back when the preferred run lacks the type" behavior is right for a stage consuming upstream facts, but an MCP caller who names a run is asking about that run.

`where_to_start`'s fallback previously shared one resolved run between hotspots and centrality (12c). With type scoping each resolves independently; in a full run both come from the same run anyway, and after `--only hotspots` centrality correctly comes from the last code-graph run instead of disappearing.

`get_component` returns facts of many types (discovery, git, complexity, graph, hotspots) about one file, so no single type can pick its run. Default behavior: every fact about the matched file is kept only if its `run_id` equals `latest_run_id(type=fact.type)` — one fact set per type, each from the latest run that produced that type. No duplicates across historical runs (12c's concern), no loss after a partial run.

### `FactStore.find_subject_id(subject_type, name_or_path, run_id=None)` (new, additive, Feature 01)

`get_component` used to load **every** fact of the resolved run into memory to find a matching file id. With per-type resolution there is no single run to scan, and scanning the whole history is the full-table load 12c ruled out. The new method does the match in SQL: case-insensitive exact match or `/<name_or_path>` suffix match (via `substr`, not `LIKE`, so `_`/`%` in file names are literal), optionally restricted to a run, exact match first then alphabetical. `query_facts` is untouched.

### New tool: `get_insights(repo_path, kind, limit=10, run_id=None)` (fixes §2.3)

Read-only, bounded, same shape as the existing tools.

- `kind` ∈ `architecture` → `architecture_hypothesis`, `concepts` → `business_concept`, `glossary` → `glossary_term`. An unknown kind returns `{"error": "unknown kind ...; expected one of [...]"}` rather than an empty list — an empty list must keep meaning "no such facts were produced".
- Results sorted by `confidence` descending; `limit` hard-capped at **50** (Q152: bounded, never a dump).
- Default run: `_run(store, <fact type>, run_id)` — after `--only architecture`, `kind="concepts"` still returns the concepts of the last domain run.
- Each fact is returned with the same `_fact_to_dict` serialization as every other tool: `provenance` (`hypothesis`), `confidence`, `run_id`, `value` (including `fact_ids` citations) intact — Q143's requirement that a consumer can distinguish fact from hypothesis.

`workflows` and `onboarding` are **not** kinds: `find_workflow` and `where_to_start` already expose them; a second path to the same facts would be two contracts to keep in sync.

### Agent definition (Feature 14)

`.claude/agents/atlas-synthesis.md`'s MCP query sequence gains `get_insights(kind="architecture")` and `get_insights(kind="concepts")` (plus `glossary` when useful), so "Architecture pattern + confidence" and "Domain concepts identified" are fed by a real call instead of "if returned".

## Explicitly out of scope

- **Q142, generic filtered raw-fact query** (`query_facts(repo_path, type, subject, limit)`). `get_insights` covers Q143 only; Q142 stays not implemented and keeps its own status note. A generic query would also have to decide pagination and evidence shape (Q144) — a separate spec.
- Exposing evidence rows (Q144) — facts are returned with the evidence already embedded by `_fact_to_dict`, no new evidence primitive.
- `module`/`symbol`-level MCP queries (Q145/Q147) — file level only, as today.
- Changing the HTML report's fallback logic (Feature 11c), or the stages' use of `run_id_with`.
- Cross-run history/comparison — still out of scope, as in 12c.

## Acceptance criteria

- A fixture store with a full run followed by a later architecture-only run proves `get_hotspots`, `get_dependencies`, `get_dependents`, `get_path`, `where_to_start` (fallback) and `get_component` all still return the full run's facts.
- `get_component` with facts of one type in two runs returns only the latest run's facts for that type while keeping other types from the older run; with an explicit `run_id` it returns only that run's facts, or `None` if the file has no facts in it.
- `find_subject_id`: exact match wins over a suffix match; matching is case-insensitive; `_` is not a wildcard; subject type is respected.
- `get_insights`: `architecture` returns the latest architecture run's hypotheses sorted by confidence; `concepts` falls back to the run that holds concepts; an explicit `run_id` is exact; `limit` is capped at 50; an unknown kind raises `ValueError` in `queries` and returns an error JSON from the tool.
- `create_server()` lists 8 tools, including `get_insights`.
- Existing 12/12b/12c tests pass unchanged except the tool-count assertion.
- `uv run pytest` and `uv run ruff check .` pass.
