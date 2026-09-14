# Feature 14 — Agent-driven synthesis via MCP

## Depends on

Feature 12 (MCP server — already implemented, read-only, per Q141–153). Does not depend on [Feature 11b](11b-human-readable-report.md), and 11b does not depend on this — they're two independent, complementary consumption paths onto the same analysis (see "Two paths, not one" below).

## Goal

Per **Décidé Q154b**: document a standard way to connect a coding agent (Claude Code, or any other MCP-compatible agent) to Atlas's already-shipped MCP server, so it can pull facts/insights/evidence and produce a final, human-readable **HTML synthesis document** for a developer to read — assembled by an agent at the point someone asks for it, tailored to what they actually need, not pre-baked into a fixed static template the way Feature 11/11b's full report is.

Critically, this is not a relay/reformatting job: the agent must go beyond restating what MCP returned and actually **interpret** it — what the detected hotspots/architecture/domain concepts/onboarding path add up to for someone about to work in this codebase, what looks risky, where the real complexity is, what it would recommend focusing on first. Feature 11/11b's report (and the raw MCP facts underneath it) are Atlas's own evidence and hypotheses; this feature's output is the **agent's own read of that material**, clearly distinguished as such (see "Agent interpretation, not just relay" below) — otherwise this feature is just a worse-formatted copy of the HTML report, which defeats the point of having an agent do it at all.

**This feature ships a recipe, not a new Atlas primitive.** Nothing here adds a new MCP tool, changes Feature 12's read-only contract, or adds new fact types. What's missing today isn't capability — Feature 12 already exposes everything an agent needs — it's a documented, reusable way to invoke that capability consistently, the same way the project already has an `onboarding-scout`-style agent recipe for exploring an unfamiliar codebase from scratch.

## Two paths, not one

Atlas has exactly two ways a human ends up reading something, and this feature only concerns the second:

1. **The HTML report** ([Feature 11](11-html-report.md) + [11b](11b-human-readable-report.md)) — a standalone, offline, self-contained deliverable, generated deterministically from every fact in the store, following a fixed section template. It must be readable on its own, with no agent involved — that's the whole point of it existing as a file. This feature does not touch it, and does not become a prerequisite for it.
2. **Agent-driven synthesis (this feature)** — for when someone wants a *tailored* pass: a shorter brief, an answer to a specific question ("where do I start if I need to touch payments?"), or a synthesis that reads more like something a senior engineer on the team would actually hand you, built by an agent querying live facts through MCP rather than reading the fixed full report. Still delivered as **HTML** (see below) — not a different format, a different degree of curation. This is additive convenience on top of Feature 12, not a replacement for the HTML report, and not something the HTML report depends on.

## Scope

### The agent definition (Décidé Q154b)

