# Feature 07b — Ollama local provider

## Why this is a separate feature, not a rewrite of Feature 07

Feature 07 (LLM orchestration framework) and Feature 08 (Architecture interpretation) are **already implemented and shipped** (`src/project_intel/llm/`, `ClaudeCodeProvider` as the current default). Per the [regeneration contract](README.md#regeneration-contract), a feature's spec is a stable interface once built — rewriting Feature 07's spec to describe a provider that doesn't exist in the shipped code, or to claim a different default than what's actually running, breaks that contract for no reason: nothing requires touching Feature 07 itself to add a new provider.

This feature is purely additive: one new `LLMProvider` implementation, added the same way Feature 07's own spec already anticipated ("a local LLM provider will be added later, without re-discussing this choice or changing the `LLMProvider` interface" — Q94). It changes nothing about `LLMProvider`, `StructuredPrompt`, `LLMCallResult`, `BudgetConfig`, `BudgetTracker`, the citation validator, or the cache — all already shipped by Feature 07 and reused unmodified.

## Depends on

Feature 07 (LLM orchestration framework — already implemented). Does not depend on Feature 08, 09, or 10; those consume whatever provider is configured without knowing which one it is.

## Goal

Add `OllamaProvider`, a second real `LLMProvider` implementation talking to a local Ollama server, per **Décidé Q168** (resolved 2026-09-14: the user has Ollama running locally with a Qwen model installed). Selectable in configuration alongside the already-shipped `ClaudeCodeProvider` and `DisabledProvider` — this feature does not change which one is the default; that's a separate, later decision the user can make once this lands (see "Explicitly out of scope").

## Scope

### `OllamaProvider` (implements the existing `LLMProvider` Protocol, unchanged)

```python
class OllamaProvider:
    provider_id = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: int = 120) -> None: ...

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]: ...
```

Same shape as the shipped `ClaudeCodeProvider` (`src/project_intel/llm/providers.py`): builds a full prompt from `StructuredPrompt.instructions`/`.content` plus a schema description, calls the model, parses the JSON response, structures it into `schema` via `cattrs`, and returns `LLMCallResult(status="ok", value=...)` — or `LLMCallResult(status="not_analyzed", reason="llm_failed")` on any error (timeout, connection refused, malformed JSON, schema mismatch), exactly mirroring `ClaudeCodeProvider`'s exception handling so callers see identical failure behavior regardless of which provider is configured.

`model` is a **required constructor argument, never a hard-coded default in this feature's code** — which Qwen tag is actually installed (e.g. `qwen2.5:14b`) is a fact about the user's machine, not something this spec or its implementation should assume. Whatever wires `OllamaProvider` into the pipeline (Feature 13's config loading, or a manual instantiation in the meantime) is responsible for supplying it, e.g. via an `OLLAMA_MODEL` environment variable or config field.

### Requesting structured output

Calls Ollama's `/api/generate` or `/api/chat` HTTP endpoint with the `format` parameter set to constrain the output — a JSON-schema constraint if the installed Ollama version supports it, otherwise plain `format: "json"`. Regardless of which is used, this feature **does not add or bypass any validation**: Feature 07's existing schema structuring (`cattrs`) and the citation validator (already applied uniformly to every provider's response, per Feature 07's `LLMOrchestrator`) run exactly as they do for `ClaudeCodeProvider` — this feature adds no provider-specific validation path.

### Context-window awareness (optional helper, not a change to `BudgetConfig`)

`BudgetConfig.tokens_per_category` (Feature 07, already shipped) is a plain `dict[str, int]` set by whoever configures the run — this feature does not change that type or add automatic introspection into the budget-tracking path itself (`BudgetTracker` stays exactly as shipped). What this feature adds is a **standalone helper**, not wired into the hot path:

```python
def suggest_ollama_budget(model: str, base_url: str = "http://localhost:11434") -> int | None: ...
```

Calls Ollama's `/api/show` for the configured model and returns a conservative token budget derived from its reported context window (leaving margin for prompt scaffolding and output), or `None` if introspection fails for any reason. Whoever configures `BudgetConfig` (a human, or later Feature 13's config loading) may call this to pick a sensible number for the `"ollama"`-routed categories — it is advisory, never required, and never called automatically inside `OllamaProvider.complete()`.

## Explicitly out of scope for this feature

- Changing `LLMProvider`, `StructuredPrompt`, `LLMCallResult`, `BudgetConfig`, `BudgetTracker`, the cache, or the citation validator — all already shipped by Feature 07, reused as-is.
- Changing the default provider — `ClaudeCodeProvider` remains whatever Feature 07/13's wiring currently selects by default; flipping the default to `OllamaProvider` (if ever wanted) is a separate, later decision, not part of this feature, and would touch Feature 13's config-loading defaults, not this one.
- Automatic cross-provider fallback (e.g. falling back from `OllamaProvider` to `ClaudeCodeProvider` on failure) — not decided anywhere and out of scope for the same reason Feature 07 already excludes it: exactly one provider is configured per run.
- Any change to Feature 08/09/10 — they already consume `LLMProvider` generically and need no changes to work with a new implementation of it.
- A hosted-API-key provider — unrelated to this feature.

## Acceptance criteria

- `OllamaProvider` implements the existing `LLMProvider` Protocol exactly (same `provider_id`/`complete` shape as `ClaudeCodeProvider`), with no changes to any Feature 07 type.
- A test with a fake/mocked Ollama HTTP endpoint proves: a well-formed structured response is parsed and structured into the target schema correctly; a malformed/non-JSON response, a connection error, and a timeout all produce `LLMCallResult(status="not_analyzed", reason="llm_failed")` without raising.
- `model` has no hard-coded default anywhere in this feature's code — a test instantiating `OllamaProvider` without a `model` argument fails to construct (required argument), proving it can't silently fall back to an assumed tag.
- The citation validator and schema structuring already shipped by Feature 07 are exercised, unmodified, against `OllamaProvider`'s output — a test proves a response citing an unknown fact id is rejected exactly as it already is for `ClaudeCodeProvider`, via the same code path (not a duplicated check).
- `suggest_ollama_budget` returns a plausible integer against a fixture of a captured real `/api/show` response, and `None` (not an exception) when the request fails — and is not called anywhere inside `OllamaProvider.complete()` itself (grep/import check, or a test proving `complete()` makes no `/api/show` call).
- `uv run pytest` and `uv run ruff check .` pass.
