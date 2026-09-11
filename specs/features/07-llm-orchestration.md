# Feature 07 — LLM orchestration framework

## Depends on

Feature 01 (Facts & Evidence model).

## Goal

Implement the generic machinery every LLM-based feature (Architecture Interpretation, Domain Understanding, Onboarding Path) must be built on: provider abstraction, structured-output contract, citation validation, caching, and budget enforcement — per **Décidé Q94–Q107, Q95**. This feature ships no actual synthesis content (no architecture/domain/onboarding prompts) — those are later features that consume this framework.

## Scope

### `LLMProvider` interface (Décidé Q94)

```python
class LLMProvider(Protocol):
    def complete(self, prompt: StructuredPrompt, schema: type[T]) -> T: ...
```

Abstracts over provider/model choice so the synthesis layer never talks to a specific API directly. This feature ships the interface and one concrete implementation; which provider is the MVP default is an implementation choice, not a re-litigation of the (still-open) provider question.

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

## Explicitly out of scope for this feature

- Any real prompt content for architecture/domain/onboarding synthesis — later features.
- Content-selection logic (which files/facts to include within budget) — **Décidé Q87** assigns this to hotspot/centrality reuse, which is a later feature's responsibility; this feature only enforces that *whatever* is selected fits the schema and budget contract.
- Local-LLM-specific wiring (**Proposition Q168**, not decided) — the `LLMProvider` interface must not preclude it, but no local-model implementation ships here.
- Exact context-size default (**Ouvert Q86**) — the budget mechanism must be configurable, with no hard-coded assumption about what the "right" default is.
- Multi-pass orchestration strategy across features (**Proposition Q96/Q98**, not decided in detail) — this feature provides the primitive a single pass is built from; sequencing multiple passes into one report is assembled later.

## Acceptance criteria

- `LLMProvider` protocol + one concrete implementation (can be a deterministic stub/fake for testing plus one real provider integration).
- Structured request/response cycle enforces schema validation on both ends.
- Citation validator: given a `FactStore` and a response with `fact_ids`, correctly accepts valid ids and rejects unknown ones; a test proves an unknown-id response never reaches the caller as a successful result.
- A "disabled" no-op provider produces the same `not_analyzed: llm_failed`-shaped result as a real provider failure, proving downstream code needs no separate disabled-mode branch.
- Cache: same prompt+schema+provider hash returns the cached response without a second provider call (proven via a call-counting fake provider in tests); a changed prompt content bypasses the cache.
- Budget: a call exceeding a configured per-category budget is skipped and recorded, not raised as an exception.
- `uv run pytest` and `uv run ruff check .` pass.
