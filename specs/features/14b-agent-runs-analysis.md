# Feature 14b — Agent runs `analyze` itself

## Why this is a separate feature, not a rewrite of Feature 14

Feature 14 (agent-driven synthesis via MCP) is **already implemented** — `.claude/agents/atlas-synthesis.md` and `examples/atlas-synthesis-example.html` are shipped. Per the [regeneration contract](README.md#regeneration-contract), its spec and its agent definition are a stable record of what shipped; this feature changes one explicit, documented behavior (the agent refuses to run analysis itself) additively, per direct user feedback, rather than rewriting Feature 14's file from scratch.

The shipped agent definition currently says, verbatim, under "Prerequisites": *"`atlas analyze <repo_path>` has already run... This agent does **not** trigger analysis itself."* The user has to run `atlas analyze` by hand before every synthesis. That's the friction this feature removes.

## Depends on

Feature 14 (agent-driven synthesis — already implemented, this feature changes its "Prerequisites" section only). Feature 13 (Full CLI — already implemented, provides the `atlas analyze` and `atlas mcp-serve` commands this feature's agent now chains together itself).

## Goal

The `atlas-synthesis` agent should be usable as a single self-serve step: point it at a repository, and it runs whatever's missing itself — analysis, then the MCP server, then the synthesis — instead of requiring the human to run `atlas analyze` by hand first.

## Scope

### Agent runs `analyze` when needed (replaces Feature 14's "Prerequisites" §1/§3)

The agent's prerequisites become:

1. Given a repository path, the agent checks whether a facts store already exists at that repository's fixed analysis output location (`<repo_path>/.atlas-cache/facts.sqlite` — the only location `atlas analyze` writes to; it has no `--output`/`--db-path` flag today, so this path is fully derivable from `repo_path` alone, not guessed).
2. If it does not exist (first run), or the user asked for a fresh analysis, the agent runs `atlas analyze <repo_path>` itself (as a subprocess/tool call, exactly as a human would from the CLI — same flags available: `--llm-provider`, `--ollama-model`, `--no-llm`, etc., passed through if the user specified any), and waits for it to complete before continuing. A failed/partial `analyze` run (some stages `not_analyzed`) is not a reason to stop — Feature 06b/13's own failure-isolation behavior already handles that; the agent proceeds with whatever facts exist, same as it already does for individual `not_analyzed` MCP results.
3. The agent then starts `atlas mcp-serve <same repo_path>/.atlas-cache/facts.sqlite` — **always passing this exact, explicitly-derived path**, never relying on `mcp-serve`'s own CLI default (`.atlas/facts.sqlite`, per its `db_path` argument's default value) or any other guessed location. This sidesteps a real inconsistency in the shipped CLI (`analyze` writes to `.atlas-cache/facts.sqlite`; `mcp-serve`'s own default argument points at `.atlas/facts.sqlite`; the previous Feature 14 agent definition's prose even mentioned a third path, `.atlas/facts.db`) without requiring a code change to Feature 12/13's already-shipped default flag values — the agent simply never depends on either default, it always computes and passes the path itself.
4. Only then does it proceed with the existing MCP query sequence and synthesis (Feature 14, unchanged).

### Re-analysis is opt-in, not automatic on every run (avoids surprise cost)

If a facts store already exists for the target repository, the agent does **not** silently re-run analysis (which can be slow and makes real LLM calls) — it uses what's there, same as today. Re-running analysis happens only when: no facts store exists yet, or the user explicitly asks for a fresh run (e.g. "re-analyze and then synthesize"). This mirrors the same "no hidden trigger of LLM/compute cost" reasoning already decided for the MCP server itself (Décidé Q154, still not applicable here since this is the agent's own CLI orchestration, not a new MCP primitive — see "Explicitly out of scope").

## Explicitly out of scope for this feature

- Any new MCP tool/primitive to trigger analysis (**Proposition Q154**, still not decided) — this feature does not touch Feature 12 at all. The agent runs `atlas analyze` as a plain CLI subprocess/tool call, outside of MCP entirely; Feature 12's MCP server remains exactly as shipped, read-only, with no "trigger a run" tool.
- Fixing the underlying default-path inconsistency between `atlas analyze` and `atlas mcp-serve`'s own CLI defaults — this feature works around it by never relying on either default, but the mismatch itself (a real bug in already-shipped Feature 12/13 code) is a separate, smaller fix left for whoever touches that code next; noting it here so it isn't lost.
- Incremental/diff-based re-analysis (**Proposition Q160**, not decided) — "fresh analysis" here always means a full `atlas analyze` run, same as everywhere else in this project.
- Changing Feature 14's MCP query sequence, provenance rules, two-layer output shape, or HTML conventions — all unchanged; this feature only touches what happens *before* the agent starts querying MCP.

## Acceptance criteria

- Run the agent against a repository with no `.atlas-cache/facts.sqlite` present: it runs `atlas analyze` itself (observable via its own tool-call log), then starts `mcp-serve` against the exact path it just produced, then completes the synthesis — no manual `atlas analyze` step by the user.
- Run the agent again immediately against the same repository: it does not re-run `atlas analyze` (no LLM calls made a second time for the same facts) — it goes straight to starting `mcp-serve` and querying.
- The agent definition's own text no longer contains the line "This agent does not trigger analysis itself" or equivalent — it's updated to describe the new self-serve behavior.
- A test/worked example proves the agent never passes a bare/default path to `mcp-serve` — the path argument in its `mcp-serve` invocation is always the one it derived from the repository path (grep the agent's own logged tool calls, or an integration test asserting the invocation's argument).
