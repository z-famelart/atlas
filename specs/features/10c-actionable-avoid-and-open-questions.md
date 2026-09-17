# Feature 10c — Make `avoid_initially`/`open_questions` actionable, not just labels

## Why this is a separate feature, not a rewrite of Feature 10/10b

Feature 10/10b are **already implemented**. This feature fixes a concrete content-generation defect found by reading a real synthesis output, in `onboarding/analyzer.py`'s prompt text only — no schema change (`OnboardingPathResponse`/`AvoidItem`'s shape is unchanged, `open_questions` stays `list[str]`).

## Depends on

Feature 10/10b (onboarding path synthesis — already implemented, this feature only changes `onboarding/analyzer.py`'s `_INSTRUCTIONS` prompt text).

## What was actually found (grounding for this spec)

A real synthesis output relayed this verbatim from a stored `onboarding_path` fact, per direct user feedback ("je ne sais pas quoi faire de cette information, elle n'est pas assez précise"):

> Avoid initially (per Atlas): `test_undo_an_edit_restores_the_previous_values()`, `test_set_ops_window_end_before_start_rejected()`. Open questions Atlas flagged: how shifts are validated before saving; the relationship between `ShiftIn` and the DB model.

Two distinct causes, both in `onboarding/analyzer.py`:

1. `AvoidItem` already has a `rationale` field (stored in the fact, available via MCP's `_fact_to_dict`), but `_INSTRUCTIONS` only tells the model *when* to include an item ("components that are high-complexity or low-centrality and irrelevant to a first pass") — never what the `rationale` text itself should actually explain. In practice the model produces a `rationale` that just restates the category, not a reason specific to that item.
2. `open_questions` is a plain `list[str]`, and the instruction ("explicit unresolved items — things you cannot determine from the available facts") only asks for the unknown itself, never why it matters. A string like `"how shifts are validated before saving"` names the gap without saying why a newcomer should care or what it blocks.

Both are prompt-content gaps, not rendering bugs — the renderer/agent-relay layers (Feature 11/14) already surface whatever text the model produces; the text itself just isn't actionable.

## Scope

### Strengthen `_INSTRUCTIONS` for `avoid_initially`

Require `rationale` to be a concrete, item-specific reason, not a restated category — e.g.: *"`rationale` must explain the specific reason for this item, not just restate a category (e.g. 'high complexity, unrelated to the save/create path a newcomer needs first' rather than 'high complexity')."*

### Strengthen `_INSTRUCTIONS` for `open_questions`

Require each item to be a self-contained sentence naming both the unknown and why it matters — e.g.: *"Each `open_questions` item must be a complete sentence stating both what is unresolved and why it matters (what it blocks, or what risk ignoring it carries) — not a bare noun phrase. E.g. 'how shifts are validated before saving — unresolved, and central to any change touching `ShiftIn` without risking silently invalid data' rather than 'how shifts are validated before saving'."*

No dataclass/schema change — `open_questions` stays `list[str]`; the added context lives in the string itself, same as `AvoidItem.rationale` already does.

## Explicitly out of scope for this feature

- Any change to `OnboardingPathResponse`, `AvoidItem`, `EntryPoint`, or `TimeBoxed`'s fields — this is a prompt-wording change only.
- How the agent/renderer relay `rationale`/`open_questions` text once produced — the "Atlas findings" relay layer surfacing the full `rationale` (not just the component name) is [Feature 14d](14d-agent-grounds-interpretation-in-own-reading.md)'s scope, not this one; this feature only makes the source text worth relaying in full.
- Feature 07's citation validator or Feature 10b's grounding filter (`_drop_ungrounded`) — unchanged; this feature doesn't touch which items are kept or dropped, only the quality of the text inside items that are kept.

## Acceptance criteria

- `build_prompt`'s output (asserted via a test) includes the strengthened `avoid_initially` and `open_questions` instructions above.
- No change to `OnboardingPathResponse`/`AvoidItem`/`EntryPoint` field shapes — existing tests for those dataclasses pass unchanged.
- `uv run pytest` and `uv run ruff check .` pass.
