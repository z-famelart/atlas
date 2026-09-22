# Feature 13b — Multi-repository System orchestration

## Depends on

Feature 13 (CLI — the `[[repositories]]` loop, `_load_config`, already implemented and unchanged by this feature). Feature 01 (Facts & Evidence model — `EntityType.SYSTEM`/`EntityType.REPOSITORY` and `RelationType.BELONGS_TO` already exist as valid values; this feature needs no schema change).

## Goal

Complete **Décidé Q3/Q4**, which Feature 13's own spec already claimed ("running the same `STAGE_REGISTRY` per repository and merging results into one `FactStore`") but never delivered: today each `[[repositories]]` entry is analyzed fully independently (own `FactStore`, own `run_id`, own HTML report) and the `system` field Q4 defines is parsed away and never read (`repos_cfg` keeps only `path`/`name` — see `src/project_intel/cli/main.py`). `Design Decisions.md` Q4 already documents this gap explicitly as "Statut : non implémenté". This feature closes it, narrowly, to exactly what Q4 already decided — no more.

## What Q4 already ruled out (do not re-litigate)

Q4 is explicit: system membership is **organizational knowledge, declared only** — "Pas de détection automatique : l'appartenance à un système est une connaissance organisationnelle que le code seul ne prouve pas — la deviner contredirait « Never pretend to know »." This feature therefore does not infer *how* repositories relate (no docker-compose/workspace/OpenAPI parsing, no heuristic clustering) — it only records and exposes what the config *declares*. Narrating how declared members relate is deliberately left to the agent-recipe layer (Feature 14 family), which can read root-level files itself and label that reading as interpretation, not an Atlas fact — consistent with how Feature 14d already handles architecture gaps.

## Scope

### Config: read the `system` field (Décidé Q4)

Each `[[repositories]]` entry in the `Project` TOML config may carry an optional `system = "<name>"` string (a repository may belong to zero, one system for now — many-to-many per Q5 is a model-level allowance, not required by this feature's first cut; a repo with no `system` behaves exactly as today, fully unaffected). No other config shape changes.

### System/Repository/belongs_to facts (Décidé Q2, Q4, Q5)

After Feature 13's existing per-repository loop completes unchanged (each repository still gets its own `STAGE_REGISTRY` run, its own `.atlas-cache/facts.sqlite`, its own HTML report — none of that is touched by this feature), group the configured repositories by declared `system`. For every system name with **two or more** member repositories (a system of one repository has nothing to orchestrate — skip it):

- One `Entity(type=EntityType.SYSTEM, id=<system_name>, attributes={})`.
- One `Entity(type=EntityType.REPOSITORY, id=<repo_name>, attributes={"path": <repo_path>}, repository_id=<repo_name>)` per member (reuses the `repository_id` field `Entity` already has).
- One `Fact` per member: `subject=EntityRef(REPOSITORY, <repo_name>)`, `predicate="belongs_to"` (`RelationType.BELONGS_TO`, already defined), `object=EntityRef(SYSTEM, <system_name>)`, `provenance="observed"` (it is read verbatim from user-authored config, not inferred), `confidence=1.0`, `evidence=(Evidence(kind="config", ref=ConfigRef(repository_id=<repo_name>, path=<config file path relative to itself>), source_analyzer="system_orchestration", retrieved_at=now),)`.

### Storage: a small, separate System store (no merged FactStore)

Per-repository stores keep their existing fixed location (`<repo_path>/.atlas-cache/facts.sqlite`) — a convention already load-bearing for the MCP server (Feature 12) and the `atlas-synthesis` agent (Feature 14), unchanged by this feature. System-level facts go into a **new, separate** `FactStore` at `<project_root>/.atlas-cache/system-<system_name>.sqlite`, where `project_root` is the directory containing the loaded config file (mirroring the existing `<repo_path>/.atlas-cache/` convention one level up, at Project instead of Repository granularity). Reuses `FactStore` unchanged — no schema/class change, just a different path.

### CLI wiring

After the existing `for repo_entry in repos:` loop in `analyze` (`src/project_intel/cli/main.py`), add the grouping-and-write step described above. Runs once per `analyze` invocation with a multi-repository config, using a fresh `run_id` distinct from every per-repository run's `run_id`. Prints one summary line per system written (e.g. `System 'myapp': 4 repositories`) — same terse style as the existing per-repository `── {repo_name} ({repo_path}) ──` banner.

## Explicitly out of scope for this feature

- Any automatic/heuristic detection of *how* repositories relate (docker-compose, package-manager workspaces, OpenAPI client matching, CI matrix parsing) — ruled out by Q4 itself, not merely deferred; a future heuristic (if ever wanted) is P2 and produces `hypothesis`-provenance facts, a different feature.
- Merging per-repository `FactStore`s into one database, or changing the `<repo_path>/.atlas-cache/facts.sqlite` path convention — both explicitly rejected as unnecessary and load-bearing-breaking (see "Storage" above).
- Any change to Feature 11's HTML report — a system spans multiple repositories, each already producing its own standalone report unchanged; no cross-repository rendering is added to the core report by this feature (see [Feature 12e](12e-mcp-system-query.md) and the `atlas-synthesis` agent recipe for how this data actually reaches a human — a deliberate choice made in conversation, not this spec's default).
- Exposing the new system store over MCP — that is [Feature 12e](12e-mcp-system-query.md), kept separate since it's an MCP-surface change, following the existing precedent of splitting CLI-family (13, 13b) from MCP-family (12, 12b, 12c) specs.
- A repository belonging to more than one system in the same run producing more than one `belongs_to` fact — technically already supported by the loop (one fact per system it's declared under) but not specifically tested by this feature's acceptance criteria; not a blocker, just not verified here.

## Acceptance criteria

- A `Project` config with 4 `[[repositories]]` entries, all `system = "myapp"`, run through `analyze`, produces `<project_root>/.atlas-cache/system-myapp.sqlite` containing exactly 1 `System` entity, 4 `Repository` entities, and 4 `belongs_to` facts, each with `provenance="observed"`, `confidence=1.0`, and a `config`-kind evidence entry resolving back to the config file.
- Each of the 4 repositories still produces its own unchanged `.atlas-cache/facts.sqlite` and its own HTML report — a test asserts nothing in the per-repository pipeline changed (same fact count/shape as before this feature, run against a fixture with this feature's code reverted).
- A config with `[[repositories]]` entries that declare no `system`, or where every declared `system` has only one member, produces **no** system store at all.
- A config where two repositories share `system = "myapp"` and a third has no `system` produces a system store with exactly 2 members — the third is correctly excluded.
- `uv run pytest` and `uv run ruff check .` pass.
