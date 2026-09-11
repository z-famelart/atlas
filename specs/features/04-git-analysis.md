# Feature 04 — Git analysis

## Depends on

Feature 01 (Facts & Evidence model), Feature 02 (Adapter framework). Builds on the Git-presence check from Feature 03 (Discovery) but does not require the rest of Discovery.

## Goal

Compute Git history metrics deterministically — churn, co-change, rename-aware file history — per **Décidé Q110–Q116**. These facts feed the later Hotspots feature but this feature does not compute any score itself.

## Scope

### Churn (Décidé Q110, Q113)

Number of commits (and, separately, lines changed) touching a file over the analysis window, computed via `git log`. Merge commits are **excluded by default** (**Décidé Q113** — avoids inflating churn from large merges) with a config flag to include them. Output: `Fact(type=git_churn, subject=File, value={commits: int, lines_changed: int}, provenance=computed)`.

### Rename handling (Décidé Q112)

Uses Git's native rename detection (`git log --follow` / similarity detection) so a file's churn/co-change history survives renames — a renamed file is not treated as two unrelated files with broken history.

### Co-change (Décidé Q111)

Pairs of files that appear together in the same commit more often than a configurable frequency threshold, over the same window. Output: `Fact(type=git_co_change, subject=File, object=File, predicate=changed_in, value={co_occurrences: int}, provenance=computed)` — note this reuses the `changed_in` relation type from Feature 01's model rather than inventing a new one.

### History window (Décidé Q108, Q109)

A **configurable window** (default: a bounded recent period, not full history) is applied to all of the above. Full-history analysis is available as an explicit option. This feature accepts a `window: timedelta | None` parameter (`None` = full history) — it does not decide what the default value should be beyond "bounded by default"; the exact default duration is left to configuration, not hard-coded as a magic number buried in logic.

### Correlation key (Décidé Q116)

All Git facts key on the same normalized file path used elsewhere in the model (Feature 01 `Evidence.ref.path`), so a later feature (Hotspots) can join Git facts with graph facts purely via the `FactStore` query API — this feature must not introduce a separate path-normalization scheme.

### Evidence (Décidé Q41)

Every Git fact's evidence references the relevant commit(s) by full hash (never short hash), per Feature 01's `commit` evidence kind.

## Explicitly out of scope for this feature

- Monorepo-specific scoping behavior (**Proposition Q114**, not decided) — this feature computes churn/co-change repository-wide; how a later feature narrows that to a `Project` sub-scope is not addressed here.
- Any hotspot scoring or combination with complexity/centrality — Feature 06 (Hotspots).
- Contributor-concentration analysis (`Q189` of the Capability Matrix, P1) — not in this feature.
- Incremental/diff-based re-analysis (**Proposition Q160**, not decided) — this feature always computes from the full configured window on each run.

## Acceptance criteria

- A Git adapter (via Feature 02's contract) producing churn and co-change facts from a real Git history, using the `git` binary directly (no re-implementation of Git internals).
- Merge-commit exclusion is the default and is toggleable.
- Rename continuity is demonstrated: a test fixture repository with a renamed file shows continuous churn history across the rename.
- Window parameter honored: a test asserts that commits outside the window are excluded, and that `window=None` includes everything.
- All facts carry full commit-hash evidence and `provenance=computed`.
- `uv run pytest` and `uv run ruff check .` pass.
