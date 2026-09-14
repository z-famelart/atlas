# Feature 13 — Full CLI

## Depends on

Feature 06b (Minimal CLI — the `project-intel` entry point, the `Stage`/`STAGE_REGISTRY` runner, and `project-intel facts query` already exist by this point; this feature extends that same CLI module, it does not replace it). Wires in whichever of Features 07–12 are present at build time, but per its own scope rule below, must not assume all of them exist.

## Goal

Turn the minimal walking-skeleton CLI from Feature 06b into the full human-facing entry point described in the Product Brief §7, per **Décidé Q171, Q9, Q173–Q181**. Everything Feature 06b already does (running registered stages, printing a status summary, `facts query`) stays as-is; this feature adds what a human actually needs to *use* the tool day to day: configuration, selective runs, leveled logging with a live interactive progress display, interactive prompts for missing config, and the LLM/report stages wired in end to end. Introduces one new dependency, `rich`, for the live spinner/timer display (see "Live progress display" below) — `click` remains the command/argument-parsing framework, unchanged.

This is the CLI's **human-facing half** — see [12-mcp-server.md](12-mcp-server.md) for the symmetric AI-facing half. The two are independent entry points onto the same `FactStore`; neither wraps the other (see that spec's "CLI vs. MCP" note).

## Scope

### Layered configuration (Décidé Q173, Q9)

Auto-discovery is the default for anything detectable (all of Discovery, Feature 03); explicit configuration is required only for what can't be safely inferred: multi-repository/system scope, credentials, LLM budget. This feature implements the `Project` configuration file format referenced but deliberately left undefined by Features 03/06b/09 (`ScopeConfig` beyond 06b's built-in defaults, `HotspotWeights`, budget settings) — this is the feature that finally defines and loads that file, since it's the first point where a human actually needs to author one. Loading this file replaces 06b's built-in default `ScopeConfig`; it does not introduce a second, parallel scope mechanism.

### Multi-repository / `Project` scope (Décidé Q3, Q195)

06b's `analyze` takes a single repository path. This feature extends it to accept a `Project` configuration listing multiple repositories (per Décidé Q3/Q195), running the same `STAGE_REGISTRY` per repository and merging results into one `FactStore` — the stage-running mechanism itself is unchanged, only what it's invoked against.

### Extended progress & error reporting (Décidé Q174, Q180)

06b already prints a per-stage summary using the `AdapterResult`/status vocabulary. This feature extends that to cover the LLM stages (Features 07–10) once they exist, and adds the HTML report generation step (Feature 11) as a final pipeline step — same vocabulary, same failure-isolation rule, no new error model. At default verbosity, each stage now prints its status line as it happens (not only in the final summary), per Q174.

### Logging: configuration and rendering (Décidé Q170, Q179 — motivated by real dogfooding: `atlas analyze` on Atlas's own repository and on a larger project surfaced LLM failures with no usable detail)

