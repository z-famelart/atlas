# Feature 11e — Narrative coherence: fix contradictory fallback prose and the "uncatalogued" noise wall

## Why this is a separate feature, not a rewrite of Feature 11/11b/11c/11d

Features 11/11b/11c/11d are **already implemented**. This feature fixes two concrete, evidence-backed readability defects found by reading two real generated reports (a raw `atlas-report-*.html` and an `atlas-synthesis` agent output, both against `crewlybase`) end to end — not by rewriting the fallback/gap-state logic Feature 11c already shipped, and not by touching `architecture/schema.py`'s `normalize_pattern` (Feature 08b) or its prompt (Feature 08b/08c). Per direct user feedback: *"les textes sont trop succincts, et forment à peine des phrases compréhensibles."*

## Depends on

Feature 11/11b/11c (HTML report, narrative prose, cross-run fallback — already implemented, this feature only edits prose-composition code inside `html_report/renderer.py`'s section renderers). Feature 08b (`architecture/schema.py`'s `normalize_pattern` — already implemented, this feature reads but does not change its output format).

## What was actually found (grounding for this spec)

Read directly from a real report (`atlas-report-1753d267-...html`, crewlybase) and its `FactStore`:

1. **Every section that uses cross-run fallback (Feature 11c, Q140c) reads as self-contradictory.** Example, Executive Summary's actual rendered prose: *"Detected 6 technologies: npm, flask, npm, github-actions, django, uv. No technology data for this run. Showing results from a previous analysis (run `a38537cb`, 2026-09-16 07:30) — 6 technology(ies) found."* The first sentence states the finding in the present tense as if it's this run's own result; the second sentence immediately says the opposite ("No technology data for this run"), then a third restates the same count already given in the first sentence. This exact pattern (content sentence in the present tense, followed by an unedited `_fallback_note` appendix) repeats verbatim in `_render_executive_summary`, `_render_system_map`, `_render_code_map`, `_render_hotspots`, `_render_domain`, `_render_git_evolution`, `_render_risks`, `_render_onboarding`, and `_render_glossary` — every one of the nine call sites that can trigger a fallback, not an isolated case.
2. **The Architecture section's narrative is a wall of repeated debug strings.** Real rendered prose (10 hypotheses, all forced to `pattern="uncatalogued"` by Feature 08b's `normalize_pattern`): `"(unrecognized pattern value: 'backend/src/crewlybase/apps/accounts/auth.py') (unrecognized pattern value: 'frontend/src/components/DevBar.tsx') (unrecognized pattern value: 'backend/src/crewlybase/urls.py') ..."` — ten near-identical fragments with no separators, none of them an actual sentence. `_render_architecture`'s prose loop (`html_report/renderer.py`) collects every fact's `pattern_description` verbatim into `prose_parts`, including the synthetic string `normalize_pattern` writes for debugging (`architecture/schema.py:36`, `f"(unrecognized pattern value: '{pattern}')"`) — a string designed to be inspected per-fact in the evidence drill-down (Q131/Q132), never meant to be concatenated into a paragraph.

Both defects are pure prose-composition bugs in `html_report/renderer.py` — the underlying facts, the fallback mechanism, and `normalize_pattern`'s data-level fix are all already correct and unchanged by this feature.

## Scope

### A. Coherent fallback sentence (fixes defect 1)

Replace the current "always append `_fallback_note` after the content sentence" pattern, duplicated across all nine call sites, with a single shared helper that picks **one** coherent framing instead of two juxtaposed ones:

- **No fallback** (current run has data): unchanged — existing present-tense content sentence only.
- **Fallback used**: exactly one sentence, past/fallback-framed from the start, e.g. *"No technology data for this run — showing 6 technologies from a previous analysis (run `a38537cb`, 2026-09-16 07:30): npm, flask, github-actions, django, uv."* The item list (technologies, top file, concept names, etc.) that used to sit in the now-removed present-tense sentence is folded into this single sentence instead of being dropped.

Concretely: a new helper (e.g. `_fallback_aware_narrative(content_items_desc: str, fb: tuple[str, datetime] | None, section_desc: str) -> str`) replaces the current two-call pattern (`parts.append(<content sentence>)` + `if fb: parts.append(_fallback_note(...))`) at all nine call sites; `_fallback_note` itself is either removed or absorbed into the new helper (its current signature/wording is not reused verbatim elsewhere, so no external contract breaks).

### B. Collapse synthetic "uncatalogued" descriptions in Architecture prose (fixes defect 2)

In `_render_architecture`'s prose loop: a `pattern_description` matching the synthetic prefix `normalize_pattern` writes (`"(unrecognized pattern value: '"`) is never appended to `prose_parts` verbatim. Instead, all hypotheses whose description matches this prefix are counted and summarized in **one** sentence, e.g.: *"Atlas flagged 10 individual files as architecturally notable but could not assign a named pattern to any of them — see the fact rows below for detail."* A hypothesis with a real, non-synthetic `pattern_description` (free text the model actually wrote) is unaffected and still shown verbatim, same as today. If a report mixes both (some real descriptions, some synthetic), the real ones are shown as today and the synthetic ones are summarized as the one added sentence — not one added per synthetic hypothesis.

## Explicitly out of scope for this feature

- `architecture/schema.py`'s `normalize_pattern` or its debug-string format — this feature only changes how the renderer *uses* that string, not what it contains; the prefix match in scope B is read-only against the existing, already-shipped format.
- Any change to `_query_fallback`, `_gap_message`, or the distinct not-analyzed states (Feature 11c, Q180b) — those already correctly distinguish "never run" / "LLM disabled" / "LLM failed" / "found nothing"; this feature only touches the sentence built when a fallback *succeeds* (facts were found, just from an older run).
- Making the LLM stop returning file paths in `pattern` more reliably than 08b/08c's already-shipped prompt guidance — that's a model-compliance concern (08b/08c's scope), not a rendering concern; this feature makes the renderer's output readable regardless of how often the model still gets it wrong.
- Any change to which sections exist, their `nav_items`, or `generate_report`'s signature.

## Acceptance criteria

- A fixture with `technology_detected` facts only under an older `run_id` (fallback triggered) renders exactly one narrative sentence for that section, starting with "No … for this run", that includes both the fallback attribution (run id, date) and the actual technology names — no second sentence restating the same count in the present tense.
- A fixture with facts under the current `run_id` (no fallback) is unaffected — same present-tense sentence as before this feature.
- A fixture with 3 `architecture_hypothesis` facts whose `pattern_description` all match the `normalize_pattern` synthetic prefix renders exactly one summary sentence mentioning "3", not three concatenated debug strings.
- A fixture mixing 1 real (non-synthetic) `pattern_description` with 2 synthetic ones renders the real description verbatim plus one summary sentence for the 2 synthetic ones — never the synthetic strings verbatim.
- `uv run pytest` and `uv run ruff check .` pass.