A reusable agent/subagent definition (e.g. `.claude/agents/atlas-synthesis.md`, mirroring the shape of this project's own `onboarding-scout` agent) that:

1. Starts Atlas's MCP server (Feature 12) against an already-analyzed repository's `FactStore` (an `atlas analyze` run must have completed first — this feature does not trigger analysis itself, consistent with Feature 12's Q154 default of not auto-triggering runs).
2. Queries it for the primitives Feature 12 already exposes (component lookup, dependencies/dependents, hotspots, workflow search, path-between-components, "where to start" — Q145–151), following each fact's `provenance`/`confidence` exactly as returned (Q142/Q143) — never restating a `hypothesis` as if it were `observed`.
3. Synthesizes what it retrieved into a narrative, structured for a developer about to work in the codebase: what the system is, how it's built, where to start, and what's uncertain — explicitly citing evidence the same way the HTML report does (Q131/Q132), not inventing claims beyond what MCP returned.
4. Adds its **own interpretation** on top of that relayed material — see "Agent interpretation, not just relay" below.
5. Writes the result as a **single self-contained HTML file** — readable directly in a browser, no server, no build step. Reuses the same visual conventions Feature 11/11b already establish (provenance/confidence badges, clickable evidence) rather than inventing a new visual language, so a developer who's seen the full report recognizes the synthesis instantly. This feature does not ship a renderer/template engine of its own: the agent definition instructs the agent to write plain HTML/CSS directly (a few hundred lines, no framework), optionally reusing Feature 11/11b's CSS conventions as a copy-pasted reference, not as a shared imported module — the agent has no Python runtime dependency on Atlas's own code, only an MCP connection to it.

### Agent interpretation, not just relay

The output has two clearly distinguished layers, not one undifferentiated wall of text:

- **Relayed material** — what Atlas itself found, exactly as MCP returned it, provenance/confidence intact (same as today's scope: facts, computed metrics, Atlas's own `hypothesis`-provenance interpretations from Features 08/09/10).
- **The agent's own interpretation** — a distinct, clearly labeled section or voice (e.g. under a heading like "What this means" / "My read" rather than blended into the facts) where the agent actually says what it thinks the retrieved material adds up to: which hotspot is the one actually worth worrying about and why, whether the architecture hypothesis and the churn/hotspot data reinforce or contradict each other, what it would personally flag as risky or confusing for a newcomer, what it recommends looking at first and in what order. This is not a new Atlas provenance category (Q45's `observed`/`computed`/`inferred`/`hypothesis` vocabulary stays exactly as Feature 01 defined it, unchanged) — it's the *agent's* own voice, on top of and clearly separated from Atlas's facts, the same way a senior engineer's personal take is understood as their take, not as more "official" facts.

The agent is expected to actually take a position (which files matter most, what the real risk is) rather than hedge into a restatement of the raw data — that's the entire reason this feature exists instead of just linking to the Feature 11/11b report. It must still ground that position in what MCP returned (no claims about the codebase invented from nothing) but the position itself — the judgment call — is new content this feature explicitly asks the agent to produce, not a citation.

### What the recipe must say explicitly

- **Never fabricate a fact beyond MCP's response**, but interpretation is expected, not forbidden — see above. If a query returns nothing (`not_analyzed`, empty result), the synthesis says so rather than working around the gap — same "never pretend to know" principle (Product Brief principle 5), applied to the *factual* layer; the interpretation layer may still say "with what little was analyzed, my tentative read is..." rather than staying silent.
- **Distinguish observed/computed from inferred/hypothesis** in the relayed material (e.g. "Atlas found X" vs. "Atlas's architecture interpretation suggests Y, with Z% confidence") — mirroring the same provenance distinction Feature 11/11b render visually — and keep that visually/structurally separate from the agent's own interpretation layer, which carries no `provenance` value at all (it isn't an Atlas fact).
- **Every non-trivial claim in the relayed layer links to its evidence**, same evidence-first requirement as the main report (Q131/Q132) — a synthesis that summarizes without citing is exactly the "interaction-free reading" the user wants, but it must not become "trust me" prose with no way to verify a claim. The interpretation layer should reference which relayed items it's reasoning from (e.g. "given the hotspot in `payments/`, and the layered pattern Atlas identified with 60% confidence...") rather than reading as disconnected opinion.
- **One document per invocation, not a persisted Atlas artifact.** The HTML file is the agent's own output in its own working session (e.g. written to the repository being onboarded onto, or wherever the user asks) — Atlas itself does not store, version, or serve these documents; it has no opinion on where they end up or what happens to a previous one.

## Explicitly out of scope for this feature

- Any new MCP tool/primitive — this feature only documents how to use what Feature 12 already exposes.
- Any change to the HTML report (Feature 11/11b) — independent, complementary path; neither depends on the other.
- A shared HTML-rendering library imported by both Feature 11/11b and this feature's agent — the agent's output is hand-written HTML per the recipe, not a call into `html_report`'s Python code (the agent may have no Python environment at all; it only speaks MCP).
- `.docx`, PDF, or any binary document format — HTML only, per this feature's explicit resolution of Q154b.
- Triggering analysis automatically (**Proposition Q154**, not decided) — this feature's agent recipe assumes an `atlas analyze` run already happened; it does not run one itself.
- A general-purpose agent-building framework — this is one specific, documented recipe (one agent definition + usage instructions), not a toolkit for building arbitrary MCP-consuming agents.

## Acceptance criteria

- An agent definition file exists, documenting: how to point it at a running Atlas MCP server, which MCP primitives it queries and in what order, the provenance/citation rules its output must follow, the expected HTML output shape (badges, evidence links, reused from Feature 11/11b's conventions), and the explicit two-layer structure (relayed material vs. the agent's own interpretation).
- A worked example: run against a small fixture repository already analyzed by `atlas analyze`, the agent recipe (run manually, not necessarily automated in CI given it invokes a real or mocked LLM-driven agent) produces a single self-contained HTML file, openable directly in a browser, whose relayed-material layer cites real facts/evidence returned by the MCP server for that fixture — not fabricated content — and whose interpretation layer is visibly present, distinct, and takes an actual position (not a restatement of the relayed facts in different words).
- The output HTML uses the same provenance/confidence visual convention as Feature 11/11b for the relayed layer (verified by inspecting the generated markup for equivalent badge/marker classes or an explicitly documented equivalent), and a visibly distinct treatment (heading/section/styling) for the interpretation layer that carries no provenance badge.
- The recipe explicitly states, in its own text, that the HTML report (Feature 11/11b) is the standalone full deliverable and this path is a complementary, tailored, agent-driven alternative — not a required step to get a readable report, and not a replacement for it.
- No new file under `src/project_intel/` changes Feature 12's MCP tool surface — this feature is documentation/agent-definition only (verified: no diff to `mcp_server/`).