Every feature that makes an external or LLM call already emits log records on its own logger, per the [README's logging convention](README.md#logging-a-convention-every-feature-follows) — that instrumentation is each feature's own job, not this one's (see the "Logging" subsection retroactively added to 02, 07, 07b, 08). **This feature owns exactly two things: configuring the root logger, and rendering what comes out of it.**

- **Configuration**: a `-v`/`--verbose` (repeatable) and `--log-level={WARNING,INFO,DEBUG}` flag on `analyze` (and any command that runs stages) sets the root logger's level — `WARNING` by default (no flag needed), `-v`/`INFO`, `-vv` or `--debug`/`--log-level=DEBUG`. `--debug` is kept as an alias for `-vv` for backward compatibility with anyone already using it. One handler, writing to stderr (stdout is reserved for the live progress display below and any piped/`--json` output), formatted as `<level> <logger name> <message>`.
- **Rendering**: at `WARNING` (default), a failure from *any* component — adapter, stage, or LLM call — surfaces as one readable line derived from that component's own log record (already containing provider/model/error per each feature's Logging subsection, e.g. Feature 07/07b's), not a bare `not_analyzed` with no detail. This is the concrete gap the dogfooding runs exposed (Q170): the fix is that every component already logs the detail per the README convention, and this feature is what a human actually sees it.

No raw potentially-sensitive payload is logged below `DEBUG` (Q170, enforced by each feature's own logging per the convention) — only shape/metadata (component, target, size, duration, error).

### Live progress display: per-stage spinner + elapsed timer (Décidé Q174)

At default verbosity and when stdout is a TTY, `analyze` renders a live, updating list — one line per stage in `STAGE_REGISTRY`, in order — built on [`rich`](https://github.com/Textualize/rich)'s `Progress`/`Live` (**new dependency** — spinners and in-place live-redraw aren't reasonably done with `click` or the stdlib alone; `rich` is the standard, focused choice for exactly this). Each stage's line:

1. Appears the moment the runner is about to call that `Stage`'s `.run(ctx)`, showing its name and a spinner.
2. While `.run()` is executing, the spinner animates and an elapsed-time counter next to it increments live (e.g. `⠋ architecture   0:07`) — this wraps the existing synchronous `stage.run(ctx)` call from a background-friendly renderer (`rich.live.Live` refreshing on a timer), it does not make stage execution itself concurrent or asynchronous; stages still run strictly in `STAGE_REGISTRY` order, one at a time, exactly as 06b already does.
3. On completion, the spinner is replaced with a status glyph (`✓`/`✗`/`⊘` for `ok`/`failed`/`skipped`) and the line freezes showing final elapsed time and fact count — same per-stage summary 06b already prints, now shown live instead of only at the end.

**Non-interactive fallback**: when stdout is not a TTY (CI, piped output, redirected to a file) or `--log-level`/`-v` raises verbosity above `WARNING` (interleaving a live-redrawn display with a scrolling log stream is unreadable), this feature falls back to 06b's original behavior — one plain line printed per stage as it starts and one when it finishes, no ANSI redraw, no spinner. This mirrors the same TTY-detection rule as Q181 below: rich/interactive presentation only when there's an interactive terminal to render it in.

### Interactive CLI for missing required configuration (Décidé Q181)

When a required value is missing (e.g. `--llm-provider ollama` without `--ollama-model`) and stdin is a TTY, prompt instead of failing outright — e.g. run `ollama list` and let the user pick from the installed models via `click.prompt`. When stdin is not a TTY (CI, scripts, pipes), no prompt: fail immediately with the same actionable message Feature 07b already specifies. Built entirely on `click`'s own prompt/confirm primitives — already a dependency, nothing new to add for this part (only the live progress display above needs `rich`).

### Partial/selective runs (Décidé Q175–Q177)

Flags to run only a subset of `STAGE_REGISTRY` (e.g. `--only=git`) or only the LLM stages against already-persisted facts (Décidé Q47: recomputable without re-scanning) — implemented as a filter over the same registry 06b already iterates, not a second runner.

### LLM & report wiring (Décidé Q198, Q95, Q137)

Wires Features 07–11 into the pipeline: an `--llm`/`--no-llm` flag selecting a real `LLMProvider` vs. Feature 07's no-op provider (06b already threads `PipelineContext.llm_provider` through; this feature is what actually constructs a real one from configuration), and a final HTML report generation step (Feature 11) after all stages complete.

### MCP awareness, not MCP ownership

This feature may print the command to start the MCP server (Feature 12) as a convenience (e.g. `project-intel mcp` as a thin launcher), but does not embed MCP's request handling in the `analyze` pipeline — MCP is started, connects to a `FactStore`, and serves queries entirely independently of any `analyze` run in progress.

## Explicitly out of scope for this feature

- Incremental/diff-based analysis (**Proposition Q160**, not decided) — every `analyze` run is a full run within its configured scope/window.
- Any connector requiring credentials (section K) — the config format accommodates a credentials section per Q122/Q123 but this feature does not ship any credential-requiring connector.
- Reimplementing anything 06b already provides (stage execution, fact-count summary, `facts query`) — this feature only extends that module.
- A structured/audit log file, log shipping, or any destination other than stderr — Q170 is resolved as human-readable leveled logging to the console only; a persisted audit trail (if ever wanted) is a separate, later concern.
- A general-purpose interactive wizard/`atlas configure` subcommand — Q181 only covers prompting for a specific missing value at the point `analyze` needs it, not a standalone configuration flow.
- Changing `LLMProvider`, `LLMCallResult`, `Stage`, `StageRunResult`, or any other already-shipped type (Features 02/06b/07/07b/08) — every logging call this feature relies on is an internal addition inside those features' own code (see the README's logging convention), not an interface change; this feature only configures the root logger and renders output, it does not add logging calls to other features' modules itself.
- Concurrent/parallel stage execution — the live spinner+timer display is a rendering concern only; `STAGE_REGISTRY` still runs strictly sequentially, exactly as 06b already does.
- Sub-stage progress (e.g. a spinner per adapter *within* a stage) — this feature's live display is one line per top-level registered `Stage`, not per adapter call inside it; that finer granularity is only visible via `-v`/`--debug` log lines, not the live display.

## Acceptance criteria

- `project-intel analyze <path>` (or `--config <project.toml>` for multi-repo) runs end-to-end against a real small fixture repository/project using whatever features are implemented at the time this feature lands, and produces an HTML report (Feature 11) without crashing even if some sections are `not_analyzed`.
- Configuration file loading implements the full `ScopeConfig`, `HotspotWeights` (Feature 06), and budget settings (Feature 07), with sensible defaults so a bare `project-intel analyze .` (no config file) still works exactly as it did under 06b.
- `project-intel analyze --only=git` (or equivalent) runs a single stage from `STAGE_REGISTRY` without executing the others.
- `-vv`/`--debug` surfaces an adapter's raw pre-normalization output.
- Default verbosity (no flag): a test with a mocked failing `LLMProvider` call proves the resulting console output contains `provider_id`, model, and the underlying error — sourced from Feature 07/07b's own `WARNING`-level log record, without needing `-v`/`--debug`.
- `-v` prints one line per stage transition and per external call (adapter/LLM), sourced from each feature's own `INFO` records via the root logger this feature configures; `-vv`/`--debug` additionally surfaces raw adapter output and the full LLM prompt/response (each feature's own `DEBUG` records); a test asserts each level's log output is a strict superset of the level below it.
- A test confirms this feature adds no `logger.<level>(...)` calls of its own inside Features 02/07/07b/08's modules (grep/import check) — it only sets the root logger's level/handler and reads what those features already emit, consistent with "Explicitly out of scope" above.
- A test with stdout mocked as a TTY runs `analyze` against a small fixture and proves: each `STAGE_REGISTRY` entry's line appears before its `Stage.run()` returns (not only after), shows an incrementing elapsed-time value while the (mocked, slow) stage executes, and ends with the correct status glyph, final duration, and fact count.
- A test with stdout not a TTY (or `-v`/`--debug` set) runs the same scenario and proves no ANSI/live-redraw escape codes appear — only 06b's original plain per-stage lines.
- A test simulating stdin as a TTY with `--llm-provider ollama` and no `--ollama-model` triggers an interactive prompt (mocked `ollama list` output); the same scenario with stdin not a TTY fails immediately with Feature 07b's existing actionable message, no prompt.
- A run with a deliberately broken/missing external tool produces a summary listing it as skipped/failed, with exit code reflecting partial-success (not a hard failure) — consistent with Décidé Q30/Q180, unchanged from 06b's behavior.
- `uv run pytest` and `uv run ruff check .` pass; `uv run project-intel analyze <fixture>` is exercised in at least one integration test.
