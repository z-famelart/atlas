# Feature specs

Each file is one feature, scoped strictly to points marked **Décidé** in [`../Design Decisions.md`](../Design%20Decisions.md). Nothing marked **Proposition** or **Ouvert** is implemented as if decided — where a feature depends on an undecided point, its spec says so explicitly under "Explicitly out of scope" and defers it.

Build (and commit) in this order — each feature depends only on the ones before it:

1. [Facts & Evidence model](01-facts-and-evidence-model.md) — the data model and store everything else is built on.
2. [Adapter framework](02-adapter-framework.md) — generic contract for wrapping external tools.
3. [Discovery](03-discovery.md) — **Part A** (buildable now): signature-based framework/build/CI/IaC detection, Git presence, documents, scope enforcement. **Part B** (gated, see below): the concrete language/LOC adapter.
4. [Git analysis](04-git-analysis.md) — churn, co-change, rename-aware history.
5. [Code graph](05-code-graph.md) — **Part A** (buildable now): `GraphProvider` protocol, multi-level aggregation, centrality/communities/cycles, all tested against fixture facts. **Part B** (gated): the concrete `GraphProvider`.
6. [Hotspots](06-hotspots.md) — **Part A** (buildable now): the scoring engine (normalization, combination, decomposition, missing-data handling, weights), tested against fixture facts. **Part B** (gated): the concrete complexity adapter.
6b. [Minimal CLI](06b-minimal-cli.md) — a walking-skeleton `project-intel analyze`/`facts query`. Does **not** depend on Feature 06 — it's buildable as soon as 01/02 exist, and runs whatever subset of 03/04/05/06/08/09/10 is registered at the time, so the deterministic (and later LLM) pipeline is testable incrementally, feature by feature, without waiting for the full CLI.
7. [LLM orchestration framework](07-llm-orchestration.md) — provider abstraction, citations, caching, budget. **Already implemented** — its spec is a stable record of what shipped (`ClaudeCodeProvider` as the current default) and must not be rewritten to add new providers; see 07b below for how those are added instead.
7b. [Ollama local provider](07b-ollama-provider.md) — a second `LLMProvider` implementation for a local Ollama + Qwen setup, added additively on top of the already-shipped Feature 07 without changing its interface or default. Doesn't depend on Feature 08/09/10.
8. [Architecture interpretation](08-architecture-interpretation.md) — sourced architectural hypotheses. **Already implemented.**
9. [Domain understanding](09-domain-understanding.md) — business concepts/workflows/glossary.
10. [Onboarding path](10-onboarding-path.md) — synthesis of 05/06/08/09 into a recommended entry path.
11. [HTML report](11-html-report.md) — the primary output.
12. [MCP server](12-mcp-server.md) — the **AI-facing** entry point (read-only, bounded queries over the `FactStore` for a coding agent).
13. [CLI](13-cli.md) — the **human-facing** entry point: extends 06b with config file, multi-repo, selective runs, leveled logging (verbosity + actionable LLM-failure detail), interactive prompts for missing config, and LLM/report wiring.

**[02b — MVP scope decision](02b-mvp-scope-decision.md)** is not a numbered build step but a mandatory checkpoint: the Part B of Features 03, 05, and 06 above each require a language/tool choice that's still **Ouvert** (Q193, Q21/Q192) in `Design Decisions.md`. Whichever agent is first to reach one of those Part Bs must stop and ask the user directly for the answer, then record it by updating `Design Decisions.md` — see 02b for the exact rule. Don't guess a language "as an example" to unblock yourself; that silently turns a guess into the de facto MVP scope. All the Part A halves have no such dependency and are buildable in the order above without waiting on 02b. (As of this writing, 02b has already been resolved — see its Resolution section.)

## CLI and MCP: two entry points, one audience each

