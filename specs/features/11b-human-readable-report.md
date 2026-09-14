# Feature 11b — Human-readable HTML report

## Why this is a separate feature, not a rewrite of Feature 11

Feature 11 (HTML report) is **already implemented and shipped** (`src/project_intel/html_report/`). Per the [regeneration contract](README.md#regeneration-contract), its spec is a stable record of a shipped interface (`generate_report(store, run_id, output_dir) -> Path`, the section-template structure, the shared provenance/evidence rendering primitive) — this feature does not rewrite it. It fixes a real bug and adds real new scope, both additive.

This feature exists because the shipped v1 report has two concrete, user-reported problems:

1. **Mermaid diagrams never render.** `_render_system_map` emits `<pre class="mermaid">...</pre>` followed by the literal text *"Load mermaid.js locally to render diagram."* — there is no `<script>` loading Mermaid anywhere in the generated file. This technically passes Feature 11's existing acceptance criterion ("no external script/link references") while being useless: the diagram never displays, in direct tension with Décidé Q137/Q138 (report must work fully offline, diagrams included) even though no test caught it. This is a bug fix against already-decided scope, not new scope — see **Décidé Q129** (updated 2026-09-14).
2. **Every section is a raw, clickable list of individual facts (a "listicle") with no narrative text.** `_render_executive_summary`, `_render_architecture`, `_render_domain`, etc. all build `<div class="fact-list">` of one `_fact_row(...)` per fact — there is no sentence anywhere saying, in effect, "Atlas found these technologies." Reading the report today means mentally reconstructing meaning from a list of badges. This is new scope, not a bug — Feature 11's Décidé Q130 only required "always render from facts, never hide a section," it didn't mandate the *shape* of that rendering. See **Décidé Q140b** (new, 2026-09-14).

## Depends on

Feature 11 (HTML report — already implemented, its `generate_report` entry point, section list, and shared provenance/evidence primitives are reused, not replaced). Reads whatever facts Features 03–10 have produced, same as Feature 11 already does — no new fact types, no new upstream dependency.

## Goal

Make the generated report actually readable by a human without clicking through individual facts first, per **Décidé Q129 (updated), Q140b**:

- Diagrams render in the browser, standalone, offline — not a placeholder asking the user to set something up themselves.
- Each section leads with narrative prose; facts remain present as evidence, not as the primary content.

## Scope

### Mermaid vendored inline (Décidé Q129)

Bundle mermaid.js's UMD build (a specific pinned version, fetched once at build/packaging time — not at report-generation runtime, and never at report-viewing time) as a local asset, and embed its full source inside a `<script>` tag in the generated HTML, immediately followed by a small init script (`mermaid.initialize({...}); mermaid.run();` or the pinned version's equivalent API) that runs against every `<pre class="mermaid">` block already emitted by Feature 11's renderers. Delete the `.mermaid-hint` placeholder text and its CSS entirely — once the script is embedded, there's nothing to hint at. This is purely an addition to the HTML template's `<head>`/`<script>` output; the Mermaid diagram *source* generation (`_render_system_map`'s `graph LR ...` string building) is untouched.

No network fetch at any point after the mermaid.js source is committed into this repository (or vendored via the build) — opening the generated report offline must render diagrams correctly, consistent with Feature 11's already-decided Q137/Q138.

### Narrative section rendering (Décidé Q140b)

For each section Feature 11 already renders from facts, add a narrative paragraph **above** the existing fact-list (the fact-list stays — evidence drill-down per Q131/Q132 is unchanged — it becomes supporting detail under the prose, not the section's only content). Two rendering strategies, matching Q140b:

- **Deterministic/observed/computed sections** (executive summary, code map, hotspots, git evolution, risks) — a **template-generated sentence**, built from the same query results the section already computes, no LLM call. E.g.: `"Atlas detected {n} languages: {list}."`, `"The {n} highest-churn files are {list}."`, `"{n} dependency cycles were found."` Every section keeps working with zero facts (Feature 11's existing not-analyzed state is unchanged) and with any count of facts (template must handle 0/1/many gracefully, e.g. correct pluralization/list punctuation isn't required to be linguistically perfect — this is a template, not an LLM — but must not read as broken, e.g. no dangling "and ." for an empty trailing list).
- **Already-interpretive sections** (architecture, domain understanding, onboarding path — Features 08/09/10) — these features' facts *already carry* LLM-authored narrative fields (e.g. `architecture_hypothesis.pattern_description`, business concept/workflow descriptions per Feature 09, the onboarding rationale per Feature 10) plus their `confidence` and `fact_ids` citations. This feature's job is only to **render those existing fields as a paragraph** (with inline citation markers linking to the same evidence drill-down Feature 11 already provides per fact id) instead of extracting just a `pattern`/`name` label into a list row. No new LLM call, no new prompt, no new fact type — the text already exists in the `FactStore`, Feature 11 just wasn't reading that field.

### Explicit degrade path stays intact

A section with no relevant facts still renders Feature 11's existing not-analyzed state (Décidé Q130) — this feature does not change that; a template sentence is only emitted when there's something to describe. A hypothesis fact citing facts that no longer resolve (shouldn't happen given Feature 07's citation validator, but defensively) falls back to rendering the fact-list alone for that entry, same failure-isolation spirit as everywhere else in this project — never a crash.

## Explicitly out of scope for this feature

- Any new LLM call, prompt, or fact type — every narrative sentence for deterministic sections is a fixed template over already-computed values; every narrative paragraph for interpretive sections reuses text Features 08/09/10 already produce.
- Rewriting Feature 11's section list, `generate_report` signature, or shared provenance/evidence primitive — this feature only changes what's rendered *inside* each section body and adds the Mermaid init script to the page shell.
- The interactive force-directed/cytoscape.js graph view (**Proposition Q129's deferred half**) — still not built; Mermaid vendoring only fixes the existing static diagrams.
- Any change to Feature 12 (MCP) or [Feature 14](14-agent-mcp-synthesis.md)'s agent-driven synthesis path — this feature only improves the standalone HTML deliverable; see 14 for the complementary agent+MCP path.

## Acceptance criteria

- A generated report, opened in a browser with no network access, renders every Mermaid diagram Feature 11's renderers produce — no `.mermaid-hint` text anywhere in the output (grep check), no `<script src="http...">` for Mermaid or anything else (Feature 11's existing offline test still passes).
- Every section that has facts (per Feature 11's own test fixtures — Discovery + Hotspots at minimum) renders a narrative paragraph before its fact-list; a section with zero facts still renders Feature 11's existing not-analyzed state, not an empty/broken template sentence.
- A test using a fixture `architecture_hypothesis` fact with a `pattern_description` and `fact_ids` proves the rendered section includes that description as readable text (not just the `pattern` label), with citation markers still resolving to the same evidence panel Feature 11 already implements.
- Deterministic-section templates are proven not to call any `LLMProvider` (grep/import check, or a test with a `None` provider still producing correct prose).
- `uv run pytest` and `uv run ruff check .` pass.
