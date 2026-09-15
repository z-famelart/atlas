# Feature 14c — Agent detects and configures Ollama itself; doesn't trust a stale LLM-less store

## Why this is a separate feature, not a rewrite of Feature 14/14b

Feature 14 (agent-driven synthesis) and 14b (agent runs `analyze` itself) are **already implemented and shipped** (`.claude/agents/atlas-synthesis.md`). Per the [regeneration contract](README.md#regeneration-contract), this feature changes the agent's decision logic additively — it doesn't touch the MCP query sequence, provenance rules, or HTML output shape 14/14b already specify.

## What actually happened (grounding for this spec)

The user asked the `atlas-synthesis` agent to run against this repository with nothing more than "run with it" — no LLM flags, no prior setup instruction. The agent produced a synthesis whose "Atlas findings" section read:

> *"Atlas could not analyze architecture patterns, domain concepts, and onboarding paths because the LLM-based stages failed (--no-llm run). Domain workflows ... are not returned. See the 'My read' section below for manual interpretation."*

Diagnosis: this was **not** a live LLM failure and **not** the agent passing `--no-llm` itself. Ollama was running and reachable the whole time (confirmed directly: `curl localhost:11434/api/tags` and `ollama list` both worked, three models installed). The actual sequence, per 14b's already-shipped logic:

1. Earlier work in this same repository (dogfooding runs from Features 06c/11c/11d's own implementation agents) had already run `atlas analyze --no-llm .` several times, so `.atlas-cache/facts.sqlite` already existed.
2. 14b's rule is "if a facts store already exists, skip re-running analysis" — correct in general (don't silently re-trigger an expensive LLM pass), but it doesn't distinguish *why* the existing store has no architecture/domain data: genuinely analyzed-and-found-nothing, vs. **every run that ever touched this store was `--no-llm`, so LLM stages were never actually attempted at all.**
3. The agent reused that stale, LLM-less store, found nothing for architecture/domain/onboarding (correctly, per what's actually there), and reported the gap — exactly as specified. The gap-reporting behavior worked correctly; the *decision to trust that store* is what needs fixing.

Separately, confirmed by reading `src/project_intel/cli/main.py`: when no `--ollama-model`/`$OLLAMA_MODEL` is available and stdin is not a TTY (true for a subagent's tool calls), `atlas analyze` raises `click.ClickException` and refuses to run at all — it does **not** silently fall back to disabled. So if the agent's own environment doesn't have `OLLAMA_MODEL` exported, its only options today are: hit a hard failure, or (per 14b) skip running `analyze` altogether if a store already exists — neither path gets the user real LLM-backed findings when Ollama is sitting right there, reachable, with models installed. Per direct user feedback: *"ça serait assez chanmé si l'agent détecte Ollama."*

## Depends on

Feature 14/14b (agent-driven synthesis, already implemented — this changes only the "Prerequisites / startup sequence" section of the agent definition). [Feature 06c](06c-stage-run-persistence.md) (`stage_run_result` facts, already implemented — this is what lets the agent tell "this store never had a real LLM run" apart from "LLM ran and found nothing," the same distinction Feature 11c already surfaces in the HTML report). [Feature 07c](07c-disabled-provider-reason.md) — must land alongside this feature; without it, `DisabledProvider`'s `detail` string is indistinguishable from a genuine failure and this feature's core detection has nothing reliable to check.

## Goal

The agent should never present an LLM-shaped gap to the user without having actually tried, when trying was possible. Two changes:

1. **Resolve an Ollama model itself**, the same way the CLI would if it could prompt interactively — the agent isn't a TTY, so the CLI's own `_pick_ollama_model` prompt path is unreachable to it; the agent needs to do the equivalent itself, non-interactively.
2. **Don't trust an existing facts store as "already analyzed" if it never had a real LLM attempt** — check what's actually in it (via `stage_run_result` facts) before deciding to skip a fresh `analyze` run.

## Scope

### Ollama self-detection and model resolution (replaces part of 14b's step 2)

Before deciding whether `analyze` needs to run, and before constructing the `atlas analyze` invocation:

1. If the user explicitly passed LLM flags (`--llm-provider`, `--ollama-model`, `--no-llm`), pass them through unchanged — this is not new scope, matches 14b exactly.
2. Otherwise, check whether Ollama is reachable: `ollama list` (or an HTTP check against `$OLLAMA_URL`/the default `http://localhost:11434`). If reachable and at least one model is installed, pick one **deterministically** — the first entry in `ollama list`'s output, the exact same "first available model" rule `_pick_ollama_model` already uses for its interactive fallback (`src/project_intel/cli/main.py`) — and pass it explicitly as `--ollama-model <model>`. Never invent a model name, never guess a tag that isn't actually installed.
3. If Ollama is not reachable and no other provider was requested, proceed with `--no-llm`, but **say so explicitly and prominently** in the synthesis output (not buried) — e.g. a note at the top of "Atlas findings": *"Ollama was not reachable when this analysis ran; architecture/domain/onboarding sections were skipped. Install/start Ollama and re-run to get LLM-backed findings."* This is the same "actionable, not silent" principle already established for the CLI itself (Décidé Q170/Feature 07b) and for the interactive prompt (Décidé Q181) — applied here to the one case where the agent genuinely can't do anything about it.

### Don't reuse a store that never had a real LLM run (replaces 14b's "skip if store exists" rule)

Before skipping `analyze` because `.atlas-cache/facts.sqlite` already exists (14b's rule), query it for `stage_run_result` facts (Feature 06c) for the LLM-backed stages (`architecture`, `domain`, `onboarding`), across all runs, not just the latest:

- If **any** run has a `stage_run_result` for these stages with `status="ok"` or `status in ("skipped","failed")` with a `detail` that is *not* `"not_analyzed: llm_disabled"` (i.e., LLM was actually attempted at least once, whether it succeeded or genuinely failed) — the store has real signal. Skip re-running, exactly as 14b already does; Feature 11c's own cross-run fallback will already surface the best available result.
- If **every** `stage_run_result` for these stages, across every run in the store, shows `detail="not_analyzed: llm_disabled"` (i.e., LLM was *never once* attempted) — and Ollama is reachable per the check above — run `atlas analyze` now, with a real provider, even though a store already technically exists. This is not "silently re-running an expensive pass" (14b's original concern, still valid) — it's "running the pass that was never actually run," which is a different situation the original rule didn't distinguish.

**Depends on [Feature 07c](07c-disabled-provider-reason.md)** for this detection to actually work: `DisabledProvider` must return a `reason` distinguishable from a genuine failure (`"llm_disabled"` vs `"llm_failed"`) for the `detail` string this feature checks to ever actually appear — found and fixed together, since 14c's own verification surfaced the gap in Feature 07's shipped `DisabledProvider`.
- If no `stage_run_result` facts exist at all for these stages (a store from before Feature 06c landed, or a very old run) — treat this the same as the "never attempted" case above: don't assume, check by running once.

## Explicitly out of scope for this feature

- Any change to `atlas analyze`'s own CLI behavior (the `click.ClickException` on missing model + non-TTY stays exactly as shipped) — this feature only changes what the *agent* does before invoking that CLI, so it never hits that exception in the first place when Ollama is actually available.
- Any change to Feature 06c's fact shape or Feature 11c's report rendering — this feature only *reads* `stage_run_result` facts the same way 11c already does, via the same query pattern.
- Retrying a genuinely-failed LLM stage (citation validation rejection, timeout, etc.) — that's the known, separate Ollama-citation-reliability issue; this feature only concerns itself with "was it attempted at all," not "did it succeed."
- Picking a "better" model by any heuristic (size, speed, task-fit) — always the first entry from `ollama list`, matching the CLI's own existing convention exactly, no new judgment call introduced.
- Automatically starting Ollama if it isn't running (`ollama serve`) — the agent detects and reports, it does not manage the Ollama process.

## Acceptance criteria

- A worked example: a repository whose only existing facts store came from a prior `--no-llm` run, with Ollama reachable and a model installed, run through the agent with no LLM flags specified — the agent runs a fresh `analyze` with a real Ollama model (not skipped), and the resulting synthesis has real architecture/domain/onboarding content instead of the gap message.
- A worked example: same setup, but Ollama unreachable (stopped) — the agent proceeds with `--no-llm` and the synthesis's "Atlas findings" section states this explicitly and prominently, not just as an incidental gap note buried per-section.
- A worked example: a store with at least one prior run where an LLM stage was genuinely attempted (`stage_run_result.detail` is anything other than the "not configured" string) — the agent does **not** re-run `analyze`, confirming the "don't silently re-trigger an expensive pass" protection from 14b still holds.
- The agent definition's model-resolution logic is documented to pick the exact same "first `ollama list` entry" convention as `src/project_intel/cli/main.py`'s `_pick_ollama_model` — no divergent selection logic between the CLI's interactive path and the agent's non-interactive one.
