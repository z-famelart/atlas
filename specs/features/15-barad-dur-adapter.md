# Feature 15 — Barad-dur adapter (ownership, age, coupling ratios, file roles)

## Depends on

Feature 02 (adapter framework), Feature 04 (git stage, `_git_prefix`).

## Goal

[Barad-dur](https://lab.frogg.it/Edouard_Mangel/barad-dur) (GPL-3.0+, Rust) computes what Atlas lacked: blame-based ownership, file age, coupling percentages with expected pairs (test pairs) flagged, and a role per file. Atlas wraps it as a required external tool (same convention as tokei and graphify: a missing binary skips with an install hint) and never links or copies its code. It replaces Feature 04's own co-change adapter (`git_co_change`, removed): Atlas describes the project as it is now, so per-pair commit hashes are not needed evidence — churn and a tool-output reference suffice. Its import graph was empty on both Python and Rust spike targets, so graphify stays the code-graph source; its churn and complexity are not used (Atlas's own churn matched; lizard covers more languages).

## Scope

Adapter `git_analysis/barad_dur.py`, run by the `git` stage after churn/co-change. The tool runs on a throwaway `git clone` because it writes a cache and edits `.gitignore` in the analysed tree; paths are rebased onto `repo_path` (Feature 04b rule).

New fact types (provenance `computed`, evidence `tool_output`), each with a typed accessor in `value_schemas.py`:

| type | subject → object | value |
|---|---|---|
| `git_ownership` | file | `top_author`, `top_pct`, `authors` (top 5 `{name, pct}`) |
| `file_age` | file | `days_since_modified`, `last_modified` |
| `file_role` | file | `role` (`source`/`test`/`config`/`other`) |
| `git_coupling` | file_a → file_b (`changed_in`) | `co_changes`, `coupling_pct`, `is_test_pair`, `cross_boundary` |

MCP: `get_owners(repo_path, path_prefix, top_n)` (authors by mean blame share); per-file ownership/age already appear in `get_component`.

## Explicitly out of scope

- Barad-dur's 0–100 scores and CI gate (an interpretation, not evidence; Atlas is not a gate).
- Feeding ownership into the onboarding prompt and the HTML report.
- Author names are personal data: they are stored and served over MCP as-is; pseudonymisation is not decided (Q165).

## Acceptance

- `tests/test_barad_dur.py`: normalisation matches the typed schemas; `get_owners` ranking.
- Dogfood (Barad-dur v0.22.0): ripgrep 6.9 s end to end, 203 ownership/age/role facts, 848 coupling facts.
