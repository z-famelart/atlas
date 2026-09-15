# Feature 07c — Give `DisabledProvider` a distinguishable failure reason

## Why this is a separate feature, not a rewrite of Feature 07

Feature 07 (LLM orchestration framework, `DisabledProvider` included) is **already implemented**. This is a small, additive fix to `DisabledProvider.complete()`'s return value and the one place `LLMCallResult.reason`'s vocabulary is defined — not a rewrite of `LLMProvider`, `LLMCallResult`, `ClaudeCodeProvider`, `OllamaProvider`, or the orchestrator.

## What was actually found (grounding for this spec)

Found while an implementing agent verified [Feature 14c](14c-agent-detects-ollama.md) against a real `atlas analyze` run: `DisabledProvider.complete()` (`src/project_intel/llm/providers.py`) returns `LLMCallResult(status="not_analyzed", reason="llm_failed")` — **the exact same `reason` value** a genuine provider failure (timeout, connection error, citation rejection) returns. Confirmed directly: a real `--llm-provider ollama` run that hit a citation-validation failure on the `domain` stage produced `detail="not_analyzed: llm_failed"` — byte-identical to what a plain `--no-llm` run produces.

This silently breaks two already-shipped consumers that assumed these cases were distinguishable in the stored text:

- **[Feature 11c](11c-report-fidelity-fixes.md)'s `_gap_message`** checks for the substring `"llm_provider not configured"` to show *"LLM analysis was disabled for this run."* as opposed to *"Atlas attempted this analysis but it failed: {detail}."* — but that exact string is only ever produced by a vestigial `ctx.llm_provider is None` check in each LLM stage's own code (`architecture/stage.py` etc.), a branch that **never fires** through the real CLI, because `--no-llm` constructs a real `DisabledProvider()` instance (not `None`) — see `cli/main.py`'s provider resolution. So today, a `--no-llm` run and a genuine LLM failure render the exact same "attempted but it failed" message in the HTML report, even though 11c's spec and tests intended them to be distinct.
- **[Feature 14c](14c-agent-detects-ollama.md)**'s "was LLM ever actually attempted in this store" check has the same problem, for the same underlying reason.

## Depends on

Feature 07 (`LLMProvider`, `LLMCallResult`, `DisabledProvider` — already implemented). [Feature 11c](11c-report-fidelity-fixes.md) (`_gap_message`, already implemented — this feature's scope includes correcting its one now-provably-wrong string comparison, since that comparison was built on an assumption this feature shows was false, not a new capability for 11c).

## Scope

### A distinct `reason` value for "disabled," not "failed"

Add `"llm_disabled"` to `LLMCallResult.reason`'s `Literal["llm_failed", "budget_exceeded"]` type (→ `Literal["llm_failed", "budget_exceeded", "llm_disabled"]`). `DisabledProvider.complete()` returns `LLMCallResult(status="not_analyzed", reason="llm_disabled")` instead of `reason="llm_failed"`. No other provider's behavior changes — `ClaudeCodeProvider`/`OllamaProvider` keep returning `"llm_failed"` for their own failures, unchanged.

This is additive to the type (a new literal member, not a removed or renamed one) — existing code comparing `reason == "llm_failed"` for a real failure still works exactly as before; only `DisabledProvider`'s own case changes.

### Fix the one consumer whose check was built on the wrong assumption

`src/project_intel/html_report/renderer.py`'s `_gap_message` currently checks `"llm_provider not configured" in detail` — a string that (per the finding above) the real CLI path never produces. Change this check to match what `DisabledProvider` now actually produces: `detail` (built as `f"not_analyzed: {result.reason}"` by each stage) contains `"llm_disabled"`. This is a one-line string-match correction, not a change to `_gap_message`'s signature, the four-state structure Feature 11c already established, or anything else in that function.

### Correct Feature 14c's detection string before it ships

[Feature 14c](14c-agent-detects-ollama.md) is not yet merged — its agent-definition text and spec should be corrected to check for `"llm_disabled"` (matching this feature's fix) instead of the never-actually-produced `"llm_provider not configured"`, as part of landing 14c, not as a second follow-up fix.

## Explicitly out of scope for this feature

- Any change to `ClaudeCodeProvider`, `OllamaProvider`, the orchestrator, citation validation, caching, or budget — only `DisabledProvider`'s return value and its one `Literal` type member change.
- The vestigial `ctx.llm_provider is None` checks in each LLM stage (`architecture/stage.py` etc.) — they're dead code through the current CLI (since `--no-llm` never leaves `llm_provider` as `None`) but harmless; removing dead code is a separate, purely-cosmetic cleanup, not required for this fix to work (the fix works entirely through `DisabledProvider.complete()`'s return value, which every stage already goes through regardless of that early check).
- Any change to how a real failure (timeout, citation rejection, malformed response) is reported — those keep `reason="llm_failed"`, unchanged; this feature only carves out the one case that was wrongly sharing that value.

## Acceptance criteria

- `DisabledProvider().complete(...)` returns `LLMCallResult(status="not_analyzed", reason="llm_disabled")` — a test asserts this exact value, distinct from a mocked real-provider failure's `reason="llm_failed"`.
- A test running the architecture (or any LLM) stage with `ctx.llm_provider = DisabledProvider()` (the real object the CLI constructs for `--no-llm`, not `None`) produces a `StageRunResult.detail` containing `"llm_disabled"`.
- A test on `html_report/renderer.py`'s `_gap_message`, given a `stage_run_result` fact with `detail="not_analyzed: llm_disabled"`, renders *"LLM analysis was disabled for this run."* — and given `detail="not_analyzed: llm_failed"` (a genuine failure), renders the *"attempted but it failed"* message — proving the two are now actually distinguishable end-to-end, not just in a hand-constructed unit test that bypassed the real provider.
- `uv run pytest` and `uv run ruff check .` pass.
