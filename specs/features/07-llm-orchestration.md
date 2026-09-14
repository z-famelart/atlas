# Feature 07 — LLM orchestration framework

## Depends on

Feature 01 (Facts & Evidence model).

## Goal

Implement the generic machinery every LLM-based feature (Architecture Interpretation, Domain Understanding, Onboarding Path) must be built on: provider abstraction, structured-output contract, citation validation, caching, and budget enforcement — per **Décidé Q94–Q107, Q95**. This feature ships no actual synthesis content (no architecture/domain/onboarding prompts) — those are later features that consume this framework.

## Scope

### `LLMProvider` interface (Décidé Q94, resolved 2026-09-14)

```python
class LLMProvider(Protocol):
    def complete(self, prompt: StructuredPrompt, schema: type[T]) -> T: ...
```

Abstracts over provider/model choice so the synthesis layer never talks to a specific API directly. The MVP default is **not** a hosted-API-key integration — the user running this project has no LLM API keys, and the Design Decisions default-provider choice (Q94) was resolved accordingly:

- **`ClaudeCodeProvider` (default)** — shells out to the `claude` CLI (already installed and authenticated on the machine running `project-intel`, via the user's existing Claude Code session/subscription — no separate API key) in non-interactive/print mode, passing the prompt and requesting structured/JSON output the implementation parses and validates against `schema`. Check `claude --help` at implementation time for the exact current flags (e.g. `-p`/`--print`, `--output-format json`) rather than assuming a specific CLI version's flag names. Because this runs the `claude` binary as a subprocess per call, treat each call as comparatively slow/serial — this provider does not need to be optimized for throughput, only correctness.
- **`DisabledProvider` (fallback)** — the no-op provider already required by **Décidé Q95** (LLM disabled), returning the same `not_analyzed: llm_failed`-shaped outcome as any other provider failure. Available unconditionally, e.g. via a `--no-llm` style switch surfaced later by Feature 13, or simply by not configuring a real provider.
- **Local LLM (e.g. Ollama), per Q168 — deferred, not built in this feature.** The user will add this once they have a local model running; the `LLMProvider` interface must not need to change when that happens — a third implementation is added later, this feature's job is only to make sure the interface doesn't preclude it (see Explicitly out of scope).

This feature ships all of: the `LLMProvider` protocol, `ClaudeCodeProvider`, and `DisabledProvider`. No hosted-API-key provider (OpenAI/Anthropic-API/etc.) is built here — if one is wanted later, it's a fourth implementation added the same way a local-LLM one would be, not a change to this feature's scope.

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

### Budget (Décidé Q100, Q101)

A token budget is attached per call-site category (not global-only), with a running total tracked per analysis run. Exceeding budget causes graceful degradation (the call is skipped, recorded as `not_analyzed: budget_exceeded`) — never a hard crash of the pipeline.

### Logging (per [README](README.md#logging-a-convention-every-feature-follows)'s logging convention)

`ClaudeCodeProvider` and any other `LLMProvider` implementation logs via `logging.getLogger(__name__)`: `WARNING` on any call that ends in `not_analyzed` (`provider_id`, model, prompt category, and the underlying error — subprocess exit code/stderr for `ClaudeCodeProvider`), `INFO` on call start/end and cache hits, `DEBUG` with the full prompt and raw response. This is a `logger.<level>(...)` call added inside `complete()` before it returns — it does not change `LLMCallResult`'s shape or any other type this feature already shipped.

## Explicitly out of scope for this feature

- Any real prompt content for architecture/domain/onboarding synthesis — later features.
- Content-selection logic (which files/facts to include within budget) — **Décidé Q87** assigns this to hotspot/centrality reuse, which is a later feature's responsibility; this feature only enforces that *whatever* is selected fits the schema and budget contract.
- Local-LLM-specific wiring (**Proposition Q168**, not decided when, only that it's wanted eventually) — the `LLMProvider` interface must not preclude it, but no local-model implementation ships here; the user will request it as a separate follow-up once a local model is available.
- Any hosted-API-key provider (OpenAI/Anthropic API/etc.) — not needed given the `ClaudeCodeProvider` default; add one later only if actually wanted, as a new implementation, not a scope change to this feature.
- Exact context-size default (**Ouvert Q86**) — the budget mechanism must be configurable, with no hard-coded assumption about what the "right" default is.
- Multi-pass orchestration strategy across features (**Proposition Q96/Q98**, not decided in detail) — this feature provides the primitive a single pass is built from; sequencing multiple passes into one report is assembled later.

## Acceptance criteria

- `LLMProvider` protocol + `ClaudeCodeProvider` (real, subprocess-backed) + `DisabledProvider` (no-op fallback), plus a deterministic fake provider used in this feature's own tests (so tests don't shell out to `claude`).
- Structured request/response cycle enforces schema validation on both ends.
- `ClaudeCodeProvider` correctly invokes the `claude` CLI non-interactively, parses its structured output, and surfaces a malformed/non-JSON response as a call failure (`not_analyzed: llm_failed`), not a crash — tested against a fixture of captured real CLI output, same fixture-based approach as Feature 02's adapter contract tests, so this doesn't require `claude` to be installed in CI.
- Citation validator: given a `FactStore` and a response with `fact_ids`, correctly accepts valid ids and rejects unknown ones; a test proves an unknown-id response never reaches the caller as a successful result.
- `DisabledProvider` produces the same `not_analyzed: llm_failed`-shaped result as a real provider failure, proving downstream code needs no separate disabled-mode branch.
- Cache: same prompt+schema+provider hash returns the cached response without a second provider call (proven via a call-counting fake provider in tests); a changed prompt content bypasses the cache.
- Budget: a call exceeding a configured per-category budget is skipped and recorded, not raised as an exception.
- `uv run pytest` and `uv run ruff check .` pass.
