# Feature 04b — Rebase `git log` paths onto `repo_path`, not the git repository root

## Why this is a separate feature, not a rewrite of Feature 04

Feature 04 is **already implemented**, and its own spec already states the invariant this feature restores: *"All Git facts key on the same normalized file path used elsewhere in the model... this feature must not introduce a separate path-normalization scheme."* (04-git-analysis.md, Correlation key / Décidé Q116). This feature fixes a concrete violation of that already-decided invariant found by comparing two hotspot tables that "parlaient de fichiers différents alors que c'est les mêmes" (looked like different files that were actually the same) in a real `atlas-synthesis` re-run — it does not change `git_churn`/`git_co_change`'s fact shape or any other part of Feature 04.

## Depends on

Feature 04 (git analysis — already implemented, this feature only changes `git_analysis/churn.py`'s `normalize_churn` and `git_analysis/cochange.py`'s `normalize_cochange`, both currently using `git`'s raw output path unmodified as `subject.id`).

## What was actually found (grounding for this spec)

Replayed a real `atlas analyze --llm-provider ollama ... crewlybase/backend` run's `FactStore` (`repo_path` = `crewlybase/backend`, a **subdirectory** of the actual git repository, rooted at `crewlybase/`):

1. `git log --numstat`/`git log --name-only` (both run with `cwd=ctx.target_path`, i.e. `crewlybase/backend`) still print paths **relative to the git repository's top level** (`crewlybase/`, not `crewlybase/backend`) — this is `git log`'s own behavior, unrelated to `cwd`, and it holds regardless of where within the repo the command is invoked from. `normalize_churn`/`normalize_cochange` use that path unmodified as `subject.id` (e.g. `"backend/src/crewlybase/apps/scheduling/services.py"`).
2. Every other fact producer (discovery's file walker, lizard/complexity, graphify's code graph) computes paths relative to `repo_path` itself (e.g. `"src/crewlybase/apps/scheduling/services.py"`, no `backend/` prefix, since `repo_path` already *is* `.../backend`).
3. When `repo_path` happens to be the git root (the common, non-monorepo case), both conventions coincide by accident and the bug is invisible. The moment `repo_path` is a subdirectory of a larger git repository, they diverge by a fixed prefix, and **every single file fragments into two distinct `subject.id`s**: one carrying `git_churn`/`git_co_change` facts, one carrying everything else (`centrality`, `complexity`, `community`, `calls`/`imports`) — the two never join, silently breaking the "same normalized path" invariant Feature 04's own spec already requires.
4. Measured on the real store (246 distinct `hotspot_score` subjects, one run): **60 files** fragmented this way. Nearly every `hotspot_score` fact across the whole repository shows `components_available: "1/4"` instead of the `3/4`/`4/4` a file with churn+complexity+centrality all present should have — confirmed directly, e.g. `applications/services.py`: the `backend/`-prefixed entity has `git_churn` (18 commits) and a `hotspot_score.combined=0.986` from that **one** component alone; the non-prefixed entity has `complexity`/`centrality`/`community`/`calls`/`imports` and a **separate**, lower `hotspot_score.combined=0.831` from those two components alone — never combined into one real 3/4 score for the one real file.
5. **This directly explains a second, independently-reported symptom**: the domain understanding glossary being dominated by one file (`festivals/admin.py`, source of 21 of 28 domain facts in the same run) with `scheduling/services.py`-rooted vocabulary ("shift", "swap") entirely absent, despite `scheduling.shift`/`scheduling.assignment` being tracked, first-class model names elsewhere in the codebase. Trace: the `backend/`-prefixed "ghost" entity for `scheduling/services.py` ranks artificially high in the hotspot list (churn-only score, not averaged down by other components) and gets selected as a [Feature 09b](09b-domain-candidate-selection-fix.md) candidate — but `domain/selector.py::_read(repository_path, path)` then tries to open `<repo_path>/backend/src/crewlybase/apps/scheduling/services.py`, i.e. `crewlybase/backend/backend/...` (the prefix applied twice), which doesn't exist; `OSError` is caught and `""` is returned. The LLM receives a plausible-looking candidate with **empty content** for exactly the file that should have supplied "shift"/"swap" vocabulary, while the real, readable, non-prefixed entity for the same file — deprived of the churn signal that would have ranked it competitively — may not make the `top_n` cut at all. Feature 09b's real budget and coverage instruction were necessary but could not fix this: they operate on a candidate pool already corrupted upstream by this Feature 04 bug.

## Scope

### Rebase git-reported paths onto `repo_path`

In both `normalize_churn` and `normalize_cochange`: before building any `Fact`, compute the offset of `ctx.target_path` from the git repository's top level (`git rev-parse --show-prefix`, run with `cwd=ctx.target_path` — returns e.g. `"backend/"` when `ctx.target_path` is a subdirectory, or `""` when it already is the root) and strip that prefix from every path `git log`/`git log --numstat` returns, before using it as `subject.id` / `EntityRef.id`. When `repo_path` is the git root, the prefix is empty and behavior is unchanged from today. This makes the "chemin de fichier normalisé" invariant Feature 04's spec already declares (and Q116 relies on) actually hold whenever `repo_path` is a subdirectory of a larger git repository, not just when it happens to be the root.

### Defensive: drop empty-content candidates in domain selection

Small, cheap addition to [Feature 09b](09b-domain-candidate-selection-fix.md)'s already-shipped `select_candidates`: a candidate whose `_read()` result is empty (`OSError` or a genuinely empty file) is excluded from the returned `CandidateContent` list rather than sent to the LLM as a plausible-looking, content-free entry. Protects against this bug class recurring from any future path-source disagreement, not only this specific one — cheap enough to include here rather than as its own feature.

## Explicitly out of scope for this feature

- `git_churn`/`git_co_change`'s fact shape (`Fact(type=..., value={...})`) — unchanged, only the `subject.id`/`object.id` path values are corrected.
- Monorepo-specific scoping (**Proposition Q114**, still not decided) — this feature only fixes path *identity*, not whether churn/co-change should ever be scoped to a sub-project; churn/co-change stay repository-wide as today.
- Any change to `code_graph`, `complexity`, or `discovery`'s own path computation — they're already correct (`repo_path`-relative); this feature makes Git match them, not the other way around.
- Re-running or backfilling already-stored facts from past runs — this feature only affects facts produced by future `atlas analyze` runs; a store with pre-existing fragmented facts (like the one used to diagnose this) is not retroactively repaired.

## Acceptance criteria

- A test with a fake git repo where `ctx.target_path` is a subdirectory of the actual repository root (e.g. a temp repo with a `backend/` subdirectory as `target_path`) produces `git_churn`/`git_co_change` facts whose `subject.id` matches the `repo_path`-relative convention (no leading `backend/`), identical to what a `complexity`/`centrality` fact for the same file would use.
- The same test with `ctx.target_path` equal to the repository root produces unchanged output versus today (empty prefix, no behavior change).
- A fixture where `select_candidates` would otherwise include a candidate whose `_read()` returns `""` confirms that candidate is excluded from the result.
- `uv run pytest` and `uv run ruff check .` pass.
