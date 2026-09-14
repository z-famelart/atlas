# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

The repo has two parts: the specs (below) and a Python implementation being built out feature by feature under `src/project_intel/`, following [specs/features/](specs/features/) in order. Implementation is early — do not assume a feature exists just because a later one's spec references it; check `specs/features/README.md` and the actual source tree for what has landed so far.

## Git workflow

- **Linear history only** — never use `git merge`; always rebase branches before integrating (`git rebase main` then `git merge --ff-only`).
- Worktrees are fine for parallel work, but the branch must be rebased on top of `main` before merging, so the result is a straight line of commits.
- If fast-forward is impossible (histories diverged), fix it with `git rebase`, not `git merge`.
- **Conventional Commits** — all commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) spec: `<type>(<scope>): <description>`. Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `perf`. Scope is optional but encouraged (e.g. `feat(discovery):`, `fix(adapters):`).

## Commands

- Install toolchain (pins Python 3.12 + uv via `.mise.toml`): `mise install`
- Install dependencies: `uv sync`
- Run the CLI: `atlas` (or `uv run atlas`)
- Run all tests: `uv run pytest`
- Run a single test: `uv run pytest tests/test_smoke.py::test_main_runs`
- Lint: `uv run ruff check .`

- [specs/Product Brief & Vision.md](specs/Product Brief & Vision.md) — the pitch, problem statement, use cases, core principles, target outputs, conceptual architecture, and target workflow.
- [specs/Capability Matrix.md](specs/Capability Matrix.md) — a question-by-question matrix (Discovery, Code Graph, Hotspots, Domain Understanding, Runtime, Infrastructure, CI/CD, Data, Tests, Git Evolution, Observability, Documentation, Anomalies/Risks, Onboarding Path) mapping each question to priority (P0/P1/P2), source, whether it's deterministic/existing-tool/internal/LLM-derived, and its evidence type.
- [specs/Design Questions.md](specs/Design Questions.md) — ~210 open design questions grouped by topic (A–S: scope/mental model, discovery, adapters, normalized facts, graph, hotspots, architecture interpretation, domain understanding, LLM orchestration, Git, infrastructure, HTML report, MCP, performance, security/privacy, UX/CLI, extensibility, MVP, validation) that need to be resolved before implementation begins. Note the filename typo ("Atlaas") — this is the actual filename on disk, not a mistake to silently "fix" without confirming with the user first.

- [specs/Design Decisions.md](specs/Design Decisions.md) — answers to the ~210 design questions above, section by section, each marked Décidé/Proposition/Ouvert; open items still needing a product decision are listed in its closing summary.
- [specs/features/](specs/features/) — one implementation spec per feature, in build order, each scoped strictly to points marked **Décidé** in Design Decisions.md (see [specs/features/README.md](specs/features/README.md) for the ordered list and dependency chain).

The four documents above (Product Brief, Capability Matrix, Design Questions, Design Decisions) are written in French; the `specs/features/` implementation specs are written in English since they sit alongside the (English) codebase.

## Project concept: "Project Intelligence" (a.k.a. Atlas)

A tool for software engineers/consultants onboarding onto an unfamiliar codebase. It produces an actionable understanding map of a software system, answering: *What is this system? How is it built and how do its components interact? Where should I look first to become effective quickly?*

Core design principles (from the Product Brief — these should govern any future implementation work in this repo):

1. **Existing tools first** — orchestrate/adapt specialized external tools (AST, dependency analysis, complexity, security, Git, IaC, Kubernetes, CI/CD, OpenAPI, docs) rather than reimplementing them.
2. **Deterministic first** — anything computable without an LLM (file counts, language detection, dependency graphs, Git churn, centrality, Terraform/K8s parsing, simple metrics) must be computed deterministically.
3. **LLM for interpretation only** — synthesis, explanation, business-concept identification, architectural pattern interpretation, workflow construction, onboarding path suggestions, and connecting observations.
4. **Evidence first** — every non-trivial claim must be traceable to evidence (file, line, symbol, commit, config, tool output, doc, external source), and the system must distinguish *observed fact* vs *computed metric* vs *interpretation* vs *hypothesis*.
5. **Never pretend to know** — the system must be able to explicitly say information is unavailable, unanalyzed, or hypothesis-only.
6. **Repository != System** — a single analyzed repository may not represent the whole system (infra/CI/GitOps/dashboards may live elsewhere); the data model must distinguish repository, project, system, environment, and external source.

Primary output: an interactive, evidence-linked HTML report. Secondary outputs: a machine-readable facts/insights model and an MCP server so a coding agent can query the same knowledge (components, dependencies/dependents, hotspots, paths between components, "where to start").

Explicit non-goals: this is not meant to become a general AST analyzer, dependency-analysis tool, security scanner, IDE, Git replacement, Terraform/K8s tooling replacement, blind-exploration agent, or a tool that dumps whole repositories to an LLM.

## Working in this repo right now

Implementation work follows [specs/features/](specs/features/) strictly in order (01 → 13); each feature's spec lists what it depends on, what it must not implement yet (points still **Proposition**/**Ouvert** in Design Decisions.md), and its acceptance criteria. Do not skip ahead or build something two features early just because it seems related — a later feature's spec is the place that resolves what an earlier one deliberately left open. Commit after each feature lands, same as the specs themselves were committed one per feature.
