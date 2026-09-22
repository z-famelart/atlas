# Improvement ideas and known limitations

A prioritized backlog gathered while preparing Atlas for other users. Nothing here is
specified yet: per the project's workflow, an item becomes work by getting a feature spec in
[`specs/features/`](../specs/features/) (lettered, e.g. `12d`, when it extends a shipped
feature). Each item says what the problem is, what a fix could look like, and — for bugs —
how it was confirmed.

Priority: **P0** hurts every new user or produces wrong output · **P1** clear value, moderate
effort · **P2** worthwhile later.

---

## 1. First-run experience and adoption

### 1.1 One command to set up Claude Code — P0
**Problem.** Using Atlas from Claude Code takes four manual steps (register the MCP server,
allow-list its 8 tools, allow-list the agent's shell commands, install the agent). Skip the
allow-list and Claude Code asks for approval **once per tool** on first use — eight
interruptions before anything useful happens, which is the first impression colleagues get.
**Today's workaround.** [getting-started §5.2](getting-started.md#52-stop-the-per-tool-permission-prompts): add `mcp__atlas` to `permissions.allow`.
**Idea.** `atlas setup claude-code [--project]` that is idempotent and shows what it changes:
runs `claude mcp add --scope user atlas -- atlas mcp-serve`, merges the allow-list into
`~/.claude/settings.json` (or `.claude/settings.json`), symlinks the agent into
`~/.claude/agents/`. Complementary: annotate every MCP tool with `readOnlyHint: true` (MCP
tool annotations) so clients that honor it can treat them as safe. Longer term: ship
server + agent as a **Claude Code plugin** so installation is a single `/plugin install`.

### 1.2 `atlas doctor` — P0
**Problem.** Missing `tokei`/`graphify`, Ollama not running, model not pulled, MCP not
registered, a stale non-editable install: each one silently degrades the output, and you
only find out after a full run.
**Idea.** A `doctor` command that checks each prerequisite, prints ✓/✗ with the exact fix,
and warns when the installed `atlas` is not the checkout's code. `analyze` could run the
cheap checks up front and print one summary line.

### 1.3 Install without cloning — P1
**Problem.** Colleagues need mise + a clone just to use the tool.
**Idea.** `uv tool install git+ssh://git@github.com/z-famelart/atlas.git` works today and
could be the documented user path (clone remains the contributor path); later, publish to a
package index. Also consider bundling `graphifyy` as a dependency like `lizard`, leaving
`tokei` as the only external binary.

### 1.4 Stop cluttering directories — P1
**Problem.** Every run drops `atlas-report-<uuid>.html` (~3.5 MB) in the current directory
(dozens accumulate), and `.atlas-cache/` + `graphify-out/` in the analyzed repository,
which then show up in its `git status`.
**Idea.** Write reports to `<repo>/.atlas-cache/reports/` plus a stable `latest.html`,
add `--output` and `--open`; point graphify's output into `.atlas-cache/`; add both
directories to `.git/info/exclude` automatically (local, never committed).

### 1.5 Know which code the MCP server runs — P2
**Problem.** A long-running `atlas mcp-serve` keeps old code after an update; this already
caused hours of "fixed" bugs still showing.
**Idea.** Log version + git SHA at server start and include them in every response's
metadata (or an `atlas_info` tool), so a stale server is visible immediately.

---

## 2. Correctness bugs found during this review

### 2.1 Git renames create ghost files — fixed (Feature 04c)
**Was:** `git log --numstat` reports a rename as `src/{a.py => b.py}`; `git_analysis/churn.py` /
`cochange.py` took that string as a file path, creating a fake entity per rename and leaving the
pre-rename history on the old path (Design Decision Q112).
**Fixed** in [Feature 04c](../specs/features/04c-git-rename-paths.md): both notations are parsed
and, in the same newest-first `git log` pass, every older commit of a renamed file is attributed to
its newest path (co-change now reads `--name-status`). Not done: `--follow` per file (copies,
heuristic edge cases) — revisit only if a real history shows the single-pass map missing renames.

### 2.2 MCP answers "nothing" after a partial run — P0 — fixed by [Feature 12d](../specs/features/12d-mcp-type-scoped-runs-and-insights.md)
**Problem.** Every MCP query defaults to `FactStore.latest_run_id()` with no type filter.
After `atlas analyze --only architecture`, the latest run contains only architecture facts,
so `get_hotspots`, `get_component`, `where_to_start`… return empty results although the
store has them from the previous run. The HTML report does not have this problem (per-section
fallback, Feature 11c), and stages already use the right primitive
(`FactStore.run_id_with(type, preferred)`).
**Fix.** Use `run_id_with(<fact type>, run_id)` in `mcp_server/queries.py`.

### 2.3 Architecture and domain insights are not reachable over MCP — P0 — fixed by [Feature 12d](../specs/features/12d-mcp-type-scoped-runs-and-insights.md) (`get_insights`; a generic Q142 fact query is still open)
**Problem.** No MCP tool returns `architecture_hypothesis`, `business_concept` or
`glossary_term` facts: their subject is the repository, and `get_component` only matches
files; `find_workflow` covers workflows only. The `atlas-synthesis` agent is told to relay
the architecture pattern "if returned" — it never is. (Q143 requires insights to be exposed.)
**Fix.** A bounded `get_insights(repo_path, kind)` tool (architecture | concepts | glossary |
onboarding), or a generic `query_facts(repo_path, type, limit)` that also satisfies Q142.

### 2.4 Hotspot scoring mixes runs — P1
`hotspots/scorer.py` reads `complexity`, `language_detected`, `centrality` and `git_churn`
without a `run_id` filter, so on a store with many runs the latest value per file wins by
insertion order rather than by run. Scope each read with `run_id_with`.

### 2.5 No timeout on graphify — P2
CLI adapters have a 120 s timeout, but graphify is invoked by a Python callable with no
timeout; on a huge repository the run can hang silently.

---

## 3. Configuration that is parsed but not applied

| Setting | Status | Fix |
|---|---|---|
| `[hotspot_weights]` | read, never passed to the hotspots stage | put weights in `PipelineContext` (Q65) |
| `llm.budget_tokens` | read, stages use an unlimited budget | same, plus a per-pass split (Q101) |
| `[scope]` | applied by `discovery` only | apply to `git` (pathspec), `code_graph`, `hotspots` (Q9) |
| Git window | full history, no option | `--since` / `[git] since = "12 months"` (Q108) |
| Merge commits | always excluded, no option | `[git] include_merges` (Q113) |
| Claude model | Haiku 4.5 by default | document `--claude-model` for higher-quality interpretation |

---

## 4. Output quality

- **Ship Features 10c and 11e** (specified, not implemented yet): actionable "avoid initially" / "open questions" text; non-contradictory fallback prose and no wall of "unrecognized pattern" strings in the report. — P0
- **Secret scanning before any LLM call** (Q165): a deterministic scanner (e.g. `detect-secrets`/`gitleaks` patterns) on selected file contents, blocking inclusion with a logged reason. Required before recommending `--llm-provider claude-code` on client code. — P0
- **Architecture on small local models** is often "uncatalogued". Ideas: give the pass the community graph and directory-level dependency direction (not only file facts); two-step prompt (describe layers, then pick a pattern); recommend a minimum model size in the docs. — P1
- **Confidence visible at a glance** in the report (opacity/border, Q135) and graph filters by relation/provenance (Q134). — P2
- **Interactive code graph** (cytoscape.js or similar) for drill-down beyond the top-20 community view (Q129). — P2
- **Documentation drift**: compare architecture described in README/ADRs with the observed one (Q84). — P2

## 5. Scope

- **Multi-repository systems** (Q4): today each configured repository gets its own store and report; a `system` tag and a cross-repo view would honor "repository ≠ system". — P1
- **Infrastructure and CI/CD** (Q196): parse Dockerfiles, compose, K8s/Helm, Terraform and CI workflows into facts (the signatures already detect them). — P1
- **Runtime/observability connectors** (Q120/Q121) and an optional runtime component in the hotspot score (Q72). — P2
- **States and events** extraction in the domain pass (Q90/Q91). — P2

## 6. Performance

- **Run independent stages in parallel**: `discovery`, `git` and `code_graph` do not depend on each other. — P1
- **Incremental analysis** (Q160) and **adapter output cache** keyed on input hashes (Q159): re-analysis after a small change should take seconds. — P1
- **Measure**: record per-stage duration in `stage_run_result` so size/time targets (Q155/Q156) can be set from data. — P1

## 7. Validation

- **Golden corpus** (Q207): 3–5 open-source repositories with publicly documented architecture, plus one internal project with a reference engineer; store expected hotspots/entry points and score each release against them (Q201–Q206). — P1
- **Hallucination rate as a metric** (Q205): count citation-validation failures and retries per pass and surface them in `stage_run_result`. — P2
- **Collect feedback from colleagues' first uses** with a short fixed questionnaire: was the "where to start" right? which hotspot was noise? what was missing? — P0, cheapest item on this list.
