# Feature 07 — LLM orchestration framework

## Depends on

Feature 01 (Facts & Evidence model).

## Goal

Implement the generic machinery every LLM-based feature (Architecture Interpretation, Domain Understanding, Onboarding Path) must be built on: provider abstraction, structured-output contract, citation validation, caching, and budget enforcement — per **Décidé Q94–Q107, Q95**. This feature ships no actual synthesis content (no architecture/domain/onboarding prompts) — those are later features that consume this framework.

## Scope

### `LLMProvider` interface (Décidé Q94/Q168, resolved 2026-09-14)

```python
class LLMProvider(Protocol):
    def complete(self, prompt: StructuredPrompt, schema: type[T]) -> T: ...
```

Abstracts over provider/model choice so the synthesis layer never talks to a specific API directly. Exactly one provider is configured per run — no automatic cross-provider fallback chain (that's added complexity nothing in Design Decisions calls for; a run either has a working provider configured or it doesn't). Three concrete implementations:

- **`OllamaProvider` (default)** — talks to a local Ollama server (default `http://localhost:11434`, overridable) running a model the user has installed (e.g. a Qwen model). The exact model tag (`OLLAMA_MODEL` config/env var, e.g. `qwen2.5:14b`) is **runtime configuration, never hardcoded** — what's actually installed is a fact about the user's machine, not something this spec can assume. On startup, calls Ollama's `/api/show` for the configured model to read its real context window, used to compute this call-site's token budget (Q86) rather than assuming a number; falls back to a small conservative fixed budget if introspection fails, rather than crashing. Requests structured output via Ollama's `format` parameter — a full JSON-schema constraint if the installed Ollama version supports it, otherwise plain `format: "json"` — but **never trusts that constraint alone**: this feature's existing schema + citation validation (see below) runs unconditionally on every response regardless of what the provider claims to guarantee. Entirely local — no network call leaves the machine, which is also why this is now the default (cf. Q163/Q167: best fit for the local-first principle and for confidential repositories).
- **`ClaudeCodeProvider`** — shells out to the `claude` CLI (already installed/authenticated via the user's Claude Code session, no separate API key) in non-interactive/print mode. Still available, selectable in configuration when higher synthesis quality is wanted and the machine's local compute/model isn't the bottleneck to avoid — check `claude --help` at implementation time for current flags (e.g. `-p`/`--print`, `--output-format json`) rather than assuming a specific version. Not fully local (prompts leave the machine to the user's Claude Code account), so avoid it for confidential repositories unless explicitly authorized (Q167).
- **`DisabledProvider`** — the no-op provider already required by **Décidé Q95** (LLM disabled), returning the same `not_analyzed: llm_failed`-shaped outcome as any other provider failure. Always available as the final fallback, e.g. via a `--no-llm` switch surfaced later by Feature 13, or simply by not configuring a real provider.

This feature ships all three. No hosted-API-key provider (OpenAI/Anthropic-API/etc.) is built here — if one is wanted later, it's a fourth implementation added the same way, not a change to this feature's scope.

### Structured output only (Décidé Q106)

