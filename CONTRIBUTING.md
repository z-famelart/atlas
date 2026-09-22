# Contributing to Atlas

## Setup

```bash
git clone git@github.com:z-famelart/atlas.git && cd atlas
mise install            # Python 3.12 + uv (see .mise.toml)
uv sync                 # runtime + dev dependencies into .venv
uv run pytest           # full suite, a few seconds, no external tool needed
uv run ruff check .
```

Tests use recorded tool output (`tests/fixtures/`), so you don't need tokei, graphify or
Ollama to run them — but you do to dogfood (below). Read
[docs/architecture.md](docs/architecture.md) first; it is the map of the code.

## How work is organized

Atlas is **spec-driven**. The chain is:

1. [`specs/Product Brief & Vision.md`](specs/Product%20Brief%20%26%20Vision.md) — why the tool exists (FR).
2. [`specs/Design Questions.md`](specs/Design%20Questions.md) → [`specs/Design Decisions.md`](specs/Design%20Decisions.md) — every design question with its decision and rationale (FR).
3. [`specs/features/`](specs/features/) — one implementation spec per feature, in build order, each implementing only **Décidé** points, with acceptance criteria (EN).
4. `src/project_intel/` — the code implementing those specs.

Rules that follow from it:

- **New capability or fix = new spec first.** Write `specs/features/NNx-short-name.md` (Depends on / Goal / Scope / Out of scope / Acceptance criteria), and record any new decision in `Design Decisions.md`.
- **Shipped specs are not rewritten.** Extending feature `12` means adding `12d`, not editing `12-mcp-server.md`.
- **Regeneration contract.** Public interfaces are what a spec lists; data types are frozen, slotted dataclasses; anything ordered has an explicit sort; prefer snapshot tests. See [specs/features/README.md](specs/features/README.md#regeneration-contract).
- **Read `fact.value` through the typed accessors** in `facts/value_schemas.py`, not `value.get("key", default)`.
- **Logging**: `logging.getLogger(__name__)`; `WARNING` for failures (with component, target and underlying error), `INFO` one line per external call, `DEBUG` for raw payloads only.

If you use Claude Code, the repo ships a `/feature <spec path>` skill (`.claude/skills/feature/`) that implements a spec end to end, and [CLAUDE.md](CLAUDE.md) carries the same rules for agents.

## Dogfooding: required for anything touching `analyze`

Tests passing is not enough — most fixes in this repo were found by reading real output.
After your change:

```bash
uv tool install --reinstall --editable .          # make sure `atlas` is your code
atlas analyze --llm-provider ollama --ollama-model qwen3:14b .
atlas analyze --llm-provider ollama --ollama-model qwen3:14b /path/to/a/larger/real/repo
```

Check the exit code, each stage's status and detail, and open the report. If you changed
the MCP server, reconnect it in Claude Code before testing (a running server keeps old code).

## Git

- **Conventional Commits**: `feat(mcp): …`, `fix(git): …`, `docs: …` (types: feat, fix, docs, refactor, chore, test, perf).
- **Linear history only**: rebase on `main`, then `git merge --ff-only`. Never a merge commit.
- One feature = one commit (spec commit may precede it).