Project Intelligence has exactly two front-ends, matching its two audiences (Product Brief §5): the **CLI** (06b, extended by 13) is how a **human** runs an analysis and reads the report; the **MCP server** (12) is how a **coding agent** queries the same already-collected facts live. They are independent — each opens its own connection to the `FactStore`, neither wraps the other (see [12](12-mcp-server.md)'s "CLI vs. MCP" note). This means an agent can query a project's facts via MCP without ever invoking the CLI itself, and a human can run `project-intel analyze` without the MCP server involved at all.

## Stage registration: how each feature plugs into the CLI automatically

Every feature that produces facts as an analysis step (03, 04, 05, 06, 08, 09, 10) exposes a module-level `STAGE: Stage` object and adds it to `STAGE_REGISTRY` (one import + one list entry, defined in [06b](06b-minimal-cli.md)) as part of its own Acceptance criteria — each such feature's spec has a "CLI stage registration" subsection saying so. This is a fixed, explicit list, not a dynamic plugin-discovery mechanism (Q189, plugin mechanism, is still **Proposition** — building auto-discovery now would be speculative). The result: 06b's runner code never needs to change as new features land; only the registry file gains one line per feature.

Each feature's spec has a fixed shape: Depends on, Goal, Scope (with the exact **Décidé** question numbers it implements), Explicitly out of scope (with the **Proposition**/**Ouvert** questions it deliberately does not resolve), and Acceptance criteria. Features 03/05/06 additionally split Scope and Acceptance criteria into Part A / Part B, per the gating rule above; 03/04/05/06/08/09/10 additionally have a "CLI stage registration" subsection, per the registration contract above.

## Logging: a convention every feature follows

Per **Décidé Q170** (resolved 2026-09-14, after real dogfooding — `atlas analyze` runs producing opaque failures with no usable detail): logging is not a Feature 13/CLI-only concern, it's a convention every feature that makes an external or LLM call follows, the same way the [Stage registration](#stage-registration-how-each-feature-plugs-into-the-cli-automatically) contract above is a convention rather than a single feature's job. Concretely:

- **Stdlib `logging` only, no new dependency for this part.** One logger per module: `logging.getLogger(__name__)`.
- **Three fixed levels, same meaning everywhere:**
  - `WARNING` — any failure (adapter, LLM call, stage) logs one line with enough to act on it: component, target (adapter name, or `provider_id`+model), and the underlying error (exception type/message, HTTP status, etc.) — never just a bare status code with no detail.
  - `INFO` — one line per external call as it happens (adapter invoked, LLM call made/served from cache, stage started/finished).
  - `DEBUG` — the raw payload (adapter's exact invocation + pre-normalization output, full LLM prompt/response).
- **No raw potentially-sensitive payload below `DEBUG`** — only shape/metadata (component, target, size, duration, error), consistent with the evidence-first transparency principle applied to the tool itself.
- **This is an internal addition only** — per the [regeneration contract](#regeneration-contract), adding `logger.<level>(...)` calls inside an already-implemented feature's code changes no public interface, so it doesn't require a new lettered-suffix feature the way a real capability change would; each already-implemented feature that makes external/LLM calls (02, 03 Part B, 04, 05 Part B, 06 Part B, 07, 07b, 08) has a short "Logging" subsection added retroactively, the same way 06b retroactively added "CLI stage registration" subsections.
- **Configuring and rendering these logs (verbosity flags, handlers, the live per-stage progress display) is [Feature 13](13-cli.md)'s job** — every other feature only emits records via its own logger; it never touches `logging` handler/formatter configuration itself.

## Dogfooding smoke test

Once a feature touching `analyze` is implemented, tested, and linted, run it for real against two fixed targets — Atlas's own repository and a larger real one — before calling it done; see [CLAUDE.md](../../CLAUDE.md#dogfooding-smoke-test) for the exact commands. This caught the gap that led to [Feature 13](13-cli.md)'s logging/verbosity scope: automated tests passed while a real run still produced an unhelpful `not_analyzed: llm_failed` with no way to tell why.

## Regeneration contract

These specs are the source of truth, not the code. The implementation must be regenerable from a feature's spec — by a human or an agent, from scratch — without breaking the running app, as long as the spec itself hasn't changed. Every feature spec must be written so that's actually possible:

- **Interfaces are the contract, not an implementation detail.** The types/classes/function signatures a spec lists under "Scope" are what later features and the app depend on. Regenerating a feature's code from its spec must reproduce the same public interface; if a spec doesn't change, its interface shouldn't either, even if the internals do.
- **Data types are immutable and closed.** Where a spec doesn't call for dynamic/extensible attributes, implement it as a frozen, slotted type (Python: `@dataclass(frozen=True, slots=True)`) — this makes "no attribute drift, no accidental mutation" a language-enforced property of regenerated code, not a convention someone can forget.
- **Behavior is deterministic.** Anything that returns an ordered result (query methods, list-producing calculations) must have an explicit, spec-mandated ordering — never left to incidental storage/iteration order — so the same inputs always produce byte-identical output across a regeneration.
- **Tests pin shape, not just behavior.** Prefer snapshot/golden tests that fail on any unintended change to a produced artifact's exact shape (serialized fact, query result, generated file) over tests that only assert "it doesn't crash." A looser test lets an interface silently drift across a regeneration; a snapshot test catches it immediately.

Feature 01 is the first place these rules are applied concretely (frozen+slotted dataclasses, a deterministic `FactStore` interface, snapshot-tested output) — later features should follow the same pattern rather than reinvent it.

**Once a feature is implemented, its spec becomes a historical record of a stable interface, not a draft to keep editing.** Wanting new capability in an already-shipped feature (a new provider, a new adapter, a new primitive) is not a reason to rewrite that feature's spec — it's a reason to add a new, lettered-suffix feature that depends on it additively, the same way [02b](02b-mvp-scope-decision.md), [06b](06b-minimal-cli.md), and [07b](07b-ollama-provider.md) were inserted after the fact. Check the actual source tree (or ask) before editing any numbered feature spec whose number is lower than what's already been implemented.
