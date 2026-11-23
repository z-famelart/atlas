# Atlas (Project Intelligence)

> Arriving on an unfamiliar codebase? Atlas builds an **evidence-linked map** of it:
> what the system is, how it is built, and **where to look first**.

Atlas runs existing analysis tools (Git, tokei, graphify, lizard) over a repository,
normalizes everything they report into **facts** stored in SQLite, computes cross-cutting
metrics (centrality, communities, cycles, hotspots), and only then asks an LLM to
*interpret* those facts (architecture, business domain, onboarding path) — every
interpretation must cite the facts it rests on.

You get three things out of one `atlas analyze` run:

| Output | For | What it is |
|---|---|---|
| `atlas-report-<run_id>.html` | humans | Self-contained, offline HTML report: executive summary, system map, architecture, code map, hotspots, domain, Git evolution, risks, onboarding path, glossary, evidence. |
| `<repo>/.atlas-cache/facts.sqlite` | tools | Every fact, with provenance (`observed` / `computed` / `inferred` / `hypothesis`), confidence and evidence. Query it with `atlas facts query`. |
| `atlas mcp-serve` | coding agents | Read-only MCP server (7 bounded tools) so Claude Code or any MCP client can ask "where do I start?", "what depends on X?", "what are the hotspots?". |

An optional Claude Code agent, [`atlas-synthesis`](.claude/agents/atlas-synthesis.md),
chains all of it: runs the analysis if needed, queries the MCP server, reads the code
itself where Atlas is thin, and writes a short tailored HTML synthesis
([example](examples/atlas-synthesis-example.html)).

---

## Quickstart

**Prerequisites:** macOS/Linux, Git, [uv](https://docs.astral.sh/uv/).

Pick the coding agent you use and run the one-liner. It installs Atlas, registers its MCP
server in your agent, and checks (`--install-deps`: installs) the analyzers it orchestrates.

| You use… | Run |
|---|---|
| Claude Code | `uv tool install project-intel && atlas setup --harness claude --install-deps` |
| Antigravity (`agy`) | `uv tool install project-intel && atlas setup --harness agy --install-deps` |
| Gemini CLI | `uv tool install project-intel && atlas setup --harness gemini --install-deps` |
| Codex | `uv tool install project-intel && atlas setup --harness codex --install-deps` |
| No agent (CLI + report only) | `uv tool install project-intel && atlas doctor --install` |

Then, in any repository, with the flag `setup` printed for your agent:

```bash
atlas analyze --llm-provider agy .     # claude-code | agy | gemini-cli | --no-llm | local llama.cpp (default)
open atlas-report-*.html
```

Any OpenAI-compatible API works too (`--llm-provider openai-compat`, see
[getting-started §1.3](docs/getting-started.md)). Run `atlas doctor` at any time to see what is
installed and which LLM backends are reachable.

Missing tools never crash a run: the stage that needs them is reported as skipped,
with the install command, and the report says the section was not analyzed.

**From a checkout (contributors):** `mise install && uv tool install --editable .`, then the same `atlas setup`.

Next steps: **[docs/getting-started.md](docs/getting-started.md)** — every CLI option, config
file, the permission allow-list, the synthesis agent, troubleshooting.

---

## Documentation map

| If you want to… | Read |
|---|---|
| Install and use Atlas | [docs/getting-started.md](docs/getting-started.md) |
| Use Atlas from Claude Code (MCP + agent) | [docs/getting-started.md §5–6](docs/getting-started.md#5-use-atlas-from-claude-code-mcp-server) · [docs/agent-synthesis.md](docs/agent-synthesis.md) |
| Understand how it works and why it is built that way | [docs/architecture.md](docs/architecture.md) |
| See known limitations and what could come next | [docs/improvement-ideas.md](docs/improvement-ideas.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Read the product vision (FR) | [specs/Product Brief & Vision.md](specs/Product%20Brief%20%26%20Vision.md) |
| See every design question and its decision (FR) | [specs/Design Questions.md](specs/Design%20Questions.md) → [specs/Design Decisions.md](specs/Design%20Decisions.md) |
| See how each feature was specified and built | [specs/features/README.md](specs/features/README.md) |

## Principles (the short version)

1. **Existing tools first** — orchestrate specialized tools, don't reimplement them.
2. **Deterministic first** — anything computable without an LLM is computed without one.
3. **LLM for interpretation only** — architecture, domain, onboarding; nothing else.
4. **Evidence first** — every claim links to a fact, file, symbol or commit, and carries its provenance.
5. **Never pretend to know** — "not analyzed", "LLM disabled" and "LLM failed" are shown as such, never as empty.
6. **Repository ≠ system** — one repo may be only part of the system; the model says so.

## Status

MVP, used on real projects by its author. Python, TypeScript/JavaScript, Go, Java/Kotlin,
Ruby and Rust are the supported languages. Infrastructure, CI/CD, runtime and observability
sections are not analyzed yet (they appear as explicit gaps). See
[docs/improvement-ideas.md](docs/improvement-ideas.md) for known limitations.
