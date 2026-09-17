# Feature 14d — "My read" fills Atlas's interpretive gaps by reading the repo, not by describing them

## Why this is a separate feature, not a rewrite of Feature 14/14b/14c

Feature 14/14b/14c are **already implemented**. This feature fixes a concrete instruction defect in `.claude/agents/atlas-synthesis.md` found by reading a real synthesis output judged "à côté du point" (beside the point) — no change to the MCP query sequence, the startup sequence, or the "Atlas findings" section's provenance rules.

**Correction, narrowing this feature's scope from its first draft**: this feature's Scope A originally covered *both* "no analyzer exists" and "Atlas's LLM stage (architecture/domain) came up thin" as cases where the agent should read source files itself. Per direct correction: for domain understanding specifically, the domain stage coming up thin is Atlas's own bug to fix, not something a synthesis agent should be expected to compensate for — see [Feature 09b](09b-domain-candidate-selection-fix.md), which found and fixes the actual root cause (a candidate-selection budget that didn't bound what it claimed to, feeding a weak local model ~2x its intended context with no coverage instruction). This feature's Scope A now covers only **architecture** stage thinness (Feature 08's own known, separately-documented model-reliability limit — "uncatalogued" patterns with no further LLM-reliability fix planned, per 08b's explicit scope) and true no-analyzer categories — domain is out of this feature's scope A as of this revision, since 09b addresses it at the source and an agent compensating by reading files is no longer the expected mitigation there.

## Depends on

Feature 14/14b/14c (`atlas-synthesis` agent — already implemented, this feature only edits `.claude/agents/atlas-synthesis.md`'s "My read" instructions and one bullet in "Content to include in Atlas findings"). [Feature 10c](10c-actionable-avoid-and-open-questions.md) (makes the underlying `avoid_initially`/`open_questions` text worth relaying in full — this feature is what actually relays it).

## What was actually found (grounding for this spec)

A real synthesis output's "My read" section, in full, per direct user feedback that it "misses the point" (a materially more serious problem than the wording issue Feature 10c/11e address, per the same feedback):

> The architecture stage produced ten "uncatalogued" tags and no synthesized pattern — it's not wrong, it's just empty of content beyond "these files exist and are notable." The domain stage found four facts, three of which are about festival co-admin management specifically, and nothing about applications review/accept-reject flow, scheduling rules, or registration forms — despite those being core to an MVP push. I would not use either stage as a substitute for reading `applications/services.py` and `festivals/services/core.py` directly; use them only as a hint of which files an LLM found "notable" on a first pass.

This paragraph correctly diagnoses that Atlas's architecture/domain stages came up thin — but then, instead of doing what it just said a reader should do (read `applications/services.py` and `festivals/services/core.py`), it stops and points the reader there instead. The agent is a coding agent with direct filesystem access to `repo_path` — nothing stops it from actually opening those two files itself and writing the architecture/domain interpretation a reader needs. Root cause, in `.claude/agents/atlas-synthesis.md`:

- The "My read" section's instructions say: *"If there are `not_analyzed` gaps, say what it would want to know but cannot."* This sentence conflates two different situations without distinguishing them: a gap with **no analyzer at all** (Runtime, Infrastructure, CI/CD — genuinely nothing any reading could produce today) versus a gap that is **Atlas's LLM stage coming up thin** (architecture/domain here) — which the agent, unlike Atlas's own stages, can actually close by reading the flagged source files directly. The instruction as written licenses treating both the same way: describe it and move on.
- Separately, in "Atlas findings": the relay content list doesn't say to include each `avoid_initially` item's `rationale` — a real synthesis relayed a bare list of component/test names (`"Avoid initially (per Atlas): test_undo_an_edit_restores_the_previous_values(), ..."`) even though the underlying fact already carries a `rationale` per item, reachable via MCP's `_fact_to_dict` with no loss.

## Scope

### A. "My read" must ground a thin-Atlas-stage gap in the agent's own reading

Replace the single "say what it would want to know but cannot" bullet with two explicit cases:

- **Genuinely unknowable this session** (no analyzer exists for the category at all, e.g. Runtime/Infrastructure/CI-CD/Data/Observability/Tests) — unchanged: say so, and what it would want to know.
- **Architecture came up "uncatalogued" with no synthesized pattern** (Feature 08's own known model-reliability limit, not something a prompt/selection fix can close — see 08b's explicit scope) — the agent opens and reads the specific files MCP flagged as relevant (from `get_hotspots`, `get_component`, or the hypothesis's own `fact_ids`) and writes its own grounded architectural read of those files in "My read", not a description of the stage being empty. Domain understanding is explicitly **not** in this bullet — [Feature 09b](09b-domain-candidate-selection-fix.md) fixes it at the source, so a domain gap should be rare after that lands; if one still occurs despite 09b (e.g. a repository large/unusual enough that even a correct budget and coverage instruction aren't enough), the same "read it yourself" principle still applies as a last resort, but it is no longer the expected, routine mitigation.

This directly enforces the "My read" section's existing (already-decided, Q154b) mandate — *"the agent must take a position... not just reformulate what MCP returned"* — for the one case (architecture) where no upstream fix removes the need for it.

### B. "Atlas findings" relays `rationale`, not just the component name

Add to the "Content to include in Atlas findings" list: when relaying `avoid_initially` (and `entry_points`) items from `where_to_start()`, always include each item's `rationale` field alongside the component/test name — never a bare name-only list. The `rationale` is already present in the fact value and already reachable via MCP with no additional query; this is a relay-completeness fix, not a new capability.

## Explicitly out of scope for this feature

- The MCP query sequence, startup sequence (Ollama detection, stale-store check), or provenance rules — unchanged.
- The underlying `onboarding_path` fact's text quality (whether `rationale`/`open_questions` are themselves well-written) — that's [Feature 10c](10c-actionable-avoid-and-open-questions.md)'s scope; this feature only ensures whatever text exists gets relayed in full.
- Any change to Feature 08/09's own prompts or `normalize_pattern` (Feature 08b) — this feature doesn't try to make Atlas's own stages richer; it makes the agent compensate by reading the repo itself when they're thin, which it already has the access to do.
- A hard rule to read *every* flagged file in every synthesis — the agent still uses judgment on which files are worth reading given the specific gap (same "hint, not proof" framing already correct in the example above), it just must not stop at the hint when it can go further.

## Acceptance criteria

- `.claude/agents/atlas-synthesis.md`'s "My read" section explicitly distinguishes "no analyzer exists" from "Atlas's LLM stage came up thin" and requires reading the flagged files directly for the latter case, with an explicit negative example (pointing the reader elsewhere instead of reading the file oneself is called out as the failure mode to avoid).
- The "Atlas findings" content list explicitly requires relaying `avoid_initially`/`entry_points` `rationale`, not just the component/test name.
- No change to any other section of the agent definition (MCP query sequence, startup sequence, provenance rules, HTML output shape/CSS, output destination).
