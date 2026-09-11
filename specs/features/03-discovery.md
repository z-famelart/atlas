# Feature 03 — Discovery

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework).

## Goal

Detect, deterministically, what a repository *is* — languages, frameworks, build systems, package managers, repository structure, documents, config files, and presence of IaC/Docker/Kubernetes/CI — per **Décidé Q11–Q19**. This is the first concrete set of adapters built on Feature 02, and the first pipeline stage per the Product Brief's conceptual architecture ("Source detection").

## Scope

### Signature-based detection (Décidé Q12–Q14, Q17, Q18)

Frameworks, build systems, package managers, IaC files, and Docker/Kubernetes/Helm/CI are **all** detected the same way: a **declarative signature table**, not bespoke per-category code. A signature entry is:

```
{ category: "framework"|"build-system"|"package-manager"|"iac"|"container"|"ci",
  name: str,
  match: { files: list[glob] } | { manifest_key: str, field: str, value_pattern: str },
  ecosystem: str | None }
```

Examples: `package.json` + `dependencies.react` present → framework `react`; `*.tf` present → IaC `terraform`; a YAML file with `kind:` matching a known Kubernetes API resource → container `kubernetes`; `.github/workflows/*.yml` present → CI `github-actions`.

This table-driven approach is what makes Feature Q182 ("add a new language") and the general extensibility goal (Décidé Q181/Q184) possible without touching core discovery logic later — this feature must ship the table as data (not inline conditionals) even though the initial table only needs to cover the MVP set.

### Language & LOC detection (Décidé Q11)

Delegated entirely to an existing external tool via the Feature 02 adapter contract (e.g. a `tokei`/`github-linguist`-class tool) — no in-house tokenizing/parsing. Output normalizes to `Fact`s of type `language_detected` (entity: `Repository`/`Directory`, value: language name + LOC) with `provenance = observed`.

### Git repository detection (Décidé Q15)

Presence of a `.git` directory (or `.git` file for worktrees/submodules) at the repository root, detected via the `git` binary itself (`git rev-parse --git-dir`), not manual filesystem heuristics. Produces a `Repository` entity fact confirming it is Git-backed; this is a prerequisite check consumed by the later Git analysis feature but this feature does not run any Git history analysis itself.

### Documents & config files (Décidé Q26–Q27 of Capability Matrix / Q17 of Design Questions)

Plain filesystem enumeration (respecting the scope include/exclude from configuration, see below) tagging recognized document types (`README*`, `CHANGELOG*`, `docs/**`, etc.) and recognized config files, as `Document`/`File` entity facts.

### Unrecognized technologies (Décidé Q19)

Discovery output always includes an explicit `unrecognized` bucket: files/dependencies that matched no signature. This is itself a `Fact` (`type: unrecognized_artifact`, `provenance: observed`) — never silently dropped. This is what later lets the signature table (and this feature) improve over time without hiding gaps.

### Scope enforcement (Décidé Q9)

Discovery is the first place user-declared scope (include/exclude path globs, language filters, repository filters from the `Project` configuration) is applied. This feature must accept a `ScopeConfig` and filter the filesystem walk accordingly *before* running any signature matching — this is the concrete implementation of the non-goal "agent qui explore aveuglément toute la codebase". Scope configuration itself (the `Project`/multi-repository config file format) is not part of this feature; this feature only needs to accept an already-parsed `ScopeConfig` object as input.

### Offline (Décidé Q10)

All of the above is local filesystem + local binary invocation. No network access anywhere in this feature.

## Explicitly out of scope for this feature

- Multi-repository/system declaration (**Proposition Q4**, not decided) — this feature runs discovery against one repository at a time; orchestrating it across several repositories of a `Project` is a later concern (not yet a scheduled feature) built on top of this one.
- Detecting that part of the system lives elsewhere (**Proposition Q16**, not decided) — do not implement `ExternalSource` inference heuristics here.
- The `Project` configuration file format itself (**Proposition Q172**, not decided) — this feature consumes a `ScopeConfig`, it does not define how it's authored/loaded.
- Any actual Git history analysis (churn, co-change, ...) — Git detection here is presence-only; analysis is a separate later feature.
- Any code graph extraction — separate later feature.

## Acceptance criteria

- A declarative signature table (data file, not inline conditionals) covering: at least one build system, one package manager, one framework, Docker, Kubernetes, one CI system, one IaC tool — enough to prove the mechanism, not exhaustive coverage.
- A language/LOC adapter wrapping one real external tool via the Feature 02 contract, with a fixture-based contract test (per Feature 02's harness) so it's testable without the tool installed.
- A Git-presence adapter using the `git` binary.
- A document/config enumerator respecting `ScopeConfig` include/exclude.
- All outputs are `Fact`s against the Feature 01 model, `provenance = observed`, with file-based `Evidence`.
- An `unrecognized_artifact` fact type is emitted for anything matching no signature.
- Unit tests run discovery against a small fixture repository (checked into `tests/fixtures/`) and assert the expected facts, including at least one unrecognized artifact and one scope-excluded file that must *not* appear in the output.
- `uv run pytest` and `uv run ruff check .` pass.
