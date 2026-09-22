# Feature 14e — Agent synthesis for a multi-repository System

## Depends on

Feature 14/14b/14c/14d (the `atlas-synthesis` agent recipe — single-repository mode, unchanged by this feature). [Feature 13b](13b-multi-repo-system-orchestration.md) (writes the system store this feature reads) and [Feature 12e](12e-mcp-system-query.md) (`get_system`, the tool this feature calls).

## Goal

A monorepo with several sub-projects (or several separate repositories declared under a shared `system =` in a Project config) currently has no synthesis path that reflects that structure — the agent only knows how to target one `repo_path` and produce one flat document. This feature extends the `atlas-synthesis` recipe (`.claude/agents/atlas-synthesis.md`) with a second invocation mode: given a `config_path` + `system_name` instead of a `repo_path`, it produces **one tabbed HTML document** — an Overview tab describing how the declared members relate, plus one findings tab per member, each identical in shape to what single-repository mode already produces for that member alone.

This is a pure recipe extension, same spirit as 14b/14c/14d: no new MCP primitive (12e already exists), no new fact type, no change to Atlas's core `src/` beyond what 13b/12e already shipped.

## Scope

### Two invocation modes, not a rewrite

Single-repository mode (the entire existing recipe — startup sequence, MCP query sequence, provenance rules, two-section HTML shape, output destination) is unchanged and still the default when invoked with a `repo_path`. System mode is additive: invoked with `config_path` + `system_name` instead.

### Bootstrapping and member enumeration

- `project_root` is always `config_path`'s parent directory (matches [13b](13b-multi-repo-system-orchestration.md)'s own convention).
- If `<project_root>/.atlas-cache/system-<system_name>.sqlite` doesn't exist yet, the agent runs `atlas analyze --config <config_path>` once (this single invocation analyzes every declared member *and* writes the system store, per 13b) before proceeding.
- The agent calls `get_system(project_root, system_name)` (12e) to enumerate members. Each returned repository's `id` is used directly as that member's `repo_path` — never reconstructed or guessed.

### Per-member reuse, not duplication

For each member, the agent runs the *entire* existing single-repository "Prerequisites / startup sequence" and "MCP query sequence" verbatim (its own LLM-flag resolution, its own per-repository staleness check per 14c, its own conditional `atlas analyze <repo_path>` run) — this feature does not introduce a second, parallel per-repository procedure. Each member's resulting two-section content (Atlas findings / My read) becomes that member's tab, unmodified.

### The Overview tab: relay what's declared, interpret the rest

Per **Décidé Q4**, Atlas itself does not infer *how* declared repositories relate — only *that* they do. So the Overview tab's relayed layer is thin by design: the `belongs_to` facts from `get_system` (provenance `observed`, confidence 1.0), cited plainly. Everything else is the agent's own reading — applying the same "open and read the files yourself" principle 14d already established for architecture gaps, here pointed at `project_root`'s own top-level files (`docker-compose.yml`/`compose.yaml`, workspace manifests, root CI config, the config file itself) to describe the actual topology (which members talk to which, which is standalone infra, etc.). This interpretive content carries no provenance badge, same rule as every other "My read" section in this recipe.

### Tabbed HTML shell

Still one self-contained file — no server, no build step, no per-tab file. A top nav bar (plain CSS/JS, no framework, consistent with the rest of this recipe) switches between the Overview tab and one tab per member, labeled by each member's `name` attribute (falling back to `id`). One evidence panel is shared across all tabs.

### Output destination

Defaults to `atlas-synthesis-<system_name>.html` (vs. single-repository mode's `atlas-synthesis.html`), same directory convention (current working directory unless the user specifies otherwise).

## Explicitly out of scope for this feature

- Any new MCP tool or fact type — 12e/13b already provide everything this feature reads.
- Any change to Feature 11's core HTML report — this stays an agent-recipe capability, a choice made explicitly in conversation before 13b/12e were built (see 13b's "Explicitly out of scope").
- Automatic detection of member repositories/system boundaries — the agent only enumerates whatever `get_system` returns, which only ever reflects explicit `system =` declarations (Q4); it does not guess at monorepo sub-project boundaries on its own.
- A shared/merged evidence model across members — each member's facts/evidence stay scoped to that member's own tab and its own `fact_id`s; the Overview tab's only Atlas-sourced citations are the `belongs_to` facts themselves.

## Acceptance criteria

- Invoking the recipe with a `config_path` pointing at a Project config with 2+ `[[repositories]]` sharing `system = "x"` produces one HTML file with a nav bar showing "Overview" plus one button per member, each member tab containing that member's own hotspots/architecture/domain/onboarding content exactly as single-repository mode would produce it standalone.
- The Overview tab's relayed layer states exactly the declared members (matching `get_system`'s `repositories` list) with `observed` provenance and no fabricated relationship beyond what `belongs_to` states.
- The Overview tab's interpretive content is visibly present, distinct (no provenance badge), and grounded in files the agent actually read under `project_root` (verified by spot-checking that a claim about service topology traces to an actual `docker-compose.yml`/workspace-manifest line in a worked example).
- Single-repository mode's existing behavior (startup sequence, query sequence, HTML shape, output filename) is unchanged — verified by diffing this feature's edits against the pre-existing recipe file and confirming every change is additive (new sections/subsections), not a modification of single-repository-mode prose.
