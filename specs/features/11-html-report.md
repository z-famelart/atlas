# Feature 11 — HTML report

## Depends on

Feature 01 (Facts & Evidence model). Consumes whatever the `FactStore` contains from Features 03–10, but is not hard-coupled to any one of them — see scope note below.

## Goal

Generate the primary output: a self-contained, offline, evidence-linked interactive HTML report, per **Décidé Q126, Q130–Q138, Q140**.

## Scope

### Section structure (Décidé Q126)

Mirrors the Product Brief §5 list exactly: executive summary, system map, architecture, code map, hotspots, domain understanding, runtime, infrastructure, CI/CD, data architecture, observability, tests, Git evolution, risks/anomalies, onboarding path, glossary, evidence.

### Sections render from facts, always (Décidé Q130, Q199)

Every section is a renderer that queries the `FactStore` for its relevant fact types and renders what's there. A section with no facts of its relevant type renders as an explicit "not analyzed" state (reusing the same status vocabulary as Feature 01/02) rather than being omitted from the template — this is what lets the report be generated meaningfully even though only Features 03–10 exist so far and sections like "infrastructure" or "observability" have no producing feature yet. This feature must not hard-code a dependency on any specific upstream feature; it hard-codes only the section *template* and the fact *types* each section looks for.

### Provenance visualization (Décidé Q136, Q135)

A single, shared visual convention (not per-section bespoke styling) for `observed` / `computed` / `inferred` / `hypothesis`, and for confidence score, applied uniformly across every section. This is implemented once as a shared rendering primitive, not reimplemented per section.

### Evidence drill-down (Décidé Q131, Q132)

Every rendered fact/relation is a clickable element linking to its `Evidence` list (file/line/symbol/commit/etc., per Feature 01's shapes). This is a generic capability of the shared rendering primitive above, not section-specific code.

### Search (Décidé Q133)

Full-text client-side search over entity names/paths/symbols present in the report's embedded data — no server, no network call, consistent with offline requirement.

### Diagrams (Proposition Q128/Q129)

At minimum: a system map and a code graph view, generated from graph facts (Feature 05) via Mermaid for simple static diagrams and a dedicated interactive rendering for the navigable multi-level code graph (Mermaid alone doesn't scale to large interactive graphs, per Design Decisions §L). Diagram inputs come exclusively from facts (Décidé Q130) — never hand-authored.

### Offline, self-contained, versioned (Décidé Q137, Q138, Q140)

Single HTML file (or HTML + local adjacent asset files, no external network fetch) embedding all data needed to render every section without a server. Every generated report embeds `run_id`, generation timestamp, and each analyzed repository's commit hash, so two reports can be told apart/compared later.

## Explicitly out of scope for this feature

- Filtering the graph by relation type/confidence (**Proposition Q134**, not decided in detail) — a nice-to-have on top of the interactive graph view; not required for this feature's first cut.
- Exporting individual views as image/PDF (**Proposition Q139**, P2) — not in scope.
- Any new fact production — this feature is a pure consumer/renderer of the `FactStore`; it must not compute anything that belongs in an earlier feature.

## Acceptance criteria

- A `generate_report(store: FactStore, run_id: str) -> Path` entry point producing one self-contained HTML file.
- All 17 sections from the Product Brief list are present as templates, each rendering real data when facts exist and an explicit not-analyzed state when they don't — demonstrated by running report generation against a `FactStore` populated only with Discovery + Hotspots facts (no graph/LLM features run) and confirming e.g. the "architecture" section shows not-analyzed rather than crashing or vanishing.
- Provenance/confidence are visually distinguishable using one shared rendering primitive (test asserts the same CSS class/marker scheme is used across at least two different sections).
- Clicking any rendered fact reveals its evidence (verified via a DOM/data-attribute assertion in tests, not necessarily a browser test).
- The generated file has no `<script src="http...">`/`<link href="http...">` pointing outside the file itself — verified by a test that scans the output for external references.
- Report embeds `run_id`, timestamp, and commit hash(es).
- `uv run pytest` and `uv run ruff check .` pass.
