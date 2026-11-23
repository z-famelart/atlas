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

## Quickstart (≈10 minutes)

**Prerequisites:** macOS/Linux, Git, [mise](https://mise.jdx.dev/) (or Python 3.12 + [uv](https://docs.astral.sh/uv/)).

```bash
# 1. Get Atlas and install the `atlas` command globally (editable = tracks your checkout)
git clone git@github.com:z-famelart/atlas.git && cd atlas
mise install                               # Python 3.12 + uv
uv tool install --editable .               # puts `atlas` on your PATH

# 2. Install the external analyzers Atlas orchestrates
brew install tokei                         # languages + LOC   (or: cargo install tokei)
uv tool install graphifyy                  # code graph        (PyPI name has two y's)

# 3. Wire it into your coding agent and check the tools (claude | agy | gemini | codex)
atlas setup --harness claude

# 4. (Optional, for the LLM sections) a local model — nothing leaves your machine
brew install llama.cpp
llama-server -m /path/to/model.gguf -c 32768 &

# 5. Analyze a repository
atlas analyze /path/to/repo      # or --no-llm
open atlas-report-*.html
```

Missing tools never crash a run: the stage that needs them is reported as skipped,
with the install command, and the report says the section was not analyzed.

Next steps: **[docs/getting-started.md](docs/getting-started.md)** — full install, every
CLI option, config file, MCP registration in Claude Code (without the per-tool permission
prompts), the synthesis agent, troubleshooting.

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
