# Feature 12b — Global MCP server

## Why this is a separate feature, not a rewrite of Feature 12

Feature 12 (MCP server) is **already implemented** — `atlas mcp-serve <db_path>` starts a
stdio server scoped to one fixed database. Per the
[regeneration contract](README.md#regeneration-contract), its spec and interface are a stable
record of what shipped.

The problem this feature solves is operational: requiring a separate `atlas mcp-serve` invocation
per project — each with its own hard-coded `db_path` — means every project needs its own MCP
entry in every Claude Code config file. That is error-prone and defeats the purpose of a shared
tool. The root cause is that the `db_path` is a **startup argument** (bound once at launch) rather
than a **per-call argument** (bound per query). This feature fixes that.

## Depends on

Feature 12 (MCP server — already implemented, this feature changes its calling convention only).
Feature 13 (Full CLI — already implemented, provides `atlas mcp-serve` as the entry point).

## Goal

Register `atlas mcp-serve` **once**, globally, with no arguments. Each tool call carries the
target `repo_path`; the server derives `<repo_path>/.atlas-cache/facts.sqlite`, opens the
connection, answers the query, and closes it. One server handles every analyzed repository on
the machine, with zero per-project configuration.

## Scope

### `repo_path` becomes a per-call parameter on every primitive

Every MCP tool gains a required `repo_path: str` parameter as its **first** argument.
The server derives the database path as `Path(repo_path) / ".atlas-cache" / "facts.sqlite"` —
the same fixed derivation `atlas analyze` uses. It never accepts an explicit `db_path` from the
caller; the derivation is the only path logic the server knows.

The seven primitives after this change:

```
get_component(repo_path, name_or_path)
get_dependencies(repo_path, component, limit=20)
get_dependents(repo_path, component, limit=20)
find_workflow(repo_path, query, limit=10)
get_hotspots(repo_path, top_n=10, component=None)
get_path(repo_path, component_a, component_b, max_depth=5)
where_to_start(repo_path, component=None)
```

All other parameters, caps, provenance rules, and bounding behaviour from Feature 12 are
unchanged — this is a calling-convention change only.

### Connection per call (no shared state between calls)

Each tool call opens its own `FactStore` connection (`with FactStore(...) as store: ...`),
executes the query, and closes it. No store is held open between calls. This is safe for
a read-only server and lets the server serve requests against different repositories without
any state leaking between them.

If `<repo_path>/.atlas-cache/facts.sqlite` does not exist at call time, the tool returns a
structured error JSON:

```json
{"error": "no facts store found", "expected_path": "<repo_path>/.atlas-cache/facts.sqlite",
 "hint": "run `atlas analyze <repo_path>` first"}
```

It does not crash the server — the server process stays up for subsequent calls.

### `atlas mcp-serve` takes no argument

`atlas mcp-serve` loses its `[DB_PATH]` positional argument. It starts the server over stdio
and that's it. The `--port` option (reserved, unused) is kept for future SSE transport.

### Global registration in Claude Code

With no `[DB_PATH]` argument, the server is safe to register once in `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "atlas": {
      "command": "atlas",
      "args": ["mcp-serve"]
    }
  }
}
```

No per-project `.mcp.json` is needed. The `repo_path` is passed by the agent on every call,
so the server is naturally multi-tenant.

### `create_server` and `run_server` internal signatures

`create_server()` and `run_server()` lose their `db_path` argument; `create_server` now takes
no arguments. The public module-level API (`__init__.py` exports) is updated accordingly.

## Explicitly out of scope

- Fixing the underlying `db_path` default-value inconsistency in the already-shipped `mcp-serve`
  CLI argument (Feature 12/13) — that mismatch is irrelevant once `mcp-serve` takes no argument.
- Pooling or caching open `FactStore` connections across calls (a future optimisation if latency
  proves measurable — `ponytail: per-call open/close, connection pool if benchmarks show overhead`).
- SSE transport, authentication, or any new MCP primitive — all out of scope, same as Feature 12.
- Triggering analysis (**Proposition Q154**, still not decided).

## Acceptance criteria

- `atlas mcp-serve` starts with no arguments and prints a ready message.
- Calling `get_hotspots(repo_path="/some/repo", top_n=5)` against the running server
  returns results from `/some/repo/.atlas-cache/facts.sqlite` (verified by a test with two
  separate in-memory-or-temp stores at two different fake repo paths, called in the same server
  session — results must differ and each must match the correct store).
- Calling any primitive against a `repo_path` with no `.atlas-cache/facts.sqlite` returns the
  structured error JSON above, and the server continues to handle subsequent calls normally.
- All seven primitives preserve their caps, bounding, and provenance-survival behaviour from
  Feature 12 — the acceptance criteria from Feature 12's spec are all still satisfied.
- `uv run pytest` and `uv run ruff check .` pass.
