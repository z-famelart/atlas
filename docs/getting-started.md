# Getting started with Atlas

This guide takes you from nothing to: an HTML report of a repository, the facts database
behind it, Atlas's MCP server wired into Claude Code, and the `atlas-synthesis` agent.

- [1. Install](#1-install)
- [2. Analyze a repository](#2-analyze-a-repository)
- [3. Read the HTML report](#3-read-the-html-report)
- [4. Query facts from the CLI](#4-query-facts-from-the-cli)
- [5. Use Atlas from Claude Code (MCP server)](#5-use-atlas-from-claude-code-mcp-server)
- [6. The atlas-synthesis agent](#6-the-atlas-synthesis-agent)
- [7. Configuration file (`.atlas.toml`)](#7-configuration-file-atlastoml)
- [8. Updating Atlas](#8-updating-atlas)
- [Troubleshooting](#troubleshooting)
- [Quick reference](#quick-reference)

---

## 1. Install

### 1.1 Atlas itself

Requirements: macOS or Linux, Git, Python 3.12 and [uv](https://docs.astral.sh/uv/).
The repo pins both through [mise](https://mise.jdx.dev/) (`.mise.toml`), which is the
easiest path.

```bash
git clone git@github.com:z-famelart/atlas.git
cd atlas
mise install                      # installs Python 3.12 + uv for this directory
uv tool install --editable .      # installs the global `atlas` command
atlas --help
```

Why `--editable`: `uv tool install` normally *copies* the package, so later `git pull`s
are invisible to the global `atlas` command. The editable install always runs your
checkout's current code. (See [§8](#8-updating-atlas) for the one caveat.)

If you only want to hack on Atlas and not use it globally, `uv sync` is enough; run it as
`uv run atlas …` from the repo.

### 1.2 External analyzers

Atlas orchestrates existing tools instead of reimplementing them. Each one is optional:
if it is missing, its stage is marked *skipped* with the install command, the rest of the
pipeline continues, and the report shows the corresponding section as not analyzed.

| Tool | Used by stage | What you lose without it | Install |
|---|---|---|---|
| `git` | `git` | churn; hotspots lose their churn component | usually already there |
| [`tokei`](https://github.com/XAMPPRocky/tokei) | `discovery` | languages and lines of code; hotspots lose their size component | `brew install tokei` or `cargo install tokei` |
| [`graphify`](https://pypi.org/project/graphifyy/) | `code_graph` | imports/calls/symbols, centrality, communities, cycles; architecture and onboarding get much weaker | `uv tool install graphifyy` (two y's) |
| [`barad-dur`](https://lab.frogg.it/Edouard_Mangel/barad-dur) | `git` | co-change ratios, file ownership, age and file roles; hotspots then rank lockfiles, docs and deleted files too | `cargo install barad-dur --locked` |
| [`lizard`](https://github.com/terryyin/lizard) | `hotspots` | — it is a Python dependency of Atlas, installed automatically | — |

Check what is available:

```bash
for t in git tokei graphify barad-dur; do printf "%-9s" $t; command -v $t || echo "MISSING"; done
```

Framework/build/CI/IaC detection (in `discovery`) is signature-based and needs no tool.

### 1.3 An LLM (optional)

Three stages — `architecture`, `domain`, `onboarding` — ask an LLM to interpret the facts.
Everything else is deterministic. Pick one:

| Provider | When | Setup |
|---|---|---|
| **llama.cpp** (default) | Code must stay on your machine, no API key | `brew install llama.cpp`, then `llama-server -m <model.gguf> -c 32768` (serves on `:8080`; the model and context size are fixed at launch) |
| **Ollama** | Same, if you still use Ollama | `ollama serve`, `ollama pull qwen3:14b`, `--llm-provider ollama --ollama-model qwen3:14b` |
| **Claude Code** | Better interpretation quality; content is sent to Anthropic through your Claude Code login | `claude` CLI installed and logged in |
| **None** | Confidential code with no local model, or fast deterministic-only runs | `--no-llm` |

Quality note: the interpretive sections are only as good as the model. Local 7–14B models
produce usable but sometimes thin or generic architecture hypotheses; the report always
shows which model produced a claim and which facts it cites, so you can judge.

---

## 2. Analyze a repository

```bash
atlas analyze /path/to/repo                               # llama-server on localhost:8080
atlas analyze --llama-cpp-url http://host:8081 /path/to/repo
atlas analyze --llm-provider ollama --ollama-model qwen3:14b /path/to/repo
atlas analyze --llm-provider claude-code /path/to/repo    # Claude Code (Haiku 4.5 by default)
atlas analyze --no-llm /path/to/repo                      # deterministic stages only
```

`PATH` is the repository (or a sub-directory of it, e.g. `backend/` of a monorepo) — you
can run the command from anywhere.

### What it writes

| Where | What |
|---|---|
| `<repo>/.atlas-cache/facts.sqlite` | The fact store. Append-only: every run adds facts under a new `run_id`, old runs are kept. |
| `<repo>/.atlas-cache/llm_cache.sqlite` | LLM response cache (key = prompt content + schema version + provider + model). Re-running on unchanged input costs nothing. |
| `<repo>/graphify-out/` | graphify's own output (written by graphify, read by Atlas). |
| `./atlas-report-<run_id>.html` | The report, in the **current directory**. |

Add `.atlas-cache/` and `graphify-out/` to the analyzed repo's `.gitignore` (or your
global gitignore).

### Pipeline and stages

Stages run in this fixed order; each one reads the facts written by the ones before it.

| Stage | Produces | LLM |
|---|---|---|
| `discovery` | technologies (frameworks, build, CI, IaC), languages + LOC, Git presence, documents | no |
| `git` | `git_churn` (full history, merge commits excluded; renamed files keep their pre-rename history), plus from Barad-dur `git_coupling` (co-change ratios), `git_ownership`, `file_age`, `file_role` | no |
| `code_graph` | `symbol_defined`, `imports`, `calls`, `centrality`, `community`, `dependency_cycle` | no |
| `hotspots` | `hotspot_score` = complexity + size + centrality + churn, each percentile-ranked, with the breakdown | no |
| `architecture` | `architecture_hypothesis` (pattern from a fixed catalogue, confidence, cited facts) | yes |
| `domain` | `business_concept`, `business_workflow`, `glossary_term` | yes |
| `onboarding` | `onboarding_path` (entry points, what to avoid at first, open questions) | yes |

Run a subset — useful to iterate on one stage. Stages run alone reuse the latest facts of
earlier stages from previous runs, so this does not rescan the code:

```bash
atlas analyze --only git --only hotspots /path/to/repo
atlas analyze --only architecture --ollama-model qwen3:14b /path/to/repo
```

Available stage names: `discovery`, `git`, `code_graph`, `hotspots`, `architecture`, `domain`, `onboarding`.

### Reading the terminal output

Each stage ends with `✓` (ok), `✗` (failed) or `⊘` (skipped), the number of facts
produced and, if relevant, a reason:

| Detail | Meaning |
|---|---|
| `not_analyzed: llm_disabled` | You passed `--no-llm`. |
| `not_analyzed: llm_failed` | The model was called and failed (unreachable, timeout, invalid JSON, invented fact ids…). Re-run with `-v`. |
| `Binary 'tokei' not found — brew install tokei` | Tool missing; install it and re-run that stage with `--only`. |

Exit code is `1` if any stage failed, `0` otherwise.

Verbosity:

```bash
atlas analyze -v  /path/to/repo   # INFO: one line per adapter / LLM call (incl. cache hits)
atlas analyze -vv /path/to/repo   # DEBUG: exact commands, raw tool output, full prompts/responses
```

---

## 3. Read the HTML report

Open the file printed on the last line (`Report: atlas-report-<run_id>.html`). It is fully
self-contained — Mermaid is embedded, no network access, shareable as a single file.

What to look for:

- **Provenance badges** on every item: `observed` (read from a tool), `computed` (derived
  deterministically), `inferred` (rule-based guess), `hypothesis` (LLM). Hover for confidence.
- **Evidence**: click an item to see the facts, files and commits behind it.
- **Gaps are explicit**: a section says whether it was never run, had the LLM disabled,
  had the LLM fail (with the reason), or ran and found nothing. When the current run has no
  data but a previous run does, the section shows the earlier result and says which run it
  came from.
- **Search** (top right) filters across all sections.

Sections: Executive summary · System map · Architecture · Code map (community graph) ·
Hotspots · Domain understanding · Git evolution · Risks · Onboarding path · Glossary · Evidence.

---

## 4. Query facts from the CLI

```bash
atlas facts query /path/to/repo --type technology_detected
atlas facts query /path/to/repo --type hotspot_score --run-id <run_id> --json
atlas facts query /path/to/repo --provenance hypothesis
atlas facts query /path/to/repo --type stage_run_result --json   # why a stage was empty
```

Without filters it prints every fact of every run (thousands of lines) — filter first.

---

## 5. Use Atlas from Claude Code (MCP server)

`atlas mcp-serve` is a **read-only**, **global** MCP server over stdio: register it once,
use it for any repository. Every tool takes a `repo_path` and reads
`<repo_path>/.atlas-cache/facts.sqlite`; each result comes from the latest run that produced
that kind of fact (so `atlas analyze --only architecture` does not hide hotspots) unless you
pass `run_id`, and all list results are capped.

| Tool | Question it answers |
|---|---|
| `where_to_start(repo_path, component?)` | Onboarding path; falls back to top hotspots + most central files |
| `get_hotspots(repo_path, top_n=10, component?)` | Riskiest files, with the score breakdown (max 50) |
| `get_component(repo_path, name_or_path)` | Every fact about one file |
| `get_dependencies(repo_path, component, limit=20)` | What it imports/calls (max 50) |
| `get_dependents(repo_path, component, limit=20)` | What imports/calls it (max 50) |
| `get_path(repo_path, component_a, component_b, max_depth=5)` | Shortest dependency path (max depth 10) |
| `find_workflow(repo_path, query, limit=10)` | Business workflows matching a keyword (max 20) |
| `get_insights(repo_path, kind, limit=10)` | Architecture hypotheses, business concepts or glossary terms (`kind`: `architecture` \| `concepts` \| `glossary`), with confidence (max 50) |
| `get_owners(repo_path, path_prefix="", top_n=5)` | Authors ranked by mean blame share under a path (needs `barad-dur`; max 50) |

The server never runs an analysis: if the store is missing it answers with the
`atlas analyze` command to run.

### 5.1 Register the server (once)

```bash
claude mcp add --scope user atlas -- atlas mcp-serve
claude mcp list          # atlas should show as connected
```

`--scope user` makes it available in every project. (This writes to `~/.claude.json`; you
do not need a per-project `.mcp.json`.) Any other MCP client works the same way: command
`atlas`, args `["mcp-serve"]`, transport stdio.

### 5.2 Stop the per-tool permission prompts

By default Claude Code asks for approval the first time each of the 8 tools is used. They
are all read-only, so allow the whole server once in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__atlas",
      "Bash(atlas analyze:*)",
      "Bash(atlas facts query:*)",
      "Bash(ollama list)"
    ]
  }
}
```

`mcp__atlas` covers all of the server's tools. The three `Bash(...)` rules are what the
`atlas-synthesis` agent runs on its own (see §6); drop them if you don't use it. Put the
same block in a project's `.claude/settings.json` instead if you prefer to allow it per
project.

### 5.3 Try it

In any Claude Code session:

```
Use the atlas MCP to tell me where to start in /path/to/repo, then show the top 5 hotspots.
```

---

## 6. The atlas-synthesis agent

A Claude Code subagent that turns Atlas into a short, opinionated onboarding document.
It is **complementary** to the HTML report, not a replacement: the report is exhaustive and
neutral; the synthesis answers *your* question and takes a position.

What it does, in order:

1. Looks for `<repo>/.atlas-cache/facts.sqlite`.
2. Picks an LLM: your flags if you gave any, else the first model in `ollama list`, else `--no-llm` (and says so at the top of the output).
3. Runs `atlas analyze` only if there is no store yet, or if the existing store never had a real LLM attempt (e.g. only `--no-llm` runs). It never silently re-runs an expensive analysis otherwise.
4. Queries the MCP server (`where_to_start`, `get_hotspots`, `get_component`, `find_workflow`, `get_dependencies`, `get_path`).
5. Writes `atlas-synthesis.html` in the current directory with two clearly separated parts:
   **Atlas findings** (relayed facts, provenance badges and confidence intact) and
   **My read** (the agent's own interpretation — where Atlas's LLM sections are thin, it
   reads the flagged files itself rather than just reporting the gap).

See [`examples/atlas-synthesis-example.html`](../examples/atlas-synthesis-example.html).

### 6.1 Install the agent (once, for all projects)

```bash
mkdir -p ~/.claude/agents
ln -s "$PWD/.claude/agents/atlas-synthesis.md" ~/.claude/agents/atlas-synthesis.md   # run from the atlas checkout
```

A symlink keeps it in sync with `git pull`. Requires the MCP server from §5.1 (and ideally
the permissions from §5.2, otherwise expect a few approval prompts on the first run).

### 6.2 Run it

Interactive session, from the directory where you want the HTML written:

```
Use the atlas-synthesis agent on /path/to/repo — I'm joining the payments team and need to know what to read first.
```

Or non-interactively:

```bash
claude --agent atlas-synthesis "Synthesize /path/to/repo for a newcomer joining the payments team"
```

To force a model or a fresh analysis, say so in the prompt: *"…use `--ollama-model qwen3:14b`"*,
*"…re-run the analysis first"*.

More detail: [agent-synthesis.md](agent-synthesis.md).

---

## 7. Configuration file (`.atlas.toml`)

Optional. Atlas picks up `<PATH>/.atlas.toml` automatically, or any file passed with
`--config`. Precedence: config file < environment variables < CLI flags.

```toml
# Several repositories in one invocation (used only when no PATH argument is given)
[[repositories]]
path = "../billing-api"
name = "billing-api"

[[repositories]]
path = "../billing-web"

[scope]
exclude_globs = [".git/*", "node_modules/*", "vendor/*", "dist/*"]   # replaces the defaults
include_globs = ["src/*"]                                             # empty = everything
max_depth = 6

[llm]
provider = "llama-cpp"    # or "ollama", "claude-code"
model = "qwen3:14b"       # Ollama model tag (ignored by llama-cpp)
```

Environment variables: `LLAMA_CPP_URL` (default `http://localhost:8080`), `OLLAMA_MODEL`, `OLLAMA_URL` (default `http://localhost:11434`),
`CLAUDE_MODEL` (default `claude-haiku-4-5-20251001`).

Current limitations, stated plainly:

- Each repository in `[[repositories]]` is analyzed **separately** (own store, own report); cross-repository views are not built yet.
- `[scope]` is applied by the `discovery` stage; `git`, `code_graph` and `hotspots` still see the whole `PATH`. To focus on part of a monorepo, pass that sub-directory as `PATH`.
- `[hotspot_weights]` and `llm.budget_tokens` are parsed but **not applied yet** (default weights: complexity 1.0, size 0.5, centrality 1.0, churn 1.0; no token budget).

These are tracked in [improvement-ideas.md](improvement-ideas.md).

---

## 8. Updating Atlas

```bash
cd /path/to/atlas && git pull && uv sync
```

With the editable install, new `atlas` invocations use the new code immediately. A
**running** `atlas mcp-serve` does not: it keeps the code it started with. After updating,
restart it — `/mcp` → reconnect in Claude Code, or just start a new session.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `No Ollama model configured` | Non-interactive run with no model | `--ollama-model <tag>`, `OLLAMA_MODEL=…`, `[llm] model`, or `--no-llm` |
| `not_analyzed: llm_failed` | llama-server/Ollama not running, model not pulled, timeout, or the model returned invalid/uncited JSON | `ollama list`; re-run that stage with `-v` (or `-vv` for the raw response); try a larger model or `--llm-provider claude-code` |
| Architecture says "uncatalogued" everywhere | Weak model could not name a pattern | Larger model or Claude Code; the agent's *My read* compensates by reading the files |
| `⊘ code_graph … Binary 'graphify' not found` | graphify missing | `uv tool install graphifyy`, then `atlas analyze --only code_graph --only hotspots …` |
| No languages / LOC in the report | tokei missing | `brew install tokei`, re-run `--only discovery --only hotspots` |
| Empty Git evolution, hotspots without churn | Not a Git repo, or no commits | Analyze a Git checkout |
| A fix you pulled does not show up | Non-editable install, or an MCP server started before the update | `uv tool install --reinstall --editable .`; reconnect the MCP server |
| Atlas tools missing in Claude Code | Server not registered, or `atlas` not on the PATH Claude Code sees | `claude mcp list`; `which atlas`; run `atlas mcp-serve` by hand — it should wait silently on stdin |
| Claude Code asks permission for every Atlas tool | Tools not allow-listed | §5.2 |
| `uv run pytest` → `Failed to spawn: pytest` | `.venv` created when the checkout lived at another path | `rm -rf .venv && uv sync` |

---

## Quick reference

```bash
atlas analyze /path/to/repo                              # full pipeline, local LLM (llama-server)
atlas analyze --no-llm /path/to/repo                     # deterministic only
atlas analyze --only architecture -v /path/to/repo       # re-run one stage, verbose
atlas facts query /path/to/repo --type hotspot_score     # inspect facts
claude mcp add --scope user atlas -- atlas mcp-serve     # register MCP server once
claude --agent atlas-synthesis "Synthesize /path/to/repo for a new team member"
```
