# Feature 06b — Minimal CLI (walking skeleton)

## What this is

Not the CLI described in the Product Brief §7 (that's Feature 13, "the full CLI"). This is a deliberately small runner whose only job is to make **every feature that has already landed, or lands from now on, immediately runnable and testable against a real project** — without waiting for Feature 13, which needs the config file format, selective re-runs, debug tooling, and full LLM wiring to be meaningful.

It exists because, without it, there is no way to run any of Features 01–05B end-to-end today even though they're implemented — `uv run project-intel` does nothing. Waiting until Feature 13 (after the entire LLM/report/MCP stack, Features 07–12) to get a runnable entry point means the deterministic half of the pipeline goes untested as a whole for a long time. This feature closes that gap now.

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework). **Does not depend on Feature 06 (Hotspots)** or anything after it — it must work today against whatever subset of Features 03/04/05 is present (all of them, per `git log`, at the time this spec is written), and pick up Feature 06 and later stages automatically once they land, with zero changes to this feature's own code. This is the point: incremental testability, not a fixed dependency on "the whole pipeline so far."

## Goal

Provide `project-intel analyze <path>` in a minimal form — run every registered analysis stage against a real repository, store the resulting facts, print a per-stage status summary — plus `project-intel facts query` to inspect what was stored. No config file, no LLM, no HTML report: those are Feature 13's job.

## Scope

### Command entry point (Décidé Q171, pulled forward from Feature 13)

`project-intel analyze <path>` and `project-intel facts query [...]` as real, working commands — this feature updates `pyproject.toml`'s `[project.scripts]` entry point from the bootstrap stub (`project_intel:main`) to a real CLI module (`project_intel.cli:main`), replacing the placeholder created in the bootstrap step. Feature 13 (the full CLI) extends this same module with more subcommands/flags later; it does not re-point the entry point again.

### The `Stage` contract (new — this is what "automatic entry point registration" means)

Every feature that produces facts as an analysis step (03, 04, 05, 06, and later 08/09/10) exposes one module-level object conforming to:

```python
class Stage(Protocol):
    name: str                                    # e.g. "discovery", "git", "code_graph", "hotspots"
    def run(self, ctx: PipelineContext) -> StageRunResult: ...
```

```python
@dataclass(frozen=True, slots=True)
class PipelineContext:
    store: FactStore
    repository_path: Path
    run_id: str
    scope: ScopeConfig          # built-in defaults only at this stage, see below
    llm_provider: LLMProvider | None = None   # None until Feature 07 lands; a Stage that needs one degrades per its own spec

@dataclass(frozen=True, slots=True)
class StageRunResult:
    name: str
    status: Literal["ok", "skipped", "failed"]   # same vocabulary as Feature 02's AdapterResult / Feature 01's status enum
    facts_produced: int
    detail: str | None = None                     # error message, or skip reason
```

A `Stage.run` is responsible for calling whatever adapters/calculations its own feature already defines and inserting the resulting facts into `ctx.store` — this feature does not reimplement or wrap that logic, it only calls `stage.run(ctx)` for each registered stage, in order, and reports what happened. A failing stage must not raise past `run()` — same failure-isolation rule as Feature 02's adapter executor — so one broken stage never aborts the others.

### Registration (`project_intel/cli/registry.py`)

```python
STAGE_REGISTRY: list[Stage] = [
    discovery.STAGE,
    git_analysis.STAGE,
    code_graph.STAGE,
    # hotspots.STAGE, architecture.STAGE, domain.STAGE, onboarding.STAGE — added by their own features when they land
]
```

This is an explicit, ordered list — **not** a dynamic plugin-discovery mechanism. Q189 (plugin mechanism) is still **Proposition**, not decided, so this feature must not speculatively build one. "Automatic" here means: adding a new stage is *one import + one list entry* in this one file, done by that feature's own implementation as part of its Acceptance Criteria (see the "CLI stage registration" note added to Features 03/04/05/06/08/09/10) — the runner logic below never changes when a stage is added. Order in the list should follow the dependency order already established in `specs/features/README.md` (discovery/git/graph before hotspots, before the LLM stages).

### `project-intel analyze <path>` (minimal form)

1. Open (creating if absent) a `FactStore` at `<path>/.project-intel/facts.sqlite` (Proposition — a sensible default location, overridable later by Feature 13's real config; not meant to be bikeshedded here).
2. Build a `PipelineContext` with a **built-in default** `ScopeConfig` (e.g. exclude `.git`, common vendor/build directories) — no config file parsing. Parsing a user-authored `Project`/`ScopeConfig` file is explicitly Feature 13's job (Proposition Q172).
3. Run each `Stage` in `STAGE_REGISTRY` order, in-process, sequentially (no need for Feature 02's parallel executor here — this is a thin runner, not a performance-sensitive one).
4. Print a summary table: stage name, status, fact count, and non-zero process exit code if any stage `failed` (not for `skipped`, which is expected when e.g. a tool isn't installed) — reusing Feature 02/Feature 01's status vocabulary directly, no new error model.

### `project-intel facts query`

Thin CLI wrapper over `FactStore.query_facts` (Feature 01) — flags for `--type`, `--run-id`, `--provenance`, and `--json` for machine-readable output. This is the one piece of Feature 13's original scope (Décidé Q178) pulled forward here, since it's essential for verifying each stage's output incrementally as features land, and has zero dependency on config/LLM/report.

## Explicitly out of scope for this feature

- Multi-repository / `Project` config file (**Proposition Q172**, not decided) — single repository path as a CLI argument only.
- Selective single-stage re-run flags (`--only=git`, etc.) — Feature 13's job; this feature always runs every registered stage.
- Debug/verbose per-adapter raw-output inspection (Décidé Q179) — Feature 13's job.
- LLM wiring beyond passing `llm_provider=None` through — once Features 07–10 land, their stages must degrade gracefully with `llm_provider=None` exactly as their own specs already require for "LLM disabled"; this feature does not add LLM-specific handling.
- HTML report generation — Feature 11's job; this feature's only output is the stored facts plus a terminal summary.
- Any interaction with the MCP server (Feature 12) — the CLI and the MCP server are two independent entry points onto the same `FactStore` (see [12-mcp-server.md](12-mcp-server.md)); this feature does not start, wrap, or depend on the MCP server in any way.

## Acceptance criteria

- `Stage`/`PipelineContext`/`StageRunResult` implemented matching the shapes above; `PipelineContext` and `StageRunResult` are `@dataclass(frozen=True, slots=True)` per the [regeneration contract](README.md#regeneration-contract).
- `STAGE_REGISTRY` lists whatever stages exist at build time (Discovery, Git analysis, Code graph at minimum, given they're already implemented) — a test registers a fake extra `Stage` and confirms the runner picks it up and executes it correctly without any change to the runner's own code, proving the "one import + one list entry" claim.
- `project-intel analyze <path>` run against a small real fixture repository (checked into `tests/fixtures/`) executes every registered stage, persists facts, and prints a correct per-stage summary — this is the first true end-to-end smoke test of the deterministic pipeline built so far.
- A deliberately failing stage (e.g. missing external tool) is reported as `failed`/`skipped` without aborting the other stages, and the process exit code reflects it.
- `project-intel facts query --type <t> --run-id <id>` returns the expected facts from a prior `analyze` run.
- `uv run pytest` and `uv run ruff check .` pass.
