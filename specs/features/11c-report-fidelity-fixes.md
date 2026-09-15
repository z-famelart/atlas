# Feature 11c — Report fidelity: correct field mapping, real diagram edges, cross-run fallback, distinct gap states

## Why this is a separate feature, not a rewrite of Feature 11/11b

Features 11 and 11b are **already implemented**. This feature fixes concrete, evidence-backed defects found by reading a real generated report (`atlas-report-f93202e8-033e-4af0-8824-38f40391d796.html`, against ggshield) side by side with the actual `FactStore` contents, plus adds new, explicitly-requested capability (cross-run fallback, distinct not-analyzed states). Per the [regeneration contract](README.md#regeneration-contract), additive rather than a rewrite.

## Depends on

Feature 11/11b (HTML report — already implemented, this feature edits `html_report/renderer.py`'s section renderers, not its `generate_report` entry point or shared primitives). [Feature 06c](06c-stage-run-persistence.md) (`stage_run_result` facts — required for the distinct-gap-states part of this feature only; the field-mapping and diagram fixes below don't need it).

## What was actually found (grounding for this spec)

Read directly from a real report and the `FactStore` it was generated from:

1. **Executive Summary** showed *"Detected 8 technologies: /Users/.../ggshield, /Users/.../ggshield, …"* — the stored fact is `{"category": "build_system", "name": "make"}`, but the renderer reads `.get("technology", f.subject.id)`. The key is `name`, not `technology`; the fallback silently returns the fact's subject (the repository path) instead of erroring, so the bug never surfaced as a crash.
2. **Hotspots** showed `(score: 0.00)` for every entry, including the "top" one. The stored fact is `{"combined": 0.82, "components": {...}}`; the renderer reads `.get("score", 0)`. Same bug class: wrong key, silent zero fallback, and since sorting also uses the same wrong key, "top hotspot" is arbitrary, not actually top.
3. **System Map** sorts "top by centrality" using `.get("score", 0)` too — but `centrality` facts only ever contain `in_degree`/`out_degree` (confirmed in `code_graph/metrics.py` — no combined score is computed anywhere in Feature 05). Same bug class, a third instance.
4. **System Map diagram** has zero edges — the Mermaid source only ever declares nodes from `centrality` facts; it never queries `imports`/`calls` facts (12,933 and 7,704 of them exist in the store) to draw a relationship. It also derives node IDs from `path.split("/")[-1]` (the basename only), so two different files sharing a basename (e.g. `ggshield/cmd/secret/scan/archive.py` and `ggshield/utils/archive.py`) silently collapse into one Mermaid node.
5. **Onboarding Path** narrative reads as a run-on sentence — `recommended_workflow.description`, `time_boxed_understanding.thirty_minutes`, and `.two_hours` are concatenated with a bare space, no punctuation/line breaks between them.
6. **Dependency cycles** exist as `{"cycle_members": ["a.py", "b.py"]}` but the renderer only shows `"Dependency cycle: <subject.id>"` — the actual cycle membership, the one piece of information that makes a cycle diagnosable, is dropped entirely.
7. **Git co-change** facts carry a `co_occurrences` count that's never shown.
8. **Symbol** facts carry structured `name`/`kind`/`file` that's never shown — the row just prints the raw `subject.id`.
9. **Architecture / Domain Understanding** showed "Not analyzed" for the run being read, even though the *same repository*, analyzed a few hours earlier, has 15 `architecture_hypothesis` and 5 `business_concept` facts sitting in the same store under a different `run_id`. The report has no way today to tell "genuinely nothing to find" apart from "this run's LLM stage failed, but a previous one succeeded."

## Scope

### A. Field-mapping fixes (bug fix, not new scope)

Correct the key each renderer reads, matching what each producing feature actually emits:

- Executive Summary: technology name reads `.get("name", ...)` (matches Feature 03's `technology_detected` shape), not `.get("technology", ...)`.
- Hotspots: score reads `.get("combined", ...)` (matches Feature 06's `hotspot_score` shape), not `.get("score", ...)`.
- System Map: centrality has no single "score" anywhere in Feature 05's shipped shape — sort and rank by a renderer-local combination (`in_degree + out_degree`, documented in code as a display-only convenience, not a new Feature 05 fact field) instead of a nonexistent `score` key.

### B. Real diagram edges + stable node IDs (new capability)

- For the top-N nodes already selected for the diagram (by the corrected centrality combination above), query `imports`/`calls` facts (Feature 05's `relation`-shaped facts, per `subject_id`/`object_id`) and emit a Mermaid edge (`A --> B`) for every relation where **both** endpoints are in the selected node set. Relations to nodes outside the top-N are not drawn (keeps the diagram legible; the full graph is still explorable via the fact-list and, eventually, the deferred interactive view — see "Explicitly out of scope").
- Node IDs are a stable, collision-free identifier derived from the **full path** (e.g. a short hash, or the path with `/` replaced by an underscore) — the basename is used only as the **label** (`node_id[basename]`), never as the ID. Fixes the `archive.py`/`archive.py` collision.

### C. Show the structured data that already exists (new scope, no new facts)

- Dependency cycles: render the full `cycle_members` chain (e.g. `"Cycle: a.py → b.py → a.py"`), not just the subject.
- Git co-change: include the `co_occurrences` count in the row label.
- Symbols: use `name`/`kind`/`file` for the label (e.g. `"PluginDownloader (class) — ggshield/core/plugin/downloader.py"`) instead of the raw `subject.id`.

### D. Narrative punctuation fix (bug fix)

Onboarding Path (and any other multi-field narrative assembly) joins its parts with proper sentence separation (period + space, or separate `<p>`/`<li>` elements) instead of a bare space — no more run-on concatenation.

### E. Cross-run fallback (new capability, per explicit decision)

Every section renderer's query becomes two-step:

1. Query facts of the relevant type(s) for `run_id=<current run>`, as today.
2. If empty, query the same type(s) with no `run_id` filter (`FactStore.query_facts` already supports this — no store interface change needed), group by `run_id`, and use the facts from the **most recent** `run_id` that has any (by `created_at`, already a `Fact` field).

When a fallback is used, the section's narrative prose says so explicitly and states which run it's from, e.g.: *"No architecture data for this run. Showing results from a previous analysis (run `f3400128`, 2026-09-14 13:19) — 10 hypotheses found."* This is not silent — a stale-but-present result must never be presented as if it were fresh.

### F. Distinct not-analyzed states (new capability, depends on Feature 06c)

Replace the single generic `_not_analyzed(section)` message with one that reflects what actually happened, using [Feature 06c](06c-stage-run-persistence.md)'s `stage_run_result` facts (queried the same two-step way as (E) — current run first, else most recent):

- **No `stage_run_result` fact at all for this stage, ever** → *"This category has no analyzer yet."* (matches today's message for Runtime/Infrastructure/CI-CD/etc. — features that don't exist yet).
- **`status="skipped"`, `detail` mentions `llm_provider not configured`** → *"LLM analysis was disabled for this run."*
- **`status="skipped"` or `"failed"`, any other `detail`** → *"Atlas attempted this analysis but it failed: {detail}."* — surfaces the real reason (e.g. `not_analyzed: llm_failed`) instead of hiding it.
- **`status="ok"`, `facts_produced=0`** → *"Atlas analyzed this repository for {section} and found nothing to report."* — a genuine, confirmed absence, distinct from a failure.

This is the direct fix for "les textes générés par les LLM sont inexistants" being indistinguishable from "il n'y a rien à trouver ici."

## Explicitly out of scope for this feature

- The interactive/navigable full-graph view (force-directed / cytoscape.js, **Proposition Q129's deferred half**) — per explicit decision, this stays deferred as a separate, later capability; this feature's Mermaid edges are a top-N static view, not a replacement for it.
- Any change to `generate_report`'s signature, the shared provenance/evidence rendering primitive, or the section list — this feature only changes what happens inside each section renderer's own function body.
- Any change to Feature 05/06's fact shapes (`centrality`, `hotspot_score`, etc.) — the renderer adapts to what's already shipped; it does not ask upstream features to add a `score` field.
- Any change to how `atlas analyze` itself runs, retries, or handles failures — cross-run fallback and distinct gap states are read-only presentation over what's already in the store; nothing here re-triggers analysis (see [14b](14b-agent-runs-analysis.md) for the unrelated, already-specified agent-side "run analyze if missing" behavior).

## Acceptance criteria

- A fixture `FactStore` with `technology_detected` (`name` key), `hotspot_score` (`combined` key), and `centrality` (`in_degree`/`out_degree` only) facts renders each with the correct, non-fallback value — no repository path appearing where a technology/score name is expected.
- A fixture with `imports`/`calls` facts between two of the top-N centrality nodes produces a Mermaid `A --> B` line; a fixture with two same-basename, different-path files produces two distinct Mermaid node IDs, not one.
- A fixture `dependency_cycle` fact with 3 `cycle_members` renders all 3, not just the subject.
- Onboarding narrative output contains no run-on concatenation — a test asserts sentence-ending punctuation or element separation between each assembled part.
- A fixture with facts for `run_id=A` (older, `created_at` earlier) and none for `run_id=B` (current) renders `run_id=A`'s facts under `run_id=B`'s report, with the fallback explicitly stated in the section's prose including the source run id and date.
- A fixture with a `stage_run_result` fact (`status="skipped"`, `detail="not_analyzed: llm_failed"`) for the current run renders that reason in the section body instead of the generic not-analyzed message; a fixture with `status="ok"`, `facts_produced=0` renders the distinct "found nothing" message; a section with no `stage_run_result` fact at all still renders today's "no analyzer" message unchanged.
- `uv run pytest` and `uv run ruff check .` pass.
