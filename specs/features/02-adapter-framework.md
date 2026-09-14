# Feature 02 — Adapter framework

## Depends on

Feature 01 (Facts & Evidence model) — adapters produce `Fact[]` against that model.

## Goal

Implement the generic contract and execution machinery that every integration with an external tool (language/LOC detector, complexity tool, later: Git, graph provider, IaC/CI detectors, etc.) must follow, per **Décidé Q24/Q33** ("Existing tools first"). This feature ships the framework and its error-handling/lifecycle rules only — it does not ship any concrete analyzer (those are later features: Discovery, Git analysis, Code graph, ...).

## Scope

### Adapter manifest (Décidé Q24)

An adapter is declared, not hand-coded per case, whenever it's a thin wrapper around a CLI tool. Manifest shape:

```
name: str
category: str                 # e.g. "language-detection", "complexity", "git", "graph"
supported_ecosystems: list[str] | None   # languages/build systems this adapter applies to, None = always applicable
command: list[str] | Callable # invocation template, or a Python callable for non-CLI adapters
output_format: str            # how to parse the raw output ("json", "lines", custom parser name)
min_version: str | None
max_version: str | None       # Décidé Q28
normalize: Callable[[RawOutput], list[Fact]]   # adapter-specific normalization to the Fact model
```

Adapters that are pure Python (no external binary) implement the same interface via `command=None` and a direct `run()` callable — the manifest shape is the same contract either way.

### Adapter contract (Décidé Q33)

Every adapter, regardless of implementation, must produce `list[Fact]` matching Feature 01's model:
- `provenance` set to `deterministic`/`observed` or `computed` as appropriate — never `inferred`/`hypothesis` (that's reserved for the LLM/interpretation layer, later features).
- Every fact carries `evidence` and `source_analyzer = <adapter name>`.
- No adapter may return unstructured/free-form output as a `Fact.value` — normalization into typed facts happens inside the adapter, not downstream.

### Presence & version checks (Décidé Q25, Q28)

Before invocation, the framework:
1. Checks the binary is present (`which`/equivalent). No automatic installation (**Décidé Q25** — installation is never automated; the framework surfaces the install command to the user instead).
2. If present, checks its version against `min_version`/`max_version`. Out-of-range → the adapter is not run.

### Execution & failure isolation (Décidé Q29, Q30, Q157, Q180)

- Each adapter runs in isolation; one adapter's exception/non-zero exit must never abort the run of other adapters or the pipeline (**Décidé Q30**).
- Independent adapters (no data dependency between them) run in parallel by default (**Décidé Q157**); this feature should implement the parallel executor, even though the MVP set of adapters that actually use it ships in later features.
- Every adapter execution ends in exactly one of these statuses, recorded (not raised as an unhandled exception): `ok`, `skipped:tool_not_found`, `skipped:version_mismatch`, `failed` (with captured error message as evidence-worthy output). These are the same status vocabulary reserved in Feature 01.
- Errors are collected, not printed-and-forgotten: the executor returns a per-adapter result list so a later CLI feature can render a summary without re-running anything (**Décidé Q180**: "afficher les erreurs sans interruption").

### Contract testing (Décidé Q32)

The framework must make it possible to test an adapter's `normalize()` function against a **fixture of real captured tool output**, independent of whether the underlying tool is installed. This feature should ship the fixture-based test harness/helper (e.g. `assert_normalizes(adapter, fixture_path, expected_facts)`), even though no real adapters exist yet to exercise it beyond a trivial example adapter used in this feature's own tests.

### Versioning (Décidé Q31)

Each adapter carries its own semantic version, independent of the wrapped tool's version, so the normalized-output format can evolve without being tied to upstream tool releases. Store this as part of the manifest and stamp it onto every `Fact.source_analyzer` reference (e.g. `"complexity-radon@1.0.0"`) so facts remain attributable to the exact normalization logic that produced them.

### Logging (per [README](README.md#logging-a-convention-every-feature-follows)'s logging convention)

The adapter executor logs via `logging.getLogger(__name__)`: `INFO` on invocation start/end (adapter name, target), `WARNING` on any `failed`/`skipped:*` result with the underlying reason (subprocess exit code/stderr, missing binary, version mismatch), `DEBUG` with the exact command invoked and raw pre-normalization output. Every concrete adapter built on this framework inherits this for free — it does not add its own separate logging.

## Explicitly out of scope for this feature

- No concrete adapters (language detection, Git, graph, complexity, IaC/CI, etc.) — each is its own later feature.
- Docker-encapsulated adapters (**Proposition Q27**, not decided) — do not build Docker invocation support yet.
- Result caching keyed by input hash (**Proposition Q159**, not decided) — out of scope here; this feature only guarantees adapters *can* be re-run cheaply because they're isolated and declarative, not that they *are* cached.
- Any connector requiring credentials/API access (section K) — this is the local, binary/callable-invocation adapter framework only.

## Acceptance criteria

- `AdapterManifest`/`Adapter` types implemented matching the shapes above.
- An executor (`run_adapters(manifests, context) -> list[AdapterResult]`) that: checks presence/version, runs independent adapters concurrently, isolates failures, and returns one `AdapterResult` (status + facts + error detail) per adapter — never raises for an individual adapter failure.
- A fixture-based contract-test helper, demonstrated on one trivial example adapter (e.g. a fake "count files" adapter) written purely for this feature's own tests — not counted as a real analyzer feature.
- Unit tests cover: missing binary → `skipped:tool_not_found`; version out of range → `skipped:version_mismatch`; raising adapter → `failed` without aborting sibling adapters; successful adapter → facts carry correct `source_analyzer` version stamp and `provenance`.
- `uv run pytest` and `uv run ruff check .` pass.
