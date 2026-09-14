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
7. [LLM orchestration framework](07-llm-orchestration.md) — provider abstraction, citations, caching, budget.
8. [Architecture interpretation](08-architecture-interpretation.md) — sourced architectural hypotheses.
9. [Domain understanding](09-domain-understanding.md) — business concepts/workflows/glossary.
10. [Onboarding path](10-onboarding-path.md) — synthesis of 05/06/08/09 into a recommended entry path.
11. [HTML report](11-html-report.md) — the primary output.
12. [MCP server](12-mcp-server.md) — the **AI-facing** entry point (read-only, bounded queries over the `FactStore` for a coding agent).
13. [CLI](13-cli.md) — the **human-facing** entry point: extends 06b with config file, multi-repo, selective runs, debugging, and LLM/report wiring.

**[02b — MVP scope decision](02b-mvp-scope-decision.md)** is not a numbered build step but a mandatory checkpoint: the Part B of Features 03, 05, and 06 above each require a language/tool choice that's still **Ouvert** (Q193, Q21/Q192) in `Design Decisions.md`. Whichever agent is first to reach one of those Part Bs must stop and ask the user directly for the answer, then record it by updating `Design Decisions.md` — see 02b for the exact rule. Don't guess a language "as an example" to unblock yourself; that silently turns a guess into the de facto MVP scope. All the Part A halves have no such dependency and are buildable in the order above without waiting on 02b. (As of this writing, 02b has already been resolved — see its Resolution section.)

## CLI and MCP: two entry points, one audience each

Project Intelligence has exactly two front-ends, matching its two audiences (Product Brief §5): the **CLI** (06b, extended by 13) is how a **human** runs an analysis and reads the report; the **MCP server** (12) is how a **coding agent** queries the same already-collected facts live. They are independent — each opens its own connection to the `FactStore`, neither wraps the other (see [12](12-mcp-server.md)'s "CLI vs. MCP" note). This means an agent can query a project's facts via MCP without ever invoking the CLI itself, and a human can run `project-intel analyze` without the MCP server involved at all.

## Stage registration: how each feature plugs into the CLI automatically

Every feature that produces facts as an analysis step (03, 04, 05, 06, 08, 09, 10) exposes a module-level `STAGE: Stage` object and adds it to `STAGE_REGISTRY` (one import + one list entry, defined in [06b](06b-minimal-cli.md)) as part of its own Acceptance criteria — each such feature's spec has a "CLI stage registration" subsection saying so. This is a fixed, explicit list, not a dynamic plugin-discovery mechanism (Q189, plugin mechanism, is still **Proposition** — building auto-discovery now would be speculative). The result: 06b's runner code never needs to change as new features land; only the registry file gains one line per feature.

Each feature's spec has a fixed shape: Depends on, Goal, Scope (with the exact **Décidé** question numbers it implements), Explicitly out of scope (with the **Proposition**/**Ouvert** questions it deliberately does not resolve), and Acceptance criteria. Features 03/05/06 additionally split Scope and Acceptance criteria into Part A / Part B, per the gating rule above; 03/04/05/06/08/09/10 additionally have a "CLI stage registration" subsection, per the registration contract above.

## Regeneration contract

These specs are the source of truth, not the code. The implementation must be regenerable from a feature's spec — by a human or an agent, from scratch — without breaking the running app, as long as the spec itself hasn't changed. Every feature spec must be written so that's actually possible:

- **Interfaces are the contract, not an implementation detail.** The types/classes/function signatures a spec lists under "Scope" are what later features and the app depend on. Regenerating a feature's code from its spec must reproduce the same public interface; if a spec doesn't change, its interface shouldn't either, even if the internals do.
- **Data types are immutable and closed.** Where a spec doesn't call for dynamic/extensible attributes, implement it as a frozen, slotted type (Python: `@dataclass(frozen=True, slots=True)`) — this makes "no attribute drift, no accidental mutation" a language-enforced property of regenerated code, not a convention someone can forget.
- **Behavior is deterministic.** Anything that returns an ordered result (query methods, list-producing calculations) must have an explicit, spec-mandated ordering — never left to incidental storage/iteration order — so the same inputs always produce byte-identical output across a regeneration.
- **Tests pin shape, not just behavior.** Prefer snapshot/golden tests that fail on any unintended change to a produced artifact's exact shape (serialized fact, query result, generated file) over tests that only assert "it doesn't crash." A looser test lets an interface silently drift across a regeneration; a snapshot test catches it immediately.

Feature 01 is the first place these rules are applied concretely (frozen+slotted dataclasses, a deterministic `FactStore` interface, snapshot-tested output) — later features should follow the same pattern rather than reinvent it.