Every LLM call is schema-validated JSON in, schema-validated JSON out — never free text parsed heuristically. `StructuredPrompt` bundles the instructions, the bounded fact/content payload (produced by a later feature's selection logic — this feature just carries it), and the target Pydantic/dataclass schema. A response that fails schema validation is treated as a call failure (see below), not "best-effort" coerced.

### Mandatory citations + hallucination guard (Décidé Q80, Q81, Q104, Q105)

Every schema used for a narrative/interpretive field must include a `fact_ids: list[str]` alongside it. After a response validates against its schema, this feature runs a **second validation pass**: every id in every `fact_ids` list must correspond to a real `Fact.id` already present in the `FactStore` supplied to the call. A response citing an unknown fact id is rejected — not silently stripped, not accepted with a warning (**Décidé Q81**: reject/retry, not correction). This citation-validity check is also the metric this framework exposes for hallucination measurement (**Décidé Q205**: "taux de citations invalides détectées par le validateur structurel").

### Confidence (Décidé Q83, Q44)

Any schema with an interpretive field also carries a `confidence: float` `[0,1]`, explicitly supplied by the model — never defaulted or inferred by this framework.

### Multiple concurrent hypotheses (Décidé Q82)

The framework's schema-composition helpers must support "one field, many possible values with independent confidence" as a first-class shape (e.g. `hypotheses: list[Hypothesis]`), not just a single best-guess field — later features (notably Architecture Interpretation) rely on this.

### Failure handling (Décidé Q107, Q95)

A failed call (provider error, schema validation failure, or citation validation failure) never aborts the run. It's recorded as `not_analyzed: llm_failed` for whatever section requested it — the same status vocabulary reserved in Feature 01. This is also how "LLM disabled" is implemented: disabling the LLM (**Décidé Q95**, must be possible) is a no-op provider that always returns this same failure status, so downstream features don't need a separate disabled-mode code path — they already have to handle `llm_failed`.

### Caching (Décidé Q102, Q103)

Cache key = hash(prompt content + schema/prompt version + provider/model identifier) → response. Persisted so it survives across runs (same store family as facts, not in-memory-only). Invalidation is automatic and implicit: if the underlying selected content changes, the hash changes — this feature does not need to implement any dependency-tracking invalidation logic (**Décidé Q103** explicitly calls this out as a consequence of the hashing scheme, not a separate mechanism to build).

### Budget (Décidé Q100, Q101, Q86)

A token budget is attached per call-site category (not global-only), with a running total tracked per analysis run. For `OllamaProvider`, this budget is derived from the configured model's real context window (introspected via `/api/show`, see above) minus a reserved margin for the prompt scaffolding and expected output — not a number invented by this spec. For `ClaudeCodeProvider`, use a conservative fixed default (the CLI doesn't expose an equivalent introspection call) — configurable, not hard-coded as a magic number buried in logic. Exceeding budget causes graceful degradation (the call is skipped, recorded as `not_analyzed: budget_exceeded`) — never a hard crash of the pipeline.

## Explicitly out of scope for this feature

- Any real prompt content for architecture/domain/onboarding synthesis — later features.
- Content-selection logic (which files/facts to include within budget) — **Décidé Q87** assigns this to hotspot/centrality reuse, which is a later feature's responsibility; this feature only enforces that *whatever* is selected fits the schema and budget contract.
- Any hosted-API-key provider (OpenAI/Anthropic API/etc.) — not needed given the `OllamaProvider`/`ClaudeCodeProvider` defaults; add one later only if actually wanted, as a new implementation, not a scope change to this feature.
- Multi-pass orchestration strategy across features (**Proposition Q96/Q98**, not decided in detail) — this feature provides the primitive a single pass is built from; sequencing multiple passes into one report is assembled later.
- Automatic cross-provider fallback (e.g. retry on `ClaudeCodeProvider` if `OllamaProvider` fails) — not decided anywhere, and would add nondeterminism to which provider actually answered a given call; exactly one provider is configured per run.

## Acceptance criteria

- `LLMProvider` protocol + `OllamaProvider` (real, HTTP-backed) + `ClaudeCodeProvider` (real, subprocess-backed) + `DisabledProvider` (no-op fallback), plus a deterministic fake provider used in this feature's own tests (so tests don't require a running Ollama server or the `claude` CLI).
- Structured request/response cycle enforces schema validation on both ends.
- `OllamaProvider` correctly calls the configured model's `/api/show` for context-window introspection (falling back to a fixed conservative budget if it fails, not crashing), requests structured output via `format`, and surfaces a malformed/non-JSON response as a call failure (`not_analyzed: llm_failed`) rather than a crash — tested against fixtures of captured real Ollama API responses, so this doesn't require a running Ollama server in CI.
- `ClaudeCodeProvider` correctly invokes the `claude` CLI non-interactively, parses its structured output, and surfaces a malformed/non-JSON response as a call failure the same way — tested against a fixture of captured real CLI output, same fixture-based approach as Feature 02's adapter contract tests, so this doesn't require `claude` to be installed in CI.
- Citation validator: given a `FactStore` and a response with `fact_ids`, correctly accepts valid ids and rejects unknown ones — tested against both `OllamaProvider` and `ClaudeCodeProvider` response fixtures, proving the validator doesn't trust either provider's own structured-output guarantee; a test proves an unknown-id response never reaches the caller as a successful result regardless of provider.
- `DisabledProvider` produces the same `not_analyzed: llm_failed`-shaped result as a real provider failure, proving downstream code needs no separate disabled-mode branch.
- Cache: same prompt+schema+provider hash returns the cached response without a second provider call (proven via a call-counting fake provider in tests); a changed prompt content bypasses the cache; the same prompt against two different providers/models produces two distinct cache entries (provider/model identifier is part of the key).
- Budget: a call exceeding a configured per-category budget is skipped and recorded, not raised as an exception; `OllamaProvider`'s budget reflects the fake/fixture model's introspected context window in tests, not a hard-coded number.
- `uv run pytest` and `uv run ruff check .` pass.
