# Feature 11d — Code Map: community graph (size, links, importance)

## Why this is a separate feature, not a rewrite of Feature 11/11b/11c

Features 11/11b/11c (HTML report) are **already implemented**. Per the [regeneration contract](README.md#regeneration-contract), this feature replaces `_render_code_map`'s body with a real aggregated visualization, additively — it does not touch `generate_report`'s signature, the other section renderers, or the shared evidence-panel/provenance-badge JS/CSS (it reuses them).

This exists because, per direct user feedback, today's Code Map section is not actually a map: it lists up to 30 raw `community` facts — one per **file**'s community membership, often many duplicates of the same `community_id` — with no aggregation, no sizes, no relationships between communities. On a real repository (ggshield) there are 374 distinct communities; the current section conveys none of that structure.

## Depends on

Feature 05 (Code graph — `community`/`centrality` facts, and `imports`/`calls` relation facts, already implemented, unchanged). Feature 11c (`_query_fallback`, `_gap_message`, the evidence-panel/provenance CSS-JS primitives — reused, not duplicated).

## Goal

Replace Code Map's fact-listicle with a real **community graph**: node size = community size (file count), a visual encoding of community **importance** (aggregate centrality of member files), and edges showing the relationships between communities (weighted by how many cross-community import/call relations connect them) — per direct request: *"je veux que ça donne un graph avec la taille des communautés, les liens entre elles, leurs importances."*

## Scope

### Community aggregation (render-time, no new stored fact type)

Computed the same way System Map's centrality combination is already computed today (a renderer-side combination over existing facts, not a new analyzer output — see Feature 11c's precedent): group `community` facts by `community_id`, and for each community compute, purely by reading already-stored facts:

- **`size`** — count of member files (count of `community` facts sharing that `community_id`).
- **`importance`** — sum of `in_degree + out_degree` (from `centrality` facts) across the community's member files. Two distinct dimensions, both requested explicitly: size is file count, importance is aggregate connectedness — never conflated into one number.
- **Membership list** — the file paths, used for (a) computing inter-community edges below and (b) the evidence panel.

### Inter-community edges

For every `imports`/`calls` fact whose subject file and object file belong to **different** communities (per the grouping above), increment a directed edge weight for the `(community_a, community_b)` pair. This mirrors exactly how Feature 11c already computes file-level edges for the System Map diagram — same relation fact types, same "both endpoints must be in the selected set" rule, just aggregated one level up (community instead of file).

### Top-N selection (same pattern as System Map's top-N, same reason: real repos have hundreds of communities)

Select the top 20 communities by `size` (Proposition-level default, not a Décidé product requirement — revisit only if real usage shows 20 is wrong). Communities outside the top 20 are not drawn individually; the section's narrative states how many were omitted (e.g. *"20 largest communities shown; 354 smaller communities not pictured."*). Edges are only drawn between two selected communities — a relation to an unselected community is not shown, same rule Feature 11c already established for the System Map.

### Rendering: inline SVG bubble graph, not Mermaid

Mermaid (already vendored per Feature 11b) has no way to encode a continuous value as node size — it can only declare/label nodes. This feature generates a small, deterministic, self-contained **inline SVG** instead (no new dependency, no network fetch, consistent with the offline requirement already decided for this report — Q137/Q138):

- **Layout**: communities placed evenly around a circle (deterministic — ordered by `community_id` for stable output across regenerations, per the [regeneration contract](README.md#regeneration-contract)'s determinism rule), not a force-directed/interactive layout — that stays deferred (Proposition Q129, unchanged).
- **Size**: bubble radius proportional to `sqrt(size)` (area, not radius, scales linearly with file count — standard bubble-chart practice, avoids visually overstating large communities).
- **Importance**: bubble fill color on a light→dark single-hue scale, normalized against the min/max `importance` among the *selected* (top-20) communities — so color is always meaningful for what's actually drawn, not skewed by the 354 unselected outliers.
- **Both size and importance are also written as plain text** next to/inside each bubble (e.g. `"Community 12 — 84 files, importance 312"`) — the visual encoding is a supplement to the number, never a replacement for it (a color scale alone isn't reliably readable; per evidence-first, the actual figure must always be present).
- **Edges**: straight lines between bubble centers, stroke width scaled by the directed edge weight (clamped to a reasonable min/max so one huge weight doesn't make every other edge invisible).

### Evidence drill-down (reuses the existing mechanism, doesn't reinvent it)

Each bubble is clickable, using the exact same `data-evidence`/`onclick="showEvidence(this)"` mechanism every other fact-row already uses (Feature 11's shared primitive) — but since a community isn't a single `Fact`, its `data-evidence` payload is the aggregated evidence list of its member files' `community` and `centrality` facts (same JSON shape the evidence panel already renders, just multiple facts' worth concatenated). Clicking a bubble shows exactly what it's made of, consistent with the evidence-first principle — no aggregate number is presented without a way to see what it's built from.

### Cross-run fallback and gap states (reused unchanged from Feature 11c)

Code Map's query for `community`/`centrality`/relation facts uses Feature 11c's existing `_query_fallback` (current run, else most recent successful run, explicitly labeled) and `_gap_message` (distinguishing no-analyzer / LLM-disabled / failed / genuinely-empty) exactly as already implemented — this feature does not add a second fallback mechanism.

## Explicitly out of scope for this feature

- Interactive pan/zoom/drag, force-directed physics, or any JS graph library (cytoscape.js etc.) — still the deferred **Proposition Q129** half; this feature's SVG is static, generated once at report-build time, same "offline single file" shape as everything else in the report.
- Showing the full (non-top-N) community set as a graph — only the top-20 view; the omitted count is stated in prose, not visualized.
- Any change to how communities are detected or how `centrality`/`community` facts are computed — Feature 05's `compute_centrality`/`detect_communities` are untouched; this feature only aggregates their already-stored output at render time.
- A configurable top-N (CLI flag, config file entry) — hard-coded default for this feature; making it configurable is a separate, later concern if ever needed.
- Symbol-level detail within a community (the old per-symbol fact-list rows) — this feature's graph is community-level only; if per-symbol browsing inside a community is wanted later, that's a separate drill-down feature, not this one.

## Acceptance criteria

- A fixture `FactStore` with `community` facts across more than 20 distinct `community_id`s produces an SVG with exactly the top 20 by file count, and the section's prose states the count of omitted communities.
- Bubble radius in the generated SVG is proportional to `sqrt(size)` (a test asserts the ratio between two known-size communities' radii matches `sqrt(size_a/size_b)`, not `size_a/size_b`).
- A fixture with two communities of different aggregate `in_degree+out_degree` produces two different fill colors, and a test confirms color is normalized against the selected set's own min/max, not some global constant.
- A fixture with `imports`/`calls` facts crossing two selected communities produces an SVG edge between them; a fixture where the cross-community relation involves an unselected (below top-20) community produces no edge for that relation.
- Every bubble's `data-evidence` attribute, when clicked (verified via the existing evidence-panel test pattern, not necessarily a browser test), resolves to the underlying member files' `community`/`centrality` facts.
- Cross-run fallback and the four gap-state messages behave identically to how Feature 11c already tests them for other sections (reuse, don't reimplement, the same test helpers).
- No `<script src="http...">`/`<link href="http...">` — the SVG is inline, no new external reference, consistent with the report's existing offline test.
- `uv run pytest` and `uv run ruff check .` pass.
