# Feature 07b — Ollama local provider

## Why this is a separate feature, not a rewrite of Feature 07

Feature 07 (LLM orchestration framework) and Feature 08 (Architecture interpretation) are **already implemented and shipped** (`src/project_intel/llm/`, `ClaudeCodeProvider` as the current default). Per the [regeneration contract](README.md#regeneration-contract), a feature's spec is a stable interface once built — rewriting Feature 07's spec to describe a provider that doesn't exist in the shipped code, or to claim a different default than what's actually running, breaks that contract for no reason: nothing requires touching Feature 07 itself to add a new provider.

This feature is purely additive: one new `LLMProvider` implementation, added the same way Feature 07's own spec already anticipated ("a local LLM provider will be added later, without re-discussing this choice or changing the `LLMProvider` interface" — Q94). It changes nothing about `LLMProvider`, `StructuredPrompt`, `LLMCallResult`, `BudgetConfig`, `BudgetTracker`, the citation validator, or the cache — all already shipped by Feature 07 and reused unmodified.

## Depends on

Feature 07 (LLM orchestration framework — already implemented). Does not depend on Feature 08, 09, or 10; those consume whatever provider is configured without knowing which one it is.

## Goal

Add `OllamaProvider`, a second real `LLMProvider` implementation talking to a local Ollama server, per **Décidé Q168** (resolved 2026-09-14: the user has Ollama running locally with a Qwen model installed). `OllamaProvider` becomes the **default provider** wherever a provider is selected (Feature 13's config loading, or any manual wiring in the meantime) — the user now runs analyses against their local model by default, with `ClaudeCodeProvider` remaining available as a configurable alternative and `DisabledProvider` as the no-LLM fallback. This changes the *default selection*, made by whatever wires providers together (Feature 13) — it does not touch Feature 07's `LLMProvider` protocol, `ClaudeCodeProvider`'s own code, or its own default constructor argument (`model: str = "claude-haiku-4-5-20251001"` stays exactly as shipped).

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

### Logging (per [README](README.md#logging-a-convention-every-feature-follows)'s logging convention)

Same shape as Feature 07's own logging addendum: `logging.getLogger(__name__)`, `WARNING` on any `not_analyzed` result with `provider_id`/model/underlying error, `INFO` on call start/end and connectivity checks, `DEBUG` with the full request/response. The three actionable messages below are this logger's `WARNING`-level output — the CLI (Feature 13) renders `WARNING` and above by default regardless of verbosity flag, so these are seen without needing `-v`/`--debug`.

### Clear configuration and error messages (new: LLM stages must be easy to set up and debug)

Since `OllamaProvider` is now the default, a user without Ollama running (or without the configured model pulled) hits this path on their very first run, with no prior context on what went wrong — the failure modes must say exactly what to fix, not just degrade silently to `not_analyzed: llm_failed` the way any other provider failure does internally. Concretely:

- **Missing `model`**: `OllamaProvider.__init__` raising for a missing `model` argument (already required, per Scope above) must produce a `TypeError` whose message names the `OLLAMA_MODEL` env var / config field as the fix — not Python's generic "missing argument" text alone. Wrap the call site (wherever Feature 13 constructs the default provider) to catch a missing config value and print an actionable message, e.g. `"No Ollama model configured — set OLLAMA_MODEL (e.g. qwen2.5:14b) or run with --no-llm."`
- **Ollama not running (connection refused)**: `complete()` still returns `LLMCallResult(status="not_analyzed", reason="llm_failed")` per Feature 07's contract (unchanged) — but this feature adds a **first-call connectivity check**, run once per pipeline invocation (not per `complete()` call), that pings `/api/tags` before the first real request and, on failure, logs at `WARNING`: `"Could not reach Ollama at <base_url> — is it running? (ollama serve). Falling back to --no-llm behavior for this run."` This is a diagnostic log record alongside the existing `not_analyzed` bookkeeping, not a new status value or a change to `LLMCallResult`.
- **Model not pulled**: Ollama's own error response for an unknown model (HTTP 404 / `"model not found"` body) is detected specifically (string/status match on the response, not a generic exception catch) and logged at `WARNING` as `"Model '<model>' not found in Ollama — run: ollama pull <model>."` alongside the same `not_analyzed: llm_failed` result.
- All three messages go through this feature's logger (see the Logging subsection above) — this feature does not invent a new output channel, just makes sure the log text for these specific, predictable failure modes is actionable instead of a bare exception string. The CLI (Feature 13) is what turns a `WARNING`-level record into something the user actually sees on the console.

## Explicitly out of scope for this feature

- Changing `LLMProvider`, `StructuredPrompt`, `LLMCallResult`, `BudgetConfig`, `BudgetTracker`, the cache, or the citation validator — all already shipped by Feature 07, reused as-is.
- Changing `ClaudeCodeProvider`'s own code or its own default constructor argument — it stays exactly as shipped by Feature 07, still available as a configurable alternative to the new default.
- Automatic cross-provider fallback (e.g. falling back from `OllamaProvider` to `ClaudeCodeProvider` on failure) — not decided anywhere and out of scope for the same reason Feature 07 already excludes it: exactly one provider is configured per run.
- Any change to Feature 08/09/10 — they already consume `LLMProvider` generically and need no changes to work with a new implementation of it.
- A hosted-API-key provider — unrelated to this feature.
- A general-purpose error-reporting framework for the CLI — the three messages above are specific to Ollama's own predictable failure modes (not running, model missing, no model configured), reported through whatever mechanism 06b/13 already use for stage warnings; not a new logging/reporting system.

## Acceptance criteria

- `OllamaProvider` implements the existing `LLMProvider` Protocol exactly (same `provider_id`/`complete` shape as `ClaudeCodeProvider`), with no changes to any Feature 07 type.
- A test with a fake/mocked Ollama HTTP endpoint proves: a well-formed structured response is parsed and structured into the target schema correctly; a malformed/non-JSON response, a connection error, and a timeout all produce `LLMCallResult(status="not_analyzed", reason="llm_failed")` without raising.
- `model` has no hard-coded default anywhere in this feature's code — a test instantiating `OllamaProvider` without a `model` argument fails to construct (required argument), proving it can't silently fall back to an assumed tag.
- The citation validator and schema structuring already shipped by Feature 07 are exercised, unmodified, against `OllamaProvider`'s output — a test proves a response citing an unknown fact id is rejected exactly as it already is for `ClaudeCodeProvider`, via the same code path (not a duplicated check).
- `suggest_ollama_budget` returns a plausible integer against a fixture of a captured real `/api/show` response, and `None` (not an exception) when the request fails — and is not called anywhere inside `OllamaProvider.complete()` itself (grep/import check, or a test proving `complete()` makes no `/api/show` call).
- Missing `model`, connection-refused, and model-not-found each produce the specific actionable message described above (tested against mocked responses/exceptions for each case), while `complete()`'s return value for all three stays `LLMCallResult(status="not_analyzed", reason="llm_failed")` — the messaging is additive diagnostic output, not a change to the result contract.
- `uv run pytest` and `uv run ruff check .` pass.
