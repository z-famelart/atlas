# Feature 13 — CLI

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework). Wires in whichever of Features 03–12 are present at build time, but per its own scope rule below, must not assume all of them exist.

## Goal

Wire the pipeline into the command-line entry point, per **Décidé Q171, Q9, Q173–Q180**. This is the last feature in the ordered list because it's an integration layer over everything before it — but it deliberately does not require every prior feature to be complete (see below), so it can land and be exercised incrementally as Features 03–12 are added.

## Scope

### Command (Décidé Q171)

`project-intel analyze <scope>` as specified in the Product Brief §7 target workflow. This feature updates `pyproject.toml`'s `[project.scripts]` entry point from the bootstrap stub (`project_intel:main`) to a real CLI module (`project_intel.cli:main`), replacing — not layering on top of — the placeholder created in the bootstrap step.

### Layered configuration (Décidé Q173, Q9)

Auto-discovery is the default for anything detectable (all of Discovery, Feature 03); explicit configuration is required only for what can't be safely inferred: multi-repository/system scope, credentials, LLM budget. This feature implements the `Project` configuration file format referenced but deliberately left undefined by Features 03/09 (`ScopeConfig`, `HotspotWeights`, budget settings) — this is the feature that finally defines and loads that file, since it's the first point where a human actually needs to author one.

### Progress & error reporting (Décidé Q174, Q180)

Per-stage, per-adapter progress output (discovery → analyzers → normalization → calculations → LLM → report, per the Product Brief §7 pipeline), with a final summary of failed/skipped adapters and LLM sections — reusing the `AdapterResult`/`not_analyzed` status vocabulary from Features 01/02/07 directly, not a separate error model invented for the CLI.

### Partial/selective runs (Décidé Q175–Q177)

Sub-commands or flags to re-run a single analyzer, Git-only, or LLM-synthesis-only — all implemented as thin CLI wrappers around Feature 01's `FactStore.query_facts`/re-run capability (Décidé Q47: recomputable from persisted facts without re-scanning), not new pipeline logic.

### Fact inspection & adapter debugging (Décidé Q178, Q179)

`project-intel facts query [...]` for inspecting stored facts without generating a report; a `--debug`/`--verbose` flag surfacing an adapter's exact invocation and raw pre-normalization output (Feature 02 already captures this — this feature only exposes it).

### Graceful partial pipelines (consistent with Feature 11's not-analyzed rendering)

The CLI **must run successfully with only a subset of Features 03–12 present** — e.g. if only Discovery and Hotspots exist, `project-intel analyze` still produces a valid (partially not-analyzed) report rather than failing because Feature 08 isn't implemented yet. This is what makes "commit between each feature" a real incremental delivery model rather than a purely paper one: this CLI feature is deliberately not gated on every other feature already existing.

## Explicitly out of scope for this feature

- Incremental/diff-based analysis (**Proposition Q160**, not decided) — every `analyze` run is a full run within its configured scope/window.
- Any connector requiring credentials (section K) — the config format accommodates a credentials section per Q122/Q123 but this feature does not ship any credential-requiring connector.
- MCP server startup wiring beyond invoking Feature 12's server (packaging for a specific external coding agent) is a documentation/README concern, not new code in this feature.

## Acceptance criteria

- `project-intel analyze <path>` runs end-to-end against a real small fixture repository using whatever features are implemented at the time this feature lands, and produces an HTML report (Feature 11) without crashing even if some sections are `not_analyzed`.
- Configuration file loading implements `ScopeConfig` (consumed since Feature 03) and any other settings introduced as "deferred to configuration" by earlier features (`HotspotWeights` from Feature 06, budget settings from Feature 07), with sensible defaults so a bare `project-intel analyze .` works with zero config file.
- `project-intel analyze --only=git` (or equivalent) runs a single category of analyzer.
- `project-intel facts query` inspects a previous run's stored facts without re-running adapters.
- A run with a deliberately broken/missing external tool produces a summary listing it as skipped/failed, with exit code reflecting partial-success (not a hard failure) — consistent with Décidé Q30/Q180.
- `uv run pytest` and `uv run ruff check .` pass; `uv run project-intel analyze <fixture>` is exercised in at least one integration test.
