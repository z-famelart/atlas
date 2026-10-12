# Feature 06d — Hotspots rank source code only

## Depends on

Feature 06 (scoring engine), Feature 15 (optional `file_role` facts).

## Goal

Reading real output showed hotspot tops dominated by non-code: on ripgrep, `Cargo.lock`, `CHANGELOG.md`, `Cargo.toml`, `README.md`; on Atlas itself, specs and `uv.lock`. Churn-only history paths of files that no longer exist also ranked. `compute_hotspots` now drops them before normalisation, so percentile ranks are computed over scorable files only.

## Scope

- `compute_hotspots` scores only files with a Barad-dur `file_role` other than `config`; files Barad-dur does not know (lockfiles, docs, deleted paths) are dropped before percentile ranking.
- No `file_role` facts (Barad-dur missing) means no filtering — there is no local substitute.

## Acceptance

- Config, unknown and deleted files get no `hotspot_*` facts (`tests/test_hotspots.py`).
- Dogfood: ripgrep and Atlas hotspot tops are source/test files.
