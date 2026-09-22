# The atlas-synthesis agent

The HTML report written by `atlas analyze` is Atlas's full, standalone deliverable:
exhaustive, neutral, offline, no agent needed. The
[`atlas-synthesis`](../.claude/agents/atlas-synthesis.md) agent is a *complementary*
path: a Claude Code subagent that reads the same facts through the MCP server and writes a
**short, opinionated** synthesis for a specific reader or question. It never replaces the
report, and the report never depends on it.

Setup (MCP registration, permissions, agent install) is in
[getting-started.md §5–6](getting-started.md#5-use-atlas-from-claude-code-mcp-server).

## Usage

```
Use the atlas-synthesis agent on /path/to/repo — I'm joining the payments team.
```

```bash
claude --agent atlas-synthesis "Synthesize /path/to/repo for a newcomer joining the payments team"
```

Steering it, in plain language inside the prompt:

| You want | Say |
|---|---|
| A specific Ollama model | "use `--ollama-model qwen3:14b`" |
| Claude Code as the analysis LLM | "use `--llm-provider claude-code`" |
| No LLM at all | "use `--no-llm`" |
| A fresh analysis even though one exists | "re-run the analysis first" |
| A different output file | "write it to `docs/onboarding.html`" |

## Startup logic

1. **Store present?** `<repo>/.atlas-cache/facts.sqlite`.
2. **LLM resolution.** Flags you gave win. Otherwise `ollama list`: first installed model is used, explicitly. If Ollama is unreachable, it runs `--no-llm` and says so at the top of the findings.
3. **Reuse or re-run.** No store → run `atlas analyze`. Store exists → inspect `stage_run_result` facts for `architecture`/`domain`/`onboarding` across all runs: if *every* attempt was `llm_disabled` (the store never had a real LLM run), re-run once; otherwise reuse. This avoids both a hidden expensive re-analysis and trusting a store that never had its LLM sections computed.
4. **Query MCP**, always with `repo_path`: `where_to_start` → `get_hotspots(top_n=10)` → `get_insights` for `architecture` and `concepts` → `get_component` per hotspot → `find_workflow` with 2–3 domain keywords → `get_dependencies` for the top components → `get_path` between two interesting ones.

## Output

One self-contained HTML file (default `atlas-synthesis.html` in the current directory):

- **Atlas findings** — only what MCP returned. Provenance (`observed` / `computed` /
  `hypothesis`) and confidence kept exactly; each claim opens its `fact_id` evidence;
  onboarding items always come with their `rationale`; every empty result is stated as a gap.
- **My read** — the agent's own judgment, no provenance badge, visually distinct. It must
  take a position (real risks, where to start and why, where architecture and churn agree or
  contradict). Gaps are handled by kind:
  - no analyzer exists for the topic (runtime, infra, CI/CD, data, observability): say what is unknowable and what would be worth knowing;
  - Atlas's LLM stage was thin (e.g. architecture "uncatalogued"): **read the flagged files itself** and give a grounded interpretation, instead of telling the reader to go read them.

Worked example: [`examples/atlas-synthesis-example.html`](../examples/atlas-synthesis-example.html).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "atlas tools not found" | Server not registered at user scope (`claude mcp list`), or `atlas` not on PATH |
| One approval prompt per tool | Add `mcp__atlas` (and the `Bash(atlas …)` rules) to your allow-list — getting-started §5.2 |
| All interpretive sections say `not_analyzed` | LLM stages failed during `analyze` — run `atlas analyze --only architecture -v <repo>` to see why |
| Findings look stale after `git pull` of Atlas | The MCP server process predates the update — reconnect it (`/mcp`) |
| Empty hotspots table | No Git history, graphify/tokei missing, or no supported-language files |
