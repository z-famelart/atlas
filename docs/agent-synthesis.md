# Atlas agent synthesis

**Important**: the HTML report (`atlas analyze`, Feature 11/11b) is Atlas's standalone full deliverable —
self-contained, offline, covering every fact in the store, no agent required.
The `atlas-synthesis` agent is a *complementary, tailored alternative*: a shorter synthesis
the agent writes to answer a specific question or give a senior-engineer-style read of the codebase.
It is not a replacement for the full report, and the full report does not depend on it.

## Self-serve usage (Feature 14b)

As of Feature 14b, the agent is fully self-serve. Point it at a repository path and it
handles the full pipeline itself — no manual `atlas analyze` or `atlas mcp-serve` step required.

```bash
claude --agent atlas-synthesis "Synthesize /path/to/repo for a newcomer joining the payments team"
```

The agent will:
1. Check for an existing facts store at `/path/to/repo/.atlas-cache/facts.sqlite`.
2. Run `atlas analyze /path/to/repo` if no store exists yet (skipped on subsequent runs).
3. Start `atlas mcp-serve /path/to/repo/.atlas-cache/facts.sqlite` (always the explicit, derived path).
4. Query the MCP server and write `atlas-synthesis.html` in the current directory.

Pass LLM flags through if needed:

```bash
claude --agent atlas-synthesis \
  "Synthesize /path/to/repo --llm-provider ollama --ollama-model qwen3:14b"
```

## What the agent produces

A single self-contained HTML file with two sections:

- **Atlas findings** — relayed material from MCP, provenance badges intact
  (`observed` / `computed` / `hypothesis`), clickable evidence links.
  If any query returned `not_analyzed`, that gap is stated explicitly.
- **My read** — the agent's own interpretation, under a visually distinct heading,
  no provenance badge. The agent takes a position; it does not just restate the facts.

See `examples/atlas-synthesis-example.html` for a worked example.

## Adding the agent to your project

Copy the agent definition into any Claude Code project:

```bash
mkdir -p /path/to/your/project/.claude/agents
cp .claude/agents/atlas-synthesis.md \
   /path/to/your/project/.claude/agents/atlas-synthesis.md
```

Then invoke it in an interactive session:

```
/agent atlas-synthesis
```

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| "MCP server not reachable" | Agent couldn't start `atlas mcp-serve` — check `atlas` is on PATH |
| All sections say `not_analyzed` | LLM stages failed during `analyze` — re-run with `-v` for detail |
| Empty hotspots table | Repository has no Git history or no supported language files |
