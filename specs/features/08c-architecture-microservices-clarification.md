# Feature 08c — Don't let the model confuse a `services/` folder with microservices

## Why this is a separate feature, not a rewrite of Feature 08/08b

Feature 08 (architecture interpretation) and 08b (pattern catalogue validation) are **already implemented**. This is a small, additive prompt-text clarification, in the same spirit and location as 08b's own fix.

## What was actually found (grounding for this spec)

Read directly from a real `atlas-synthesis` agent output (`~/Documents/Perso/crewlybase/backend-synthesis.html`, a Django backend analyzed with `qwen2.5-coder:latest` via Ollama): one of four `architecture_hypothesis` facts read:

> *"There are multiple service files within the festivals app, suggesting a microservices approach within that app."* (confidence 0.7)

The agent's own "My read" section (correctly) flagged this as wrong: the repository has a `festivals/services/` **Python package** — `core.py`, `team.py`, `bans.py`, `festival_teams.py`, all in one process, one deployable, per the project's own documented 5-file-per-app convention. There is nothing "micro" or independently-deployed about it. The model pattern-matched the word "services" (a folder name, a code-organization convention) onto "microservices" (a distributed-systems deployment pattern) — two unrelated meanings of the same English word. This is a distinct failure mode from the one 08b already fixed (08b was about `pattern` receiving something that isn't a catalogue value at all, like a file glob; this is the model correctly picking a **valid** catalogue value — `microservices` is one of the seven — but for the wrong reason, on a codebase that doesn't remotely exhibit that pattern). 08b's defensive validation can't catch this, since `"microservices"` *is* a valid catalogue string — the mistake is semantic, not structural.

## Depends on

Feature 08/08b (architecture interpretation + pattern catalogue validation, already implemented — this changes only the prompt-building text in `architecture/analyzer.py`'s `build_prompt`, not the schema, the catalogue list, or 08b's validation logic).

## Scope

### Clarify what "microservices" actually means in the prompt

Add an explicit clarifying line to the prompt built by `build_prompt` (alongside the catalogue description 08 already sends), distinguishing the deployment pattern from a same-named code-organization convention:

> `"microservices"` means multiple **independently deployed processes/services** communicating over a network (separate deployables, separate runtimes) — it does **not** mean a single codebase that happens to have a directory or package named `services/`, `service_layer/`, or similar. A Django app (or any single-process application) with an internal `services/` module organizing business logic is not microservices merely because of that name. Only use `"microservices"` if there's actual evidence of multiple independently deployed/runnable units (e.g. multiple `Dockerfile`s, separate deployment manifests, separate process entry points) — not just a naming convention.

This is a prompt-text-only addition — no change to `ArchitectureHypothesis`, `ArchitectureResponse`, `_CATALOGUE`, or 08b's post-response validation, which stays exactly as shipped (it still normalizes any *invalid* catalogue value; this feature only tries to stop a *valid-but-wrong* one from being picked in the first place).

## Explicitly out of scope for this feature

- Any change to 08b's defensive validation (`normalize_pattern`) — this feature can't fix a semantically-wrong-but-syntactically-valid catalogue pick after the fact the way 08b fixes an invalid one; it can only reduce how often the model makes this specific mistake, via clearer prompting.
- General architecture-hypothesis quality improvements beyond this one specific, confirmed confusion (folder-naming vs. deployment pattern) — not a broader prompt-engineering pass.
- Detecting *actual* microservices architectures more reliably (e.g. by having Discovery look for multiple `Dockerfile`s/deployment manifests as corroborating evidence) — a real, larger idea, but a separate feature if ever pursued; this feature only edits prompt text.

## Acceptance criteria

- A test on `build_prompt`'s output asserts the clarifying microservices instruction is present.
- No change to `ArchitectureHypothesis`/`ArchitectureResponse`/`_CATALOGUE`/`normalize_pattern` (confirmed via diff — prompt text only).
- `uv run pytest` and `uv run ruff check .` pass.
