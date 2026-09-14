# Atlas agent synthesis

**Important**: the HTML report (`atlas report`, Feature 11/11b) is Atlas's standalone full deliverable —
self-contained, offline, covering every fact in the store, no agent required.
The `atlas-synthesis` agent is a *complementary, tailored alternative*: a shorter synthesis
the agent writes to answer a specific question or give a senior-engineer-style read of the codebase.
It is not a replacement for the full report, and the full report does not depend on it.

## Prerequisites

1. Run analysis first:

   ```sh
   atlas analyze <repo_path>
   ```

2. Start the MCP server (Feature 12) against the produced database:

   ```sh
   atlas mcp-serve .atlas/facts.db
   # or: atlas mcp-serve <custom_path>.db
   ```

   Note the server address printed on stdout — you'll need it for the agent configuration.

3. Configure the MCP connection in your Claude Code project settings so the agent can reach it.
   See [Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp) for setup.

## Invoking the agent

In an interactive Claude Code session (with the MCP server running):

```
/agent atlas-synthesis
```

Or in non-interactive mode:

```sh
claude --agent atlas-synthesis "Synthesize this codebase for a newcomer joining the payments team"
```

The agent will query the MCP server, then write `atlas-synthesis.html` in the current directory
(or wherever you ask). Open that file directly in a browser — no server needed.

## What the agent produces

A single self-contained HTML file with two sections:

- **Atlas findings** — relayed material from MCP, provenance badges intact
  (`observed` / `computed` / `hypothesis`), clickable evidence links.
  If any query returned `not_analyzed`, that gap is stated explicitly.
- **My read** — the agent's own interpretation, under a visually distinct heading,
  no provenance badge. The agent takes a position; it does not just restate the facts.

See `examples/atlas-synthesis-example.html` for a worked example.

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| "MCP server not reachable" | `atlas mcp-serve` not running, or wrong address in config |
| All sections say `not_analyzed` | `atlas analyze` did not run, or pointed at the wrong database |
| Empty hotspots table | Repository has no Git history or no Python/supported files |
