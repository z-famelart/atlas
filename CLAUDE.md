# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repository currently contains **specification documents only** — there is no source code, build system, package manifest, or test suite yet. It is not a git repository. Do not look for or assume the existence of an implementation; the three markdown files here *are* the project so far.

- [specs/Product Brief & Vision.md](specs/Product Brief & Vision.md) — the pitch, problem statement, use cases, core principles, target outputs, conceptual architecture, and target workflow.
- [specs/Capability Matrix.md](specs/Capability Matrix.md) — a question-by-question matrix (Discovery, Code Graph, Hotspots, Domain Understanding, Runtime, Infrastructure, CI/CD, Data, Tests, Git Evolution, Observability, Documentation, Anomalies/Risks, Onboarding Path) mapping each question to priority (P0/P1/P2), source, whether it's deterministic/existing-tool/internal/LLM-derived, and its evidence type.
- [specs/Design Questions.md](specs/Design Questions.md) — ~210 open design questions grouped by topic (A–S: scope/mental model, discovery, adapters, normalized facts, graph, hotspots, architecture interpretation, domain understanding, LLM orchestration, Git, infrastructure, HTML report, MCP, performance, security/privacy, UX/CLI, extensibility, MVP, validation) that need to be resolved before implementation begins. Note the filename typo ("Atlaas") — this is the actual filename on disk, not a mistake to silently "fix" without confirming with the user first.

- [specs/Design Decisions.md](specs/Design Decisions.md) — answers to the ~210 design questions above, section by section, each marked Décidé/Proposition/Ouvert; open items still needing a product decision are listed in its closing summary.

All documents are written in French.

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

Since there's no code yet, likely tasks are: refining these specs, answering/resolving the open design questions, or scaffolding an initial implementation. When scaffolding begins, follow the principles above (deterministic-first, evidence-first, existing-tools-first) as the architectural contract, and update this CLAUDE.md with real build/lint/test commands once a toolchain exists.
