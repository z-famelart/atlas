# Feature 01b — Typed fact value schemas (stop the silent-fallback bug class)

## Why this is a separate feature, not a rewrite of Feature 01

Feature 01 (Facts & Evidence model) is **already implemented**. This is a purely additive new module — one new file, `facts/value_schemas.py` — plus optional accessor helpers. It does not change `Fact`, `Evidence`, `FactStore`, or any already-shipped producer/consumer code's required behavior.

## Why this exists

Four confirmed bugs this session, all the exact same root cause: a consumer read `fact.value.get("wrong_key", default)` for a key that doesn't match what the producer actually emits. `.get()` never raises on a typo/rename — it silently returns the fallback, so every one of these shipped, passed review, and passed tests, and was only found by manually diffing real stored facts against renderer/query code:

1. `html_report/renderer.py`: `.get("technology", ...)` vs. the real key `"name"` (`technology_detected`).
2. `html_report/renderer.py`: `.get("score", ...)` vs. the real key `"combined"` (`hotspot_score`).
3. `mcp_server/queries.py`: `.get("combined_score", ...)` vs. the same real key `"combined"` — a *different* wrong guess than #2, for the exact same fact type, in a completely different file.
4. A prior sort routine keyed on a nonexistent `"score"` for `centrality` facts (real keys: `"in_degree"`/`"out_degree"`).

A dedicated audit swept the entire codebase afterward and found no further live instances — but the mechanism that let all four ship unnoticed (untyped, unchecked dict access) is still exactly as present as it was before any of them were found. This feature closes that mechanism, not just the four instances of it.

Note what this is *not* fixing: every producer in this codebase already emits internally-consistent, correct `value` dicts — the audit's ground-truth table (below) confirms it. The defect was always on the *reading* side. So the fix belongs on the reading side too: a typed way to read a fact's `value` that fails loudly on a mismatch, instead of a bare `.get(key, default)` that fails silently.

## Depends on

Feature 01 (`Fact`, `FactStore` — already implemented, unchanged).

## Scope

### `facts/value_schemas.py` — one frozen/slotted dataclass per fact type (the audit's ground truth, made authoritative)

```python
@dataclass(frozen=True, slots=True)
class HotspotScoreValue:
    combined: float
    components_available: str
    components: dict[str, Any]

@dataclass(frozen=True, slots=True)
class CentralityValue:
    in_degree: float
    out_degree: float

# ... one per fact type already in use:
# technology_detected, language_detected, document_detected, git_repository_detected,
# git_churn, git_co_change, complexity, hotspot_score, hotspot_<name>_score, centrality,
# community, dependency_cycle, symbol_defined, stage_run_result, architecture_hypothesis,
# business_concept, business_workflow, glossary_term, onboarding_path
# (module-level and aggregated/module-level variants both included where Feature 05's
# aggregation produces a different shape than the file-level fact — see 05's
# aggregation.py for both shapes)
```

Every field name and type here is taken directly from the audit's verified ground truth (each producer's actual construction site), not re-derived or guessed. This module is the **single canonical source of truth** for what a fact type's `value` contains — the same role `Fact`/`Evidence` already play for the fact's outer shape.

### Typed accessor per fact type

```python
def hotspot_score_value(fact: Fact) -> HotspotScoreValue:
    """Raises TypeError if fact.value's keys don't match HotspotScoreValue exactly."""
    return HotspotScoreValue(**(fact.value or {}))
```

Because these dataclasses are frozen/slotted with no defaults (unless the real producer shape has an optional field, in which case the dataclass matches that exactly), constructing one from a dict with a missing or renamed key raises `TypeError` immediately — the same silent-fallback bug class becomes impossible to reproduce for any code that uses this accessor instead of raw `.get()`.

### Convention: new fact-consuming code must use these accessors (documented in README, not enforced by a new CI gate in this feature)

Add a short section to `specs/features/README.md`, the same style as the existing ["Logging" convention](README.md#logging-a-convention-every-feature-follows): new code reading a fact's `value` for one of the types above calls the typed accessor, not `fact.value.get(...)` directly. This is a documented convention for future work, not a retrofit requirement — see "Explicitly out of scope" below for why existing call sites aren't forced to migrate in this feature.

### A validation test that catches producer drift automatically

One test (or small test module) that, for each fact type with a registered schema, runs that type's real producer (using the same fixtures/harness each producing feature's own tests already use) and asserts the result's `value` dict keys match the schema's fields exactly (no more, no less). This is what would have caught, at commit time, any future rename on the *producer* side before a consumer ever had a chance to silently misread it — complementary to the accessor, which protects the *consumer* side.

## Explicitly out of scope for this feature

- **Retrofitting every already-shipped consumer** (`html_report/renderer.py`, `mcp_server/queries.py`, `hotspots/scorer.py`, `code_graph/aggregation.py`, `domain/selector.py`, etc.) to use the new accessors — the audit confirmed every one of them is currently correct. Forcing a mass rewrite of already-working, already-tested code for stylistic consistency isn't worth the regression risk; the accessors are available for any of them to adopt opportunistically later, not required by this feature. This feature's job is to make the *next* mistake impossible, not to touch the ones that didn't happen.
- Any new dependency (no `pydantic`, no `mypy`/strict static typing rollout) — plain dataclasses, matching every other typed shape already in this codebase (Feature 01's own `Fact`/`Evidence`, Feature 07's `StructuredPrompt`/`LLMCallResult`, etc.).
- Changing any producer's actual `value=` construction — every producer already emits the correct shape (per the audit); this feature only names and types what's already true.
- A runtime schema-version negotiation or migration mechanism — if a fact type's shape needs to change later, that's an ordinary additive-feature change to this module (add/adjust one dataclass), not a new capability this feature needs to anticipate.

## Acceptance criteria

- `facts/value_schemas.py` defines one dataclass per fact type listed above, fields matching the audit's ground-truth table exactly (cross-checked against each producer's actual construction site, not just copied from this spec without verification).
- Constructing e.g. `HotspotScoreValue(**wrong_dict)` where `wrong_dict` has `"combined_score"` instead of `"combined"` raises `TypeError` — a test proves this for at least the four fact types involved in this session's confirmed bugs, demonstrating each historical bug would have been caught immediately had the accessor been in use.
- The validation test (real producer output vs. registered schema) passes for every fact type that has both a schema and an existing producer test fixture to run it against.
- No existing test, renderer, or query function is modified as part of this feature (confirmed via diff — this is a pure addition, not a retrofit).
- `uv run pytest` and `uv run ruff check .` pass.
