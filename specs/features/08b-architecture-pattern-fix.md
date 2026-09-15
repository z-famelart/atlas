# Feature 08b — Fix architecture pattern generation

## Why this is a separate feature, not a rewrite of Feature 08

Feature 08 is **already implemented**. This feature fixes a concrete content-generation defect found by reading real `architecture_hypothesis` facts from a production run (ggshield, via local Ollama/qwen3), not by rewriting Feature 08's shipped `ArchitectureHypothesis`/`ArchitectureResponse` schema or prompt-building interface.

## What was actually found

Real stored `architecture_hypothesis` facts, from a run where the stage reported `status="ok"`:

```json
{"pattern": "ggshield/verticals/secret/output/secret_*.py", "confidence": 0.8, "fact_ids": [...], "pattern_description": null}
{"pattern": "ggshield/verticals/ai/agents/*.py", "confidence": 0.7, "fact_ids": [...], "pattern_description": null}
```

`pattern` is supposed to be one of Feature 08's catalogue values (`layered`, `hexagonal`, `microservices`, `modular_monolith`, `event_driven`, `mvc_mvvm`, `big_ball_of_mud`, or `uncatalogued`) per `architecture/schema.py`'s `_CATALOGUE`. Instead it's a file glob describing a community/cluster of files — not an architectural pattern name at all. `pattern_description` (meant to carry the free-text label when `pattern="uncatalogued"`) is always `null`. The model (local Ollama/qwen3, per Décidé Q168) is not following the schema's intent — it's answering a different, unasked question ("what files does this hypothesis concern") instead of naming a pattern.

This is a genuine content-generation bug (the prompt/schema description isn't constraining the model enough, likely because a weaker local model needs more explicit guidance than `ClaudeCodeProvider` did), not a rendering bug — no fix in Feature 11/11c can repair data that's wrong at the source. Per direct decision, fixed together with the report fidelity work rather than deferred.

## Depends on

Feature 08 (architecture interpretation — already implemented, this feature changes `architecture/analyzer.py`'s prompt-building and adds a validation step; `ArchitectureHypothesis`/`ArchitectureResponse`'s shape is unchanged).

## Scope

### Prompt fix

Strengthen `build_prompt`'s instructions so the model cannot plausibly confuse "which files this hypothesis is about" (already covered by `fact_ids`) with "what architectural pattern this is" (the `pattern` field). Concretely: make `CATALOGUE_DESCRIPTION` (already built into the prompt today) more prominent and paired with an explicit negative instruction and a worked example, e.g.:

> `pattern` must be **exactly one** of: layered, hexagonal, microservices, modular_monolith, event_driven, mvc_mvvm, big_ball_of_mud, uncatalogued. It is never a file path, a glob, a directory name, or anything else — those belong in `fact_ids` (which files support this hypothesis) and, if `pattern="uncatalogued"`, in `pattern_description` (a short free-text label for the pattern itself, not a file listing).

This is a prompt-content change only — no change to `StructuredPrompt`, `LLMOrchestrator`, or any Feature 07 type.

### Defensive validation (new: don't trust an out-of-catalogue value blindly)

Independent of whether the prompt fix fully solves it for every model (weaker/future local models may still drift), add a validation step after the LLM response is structured, before it's turned into facts: if `pattern` is not one of the known catalogue values, treat it the same as if the model had said `"uncatalogued"` — move the model's actual (invalid) string into `pattern_description` (prefixed, e.g. `"(unrecognized pattern value: 'ggshield/verticals/.../*.py')"`) and set `pattern="uncatalogued"`. This guarantees `pattern` is **always** a valid catalogue value in stored facts, regardless of what the model actually returns, so [Feature 11c](11c-report-fidelity-fixes.md) (and anything else reading these facts) never has to defend against a garbage `pattern` value — the guarantee lives at the source, not at every consumer.

## Explicitly out of scope for this feature

- Any change to `ArchitectureHypothesis`, `ArchitectureResponse`, or `_CATALOGUE`'s values (the `big_ball_of_mud` addition from the earlier session stays as-is) — only the prompt text and a post-response validation step change.
- Any change to Feature 07's citation validator, caching, or budget — this feature's validation step is architecture-specific (`pattern` catalogue membership), layered on top of, not instead of, Feature 07's existing citation validation.
- Fixing model reliability in general (e.g. citation hallucination causing whole responses to be rejected, per the known Ollama/qwen3 issue) — that's a separate, broader LLM-reliability concern, not this feature's narrow scope (a single field's content quality).
- Re-running past analyses — this feature only affects facts produced by future `atlas analyze` runs; existing `architecture_hypothesis` facts already in a store (e.g. the ones read while diagnosing this) are not retroactively fixed.

## Acceptance criteria

- A test with a fake `LLMProvider` returning `pattern="some/glob/*.py"` produces a stored fact with `pattern="uncatalogued"` and `pattern_description` containing the original invalid string — never the raw glob stored as-is in `pattern`.
- A test with a fake `LLMProvider` returning a valid catalogue value (e.g. `"layered"`) is unaffected — passes through unchanged.
- The updated prompt text is asserted (via a test on `build_prompt`'s output) to include the strengthened catalogue instruction and negative example.
- `uv run pytest` and `uv run ruff check .` pass.
