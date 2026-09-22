# Feature 12e — MCP: system-scoped query

## Depends on

Feature 12 (MCP server — tool registration pattern, `_open_store`/`_missing` helpers in `src/project_intel/mcp_server/server.py`, already implemented). [Feature 13b](13b-multi-repo-system-orchestration.md) (produces the system store this feature reads — must land first).

## Naming note

Named `12e`, not `12d`, for historical reasons: `12d` (`get_insights` + type-scoped run resolution) was implemented on commit `71482db` on a separate branch (`claude/kind-hamilton-21c237`) before this feature was written, and was merged into `main` (fast-forward, no conflicts) as part of landing this feature — so by the time this feature is implemented, `12d` is real and current on `main`, not stranded. `12e` still avoids renumbering it after the fact.

## Goal

Expose [Feature 13b](13b-multi-repo-system-orchestration.md)'s system store over MCP, the same way Feature 12 exposes each repository's own store — so an agent (in particular an extended `atlas-synthesis` recipe, per Feature 14) can ask "what does this system contain" instead of reading the SQLite file directly. No new fact production, no new fact type — a pure read path onto Feature 13b's output, same spirit as Feature 12 itself ("read-only, per Q141–153").

## Scope

### One new tool: `get_system`

Signature mirrors the existing tools' shape (`repo_path` parameter pattern in `server.py`, `_fact_to_dict` response shape in `queries.py`):

```python
def get_system(project_root: str, system_name: str) -> dict[str, Any]:
    ...
```

- Opens `<project_root>/.atlas-cache/system-<system_name>.sqlite` (the exact path Feature 13b writes to — derived the same way `_db_path(repo_path)` already derives the per-repository path, just at Project granularity).
- If the store doesn't exist: return the same `not_analyzed`-shaped response `_missing(repo_path)` already returns for a missing per-repository store (reuse that helper's response shape, parameterized by what's missing) — never a crash, never a silent empty success.
- If it exists: return the `System` entity, the member `Repository` entities (id + `path` attribute), and every `belongs_to` fact with its full evidence/provenance/confidence — via `_fact_to_dict`, unchanged, exactly as every other tool already relays facts.

### Registration

One `@mcp.tool(...)` block in `create_server()` (`server.py`), following the exact structure of the other seven tools already registered there — no new registration mechanism.

## Explicitly out of scope for this feature

- Any new fact type, any change to `queries.py`'s existing seven functions, any change to Feature 13b's store format.
- Fanning a query out across every member repository's own store in one call (e.g. "give me hotspots for every repo in this system in one shot") — this feature only exposes the system-level membership/relation facts themselves; an agent that wants per-repository detail still calls the existing per-repository tools (`get_hotspots`, etc.) once per member, exactly as the `atlas-synthesis` recipe is extended to do.
- Any change to how `atlas mcp-serve` is started or registered (Feature 12b) — this is a new tool on the same already-running server, not a new server process.

## Acceptance criteria

- `get_system(project_root=<dir>, system_name="myapp")` against a store Feature 13b produced returns the `System` entity, all member `Repository` entities, and all `belongs_to` facts with intact evidence/provenance/confidence — verified against a fixture store built by Feature 13b's own test fixtures (no duplicated fixture-building logic).
- `get_system` against a `project_root`/`system_name` with no matching store returns the same not-analyzed response shape as the existing per-repository tools' missing-store case (verified by comparing response shape/keys, not exact message text).
- `uv run pytest` and `uv run ruff check .` pass.
