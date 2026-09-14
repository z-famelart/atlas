# Feature 13 — Full CLI

## Depends on

Feature 06b (Minimal CLI — the `project-intel` entry point, the `Stage`/`STAGE_REGISTRY` runner, and `project-intel facts query` already exist by this point; this feature extends that same CLI module, it does not replace it). Wires in whichever of Features 07–12 are present at build time, but per its own scope rule below, must not assume all of them exist.

## Goal

Turn the minimal walking-skeleton CLI from Feature 06b into the full human-facing entry point described in the Product Brief §7, per **Décidé Q171, Q9, Q173–Q180**. Everything Feature 06b already does (running registered stages, printing a status summary, `facts query`) stays as-is; this feature adds what a human actually needs to *use* the tool day to day: configuration, selective runs, debugging, and the LLM/report stages wired in end to end.

This is the CLI's **human-facing half** — see [12-mcp-server.md](12-mcp-server.md) for the symmetric AI-facing half. The two are independent entry points onto the same `FactStore`; neither wraps the other (see that spec's "CLI vs. MCP" note).

## Scope

### Layered configuration (Décidé Q173, Q9)

Auto-discovery is the default for anything detectable (all of Discovery, Feature 03); explicit configuration is required only for what can't be safely inferred: multi-repository/system scope, credentials, LLM budget. This feature implements the `Project` configuration file format referenced but deliberately left undefined by Features 03/06b/09 (`ScopeConfig` beyond 06b's built-in defaults, `HotspotWeights`, budget settings) — this is the feature that finally defines and loads that file, since it's the first point where a human actually needs to author one. Loading this file replaces 06b's built-in default `ScopeConfig`; it does not introduce a second, parallel scope mechanism.

### Multi-repository / `Project` scope (Décidé Q3, Q195)

06b's `analyze` takes a single repository path. This feature extends it to accept a `Project` configuration listing multiple repositories (per Décidé Q3/Q195), running the same `STAGE_REGISTRY` per repository and merging results into one `FactStore` — the stage-running mechanism itself is unchanged, only what it's invoked against.

### Extended progress & error reporting (Décidé Q174, Q180)

06b already prints a per-stage summary using the `AdapterResult`/status vocabulary. This feature extends that to cover the LLM stages (Features 07–10) once they exist, and adds the HTML report generation step (Feature 11) as a final pipeline step — same vocabulary, same failure-isolation rule, no new error model.

### Partial/selective runs (Décidé Q175–Q177)

Flags to run only a subset of `STAGE_REGISTRY` (e.g. `--only=git`) or only the LLM stages against already-persisted facts (Décidé Q47: recomputable without re-scanning) — implemented as a filter over the same registry 06b already iterates, not a second runner.

### Debugging (Décidé Q179)

A `--debug`/`--verbose` flag surfacing an adapter's exact invocation and raw pre-normalization output (Feature 02 already captures this — this feature only exposes it).

### LLM & report wiring (Décidé Q198, Q95, Q137)

Wires Features 07–11 into the pipeline: an `--llm`/`--no-llm` flag selecting a real `LLMProvider` vs. Feature 07's no-op provider (06b already threads `PipelineContext.llm_provider` through; this feature is what actually constructs a real one from configuration), and a final HTML report generation step (Feature 11) after all stages complete.

### MCP awareness, not MCP ownership

This feature may print the command to start the MCP server (Feature 12) as a convenience (e.g. `project-intel mcp` as a thin launcher), but does not embed MCP's request handling in the `analyze` pipeline — MCP is started, connects to a `FactStore`, and serves queries entirely independently of any `analyze` run in progress.

## Explicitly out of scope for this feature

- Incremental/diff-based analysis (**Proposition Q160**, not decided) — every `analyze` run is a full run within its configured scope/window.
- Any connector requiring credentials (section K) — the config format accommodates a credentials section per Q122/Q123 but this feature does not ship any credential-requiring connector.
- Reimplementing anything 06b already provides (stage execution, fact-count summary, `facts query`) — this feature only extends that module.

## Acceptance criteria

- `project-intel analyze <path>` (or `--config <project.toml>` for multi-repo) runs end-to-end against a real small fixture repository/project using whatever features are implemented at the time this feature lands, and produces an HTML report (Feature 11) without crashing even if some sections are `not_analyzed`.
- Configuration file loading implements the full `ScopeConfig`, `HotspotWeights` (Feature 06), and budget settings (Feature 07), with sensible defaults so a bare `project-intel analyze .` (no config file) still works exactly as it did under 06b.
- `project-intel analyze --only=git` (or equivalent) runs a single stage from `STAGE_REGISTRY` without executing the others.
- `--debug` surfaces an adapter's raw pre-normalization output.
- A run with a deliberately broken/missing external tool produces a summary listing it as skipped/failed, with exit code reflecting partial-success (not a hard failure) — consistent with Décidé Q30/Q180, unchanged from 06b's behavior.
- `uv run pytest` and `uv run ruff check .` pass; `uv run project-intel analyze <fixture>` is exercised in at least one integration test.
