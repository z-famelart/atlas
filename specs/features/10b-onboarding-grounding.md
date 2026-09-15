# Feature 10b — Ground `avoid_initially`/`entry_points` claims, or drop them

## Why this is a separate feature, not a rewrite of Feature 10

Feature 10 (onboarding path synthesis) is **already implemented**. This is an additive fix to `onboarding/analyzer.py`'s input-fact selection and prompt, plus one new post-response check in `onboarding/stage.py` — not a change to `OnboardingPathResponse`'s schema shape.

## What was actually found (grounding for this spec)

Read directly from a real `atlas-synthesis` run against a Django backend: `where_to_start()`'s `avoid_initially` told a newcomer to avoid "Team Management" because *"the system is not currently configured to manage teams."* This is false — `FestivalTeam`, `FestivalCoAdmin`, and `ApplicationTeamChoice` are live, wired-in models with their own service files, and the same run's `business_workflow` facts already included a "Festival Team Management Workflow" — the model contradicted evidence sitting right next to its own output.

Root cause, found by reading the actual prompt-building code (`onboarding/analyzer.py`):

1. `_INPUT_FACT_TYPES` — the facts fed to the LLM for this synthesis — is `("centrality", "hotspot_score", "architecture_hypothesis", "business_workflow", "business_concept")`. **`symbol_defined` is not included.** The model never sees which classes/models actually exist in the codebase — only aggregate per-file numeric scores and whatever the (frequently unreliable, per this session's other findings) architecture/domain stages produced. It has no way to know whether "team management" is configured or not, yet the prompt asks it to name specific components to avoid with a specific rationale — inviting exactly this kind of confident fabrication when the evidence doesn't support a specific claim.
2. Feature 07's citation validator (`llm/citation.py`, already shipped, unchanged by this feature) only checks that a cited `fact_id` **exists** in the store (`store.fact_exists(fid)`) — it has no way to check whether the free-text `rationale` sitting next to that citation is actually *supported* by what the cited fact says. Worse: `validate_citations` returns `(True, [])` when a response has **zero** `fact_ids` anywhere (`if not cited: return True, []`) — so a `rationale` written with an empty `fact_ids` list isn't rejected at all; there's currently no requirement that a specific, falsifiable claim about a specific component actually cite anything.

This is the same "never pretend to know" principle (Product Brief principle 5) the rest of this project already takes seriously elsewhere — this feature closes a real gap in how it's enforced for one specific, high-risk shape: a confident claim about a specific named component.

## Depends on

Feature 10 (onboarding path synthesis, already implemented — this changes `analyzer.py`'s input selection/prompt and adds one check in `stage.py`, not `OnboardingPathResponse`'s shape). Feature 07's citation validator (already implemented, reused unchanged — this feature adds a *stage-local* check on top of it, not a change to the shared validator, since the right requirement — "a component-specific claim must cite something" — doesn't hold for every field Feature 07's validator sees across every stage, e.g. `open_questions` is explicitly meant to name things that *aren't* known from facts).

## Scope

### Feed the model what it needs to actually know what exists

Add `symbol_defined` to `onboarding/analyzer.py`'s `_INPUT_FACT_TYPES`. This gives the model real, concrete evidence of which classes/functions exist per file — the category of evidence that would have made "the system is not configured to manage teams" an obviously unsupportable claim to generate in the first place, instead of the model filling the gap with confident-sounding fiction.

### Prompt: forbid unsupported absence/capability claims

Add an explicit rule to `_INSTRUCTIONS` (alongside the existing `avoid_initially`/`entry_points` rules): a claim about a specific named component (why to read it, why to avoid it) must cite the specific fact(s) that support *that exact claim* — not just any fact from the input set — and the model must not assert that a capability/feature is absent or unconfigured unless the provided facts positively support that absence (which, given this framework's facts are almost entirely "X exists with property Y," they usually won't — so in practice this steers the model toward not making such claims at all, rather than trying to teach it to prove a negative).

### Stage-level enforcement: drop ungrounded component claims rather than storing them

In `onboarding/stage.py`, after Feature 07's existing citation validation passes (unchanged), add one additional check specific to this stage: any `EntryPoint` or `AvoidItem` whose `fact_ids` list is empty is dropped from the stored fact's `entry_points`/`avoid_initially` lists before insertion (not rejected outright — the rest of a genuinely useful response, e.g. a well-grounded `recommended_workflow`, still gets stored; only the specific ungrounded item is removed). If dropping empty-citation items leaves `entry_points` empty, that's fine — Feature 11c's existing not-analyzed/gap-state handling already covers an onboarding_path fact with less content than expected; this feature does not add a new gap state, it just stops fabricated-but-uncited claims from reaching storage in the first place.

## Explicitly out of scope for this feature

- Any change to Feature 07's shared citation validator (`validate_citations`) — it stays exactly as shipped, existence-checking only; this feature's stricter "must actually cite something" rule is intentionally scoped to onboarding's two component-claim fields only, not applied globally (a blanket rule would incorrectly reject legitimately citation-free fields like `open_questions` in this same schema, or fields in other stages this feature hasn't audited).
- Verifying that a cited fact's *content* actually supports the claim text (true semantic fact-checking) — out of scope, and arguably not solvable without another LLM call to check the first one; this feature only requires *some* citation to exist for a specific-component claim, closing the "zero citations, still accepted" gap, not building a full claim-verification system.
- Any change to Feature 08/08b/08c (architecture) or Feature 09 (domain) — this feature only touches the onboarding stage's own input selection, prompt, and post-response filtering.
- Retroactively fixing already-stored `onboarding_path` facts from past runs — this feature only affects facts produced by future `atlas analyze` runs.

## Acceptance criteria

- `onboarding/analyzer.py`'s `_INPUT_FACT_TYPES` includes `symbol_defined` — a test confirms `collect_input_facts` returns `symbol_defined` facts when present in the store.
- A test on `build_prompt`'s output asserts the new instruction (component claims must cite supporting facts; no unsupported absence/capability claims) is present.
- A test with a fake `LLMProvider` returning an `AvoidItem`/`EntryPoint` with an empty `fact_ids` list proves that item is dropped from the stored `onboarding_path` fact's `avoid_initially`/`entry_points`, while a sibling item in the same response with valid, non-empty `fact_ids` is still stored — proving this is a targeted filter, not a reject-the-whole-response check.
- A test proves this stage-level filter runs *after* Feature 07's existing citation validation (an item citing a nonexistent fact_id is still rejected the way it already is today — unchanged behavior), not instead of it.
- `uv run pytest` and `uv run ruff check .` pass.
