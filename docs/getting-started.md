# Getting started with Atlas

Atlas produces an evidence-linked understanding map of an unfamiliar codebase.
Run it once against a repository; it writes a self-contained HTML report and a
SQLite facts database you can query live from a coding agent.

---

## 1. Install

**Requirements**: Python 3.12, [`mise`](https://mise.jdx.dev/), [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/your-org/atlas
cd atlas
mise install          # pins Python 3.12 + uv via .mise.toml
uv sync               # installs all dependencies into .venv
```

After that, `atlas` is on your PATH (`.venv/bin/atlas`).  
Verify: `atlas --help`.

---

## 2. Analyze a repository

Run this from anywhere — `PATH` points at the target repo, not Atlas itself.

```bash
atlas analyze /path/to/repo
```

Atlas writes two files into `/path/to/repo/.atlas-cache/`:
- `facts.sqlite` — the normalized fact store (every stage's output)
- an HTML report in the **current working directory** (e.g. `atlas-report-<run_id>.html`)

### LLM options

LLM stages (architecture interpretation, domain understanding, onboarding path)
are enabled by default via a local Ollama server — no API key needed.

| Scenario | Command |
|----------|---------|
| Ollama with a specific model | `atlas analyze --ollama-model qwen3:14b /path/to/repo` |
| Ollama with env var | `OLLAMA_MODEL=qwen3:14b atlas analyze /path/to/repo` |
| Claude Code (local CLI) | `atlas analyze --llm-provider claude-code /path/to/repo` |
| Skip LLM stages entirely | `atlas analyze --no-llm /path/to/repo` |

To run only specific stages (e.g. fast iteration):

```bash
atlas analyze --only git --only hotspots /path/to/repo
```

Verbose output (useful to diagnose `not_analyzed` failures):

```bash
atlas analyze -v /path/to/repo    # INFO: one line per LLM call / adapter
atlas analyze -vv /path/to/repo   # DEBUG: full prompts and responses
```

---

## 3. Open the HTML report

The report is generated automatically at the end of every `atlas analyze` run.
Open the file printed on the last line:

```
Report: atlas-report-<run_id>.html
```

Open it directly in a browser — it is fully self-contained (Mermaid diagrams,
search, evidence panel all work offline, no server needed).

---

## 4. Query facts from the CLI

```bash
# List all facts for a repository
atlas facts query /path/to/repo

# Filter by type
atlas facts query --type hotspot_score /path/to/repo
atlas facts query --type business_concept /path/to/repo
```

---

## 5. Add Atlas to Claude Code as an MCP server

Atlas ships a read-only MCP server with 7 primitives a coding agent can query
live (`get_component`, `get_dependencies`, `get_hotspots`, `where_to_start`, …).

### A. Start the server manually (one-shot)

```bash
atlas mcp-serve /path/to/repo/.atlas-cache/facts.sqlite
```

The server runs over stdio and prints its address. Use this for testing.

### B. Register it in your Claude Code project

Add a `.mcp.json` at the root of the project where you want Atlas available:

```json
{
  "mcpServers": {
    "atlas": {
      "command": "atlas",
      "args": ["mcp-serve", "/path/to/repo/.atlas-cache/facts.sqlite"]
    }
  }
}
```

Replace `/path/to/repo` with the absolute path to the analyzed repository.
Claude Code picks this up automatically; no restart needed.

> **Note**: always pass the full explicit path. `atlas mcp-serve`'s own default
> argument (`facts.sqlite`) differs from where `atlas analyze` actually writes
> (`.atlas-cache/facts.sqlite`); never rely on either default.

### C. Verify the connection

In a Claude Code session, the MCP tools appear under the atlas namespace.
Ask Claude: *"use the atlas MCP to tell me where to start in this codebase"* —
it should call `where_to_start()` and return an oriented summary.

---

## 6. Add the atlas-synthesis agent

The `atlas-synthesis` agent queries the MCP server and writes a tailored
HTML synthesis — provenance-linked Atlas findings plus the agent's own read.
As of Feature 14b it is fully self-serve: point it at a repo, it handles
`analyze` + `mcp-serve` + synthesis itself.

### A. Copy the agent definition into your project

```bash
mkdir -p /path/to/your/project/.claude/agents
cp /path/to/atlas/.claude/agents/atlas-synthesis.md \
   /path/to/your/project/.claude/agents/atlas-synthesis.md
```

The agent definition is in `.claude/agents/atlas-synthesis.md`.

### B. Invoke it

In an interactive Claude Code session (with the MCP server already wired up):

```
/agent atlas-synthesis
```

Or from the command line:

```bash
claude --agent atlas-synthesis \
  "Synthesize /path/to/repo for a newcomer joining the payments team"
```

The agent will:
1. Check whether `.atlas-cache/facts.sqlite` already exists for the repo.
2. If not (first run), run `atlas analyze <repo_path>` itself.
3. Start `atlas mcp-serve <repo_path>/.atlas-cache/facts.sqlite`.
4. Query the MCP server and write `atlas-synthesis.html` to the current directory.

On subsequent runs against the same repo it skips step 2 (no hidden re-analysis cost).

### C. What the output looks like

See `examples/atlas-synthesis-example.html` for a worked example.
The file has two visually distinct sections:

- **Atlas findings** — relayed MCP results, provenance badges (`observed` /
  `computed` / `hypothesis`), clickable evidence panel per fact.
- **My read** — the agent's own interpretation, explicitly separated, no
  provenance badge.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `not_analyzed: llm_failed` | Ollama not running or model not pulled | `ollama pull qwen3:14b` then retry |
| `not_analyzed: llm_failed` (with `-v`) | Citation hallucination — model inventing fact IDs | Switch model or use `--llm-provider claude-code` |
| MCP tools not showing in Claude Code | `.mcp.json` path wrong or server not reachable | Verify path, run `atlas mcp-serve <path>` manually to confirm |
| Empty hotspots | Repo has no Git history | Run `git init && git add . && git commit` first |
| HTML report opens blank | Browser blocked local file scripts | Use Firefox, or `python3 -m http.server` in the same directory |

---

## Quick reference

```bash
# Full pipeline (LLM on, Ollama)
atlas analyze --ollama-model qwen3:14b /path/to/repo

# Inspect facts
atlas facts query /path/to/repo

# Serve for agent queries
atlas mcp-serve /path/to/repo/.atlas-cache/facts.sqlite

# Self-serve synthesis (agent handles everything)
claude --agent atlas-synthesis "Synthesize /path/to/repo for a new team member"
```
