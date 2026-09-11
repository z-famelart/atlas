# Feature specs

Each file is one feature, scoped strictly to points marked **Décidé** in [`../Design Decisions.md`](../Design%20Decisions.md). Nothing marked **Proposition** or **Ouvert** is implemented as if decided — where a feature depends on an undecided point, its spec says so explicitly under "Explicitly out of scope" and defers it.

Build (and commit) in this order — each feature depends only on the ones before it:

1. [Facts & Evidence model](01-facts-and-evidence-model.md) — the data model and store everything else is built on.
2. [Adapter framework](02-adapter-framework.md) — generic contract for wrapping external tools.
3. [Discovery](03-discovery.md) — languages, frameworks, build systems, IaC/CI/container presence.
4. [Git analysis](04-git-analysis.md) — churn, co-change, rename-aware history.
5. [Code graph](05-code-graph.md) — structural extraction + centrality/communities/cycles.
6. [Hotspots](06-hotspots.md) — explainable score combining complexity, size, centrality, churn.
7. [LLM orchestration framework](07-llm-orchestration.md) — provider abstraction, citations, caching, budget.
8. [Architecture interpretation](08-architecture-interpretation.md) — sourced architectural hypotheses.
9. [Domain understanding](09-domain-understanding.md) — business concepts/workflows/glossary.
10. [Onboarding path](10-onboarding-path.md) — synthesis of 05/06/08/09 into a recommended entry path.
11. [HTML report](11-html-report.md) — the primary output.
12. [MCP server](12-mcp-server.md) — the agent-facing output.
13. [CLI](13-cli.md) — `project-intel analyze <scope>`, wiring it all together.

Each feature's spec has a fixed shape: Depends on, Goal, Scope (with the exact **Décidé** question numbers it implements), Explicitly out of scope (with the **Proposition**/**Ouvert** questions it deliberately does not resolve), and Acceptance criteria.

## Regeneration contract

These specs are the source of truth, not the code. The implementation must be regenerable from a feature's spec — by a human or an agent, from scratch — without breaking the running app, as long as the spec itself hasn't changed. Every feature spec must be written so that's actually possible:

- **Interfaces are the contract, not an implementation detail.** The types/classes/function signatures a spec lists under "Scope" are what later features and the app depend on. Regenerating a feature's code from its spec must reproduce the same public interface; if a spec doesn't change, its interface shouldn't either, even if the internals do.
- **Data types are immutable and closed.** Where a spec doesn't call for dynamic/extensible attributes, implement it as a frozen, slotted type (Python: `@dataclass(frozen=True, slots=True)`) — this makes "no attribute drift, no accidental mutation" a language-enforced property of regenerated code, not a convention someone can forget.
- **Behavior is deterministic.** Anything that returns an ordered result (query methods, list-producing calculations) must have an explicit, spec-mandated ordering — never left to incidental storage/iteration order — so the same inputs always produce byte-identical output across a regeneration.
- **Tests pin shape, not just behavior.** Prefer snapshot/golden tests that fail on any unintended change to a produced artifact's exact shape (serialized fact, query result, generated file) over tests that only assert "it doesn't crash." A looser test lets an interface silently drift across a regeneration; a snapshot test catches it immediately.

Feature 01 is the first place these rules are applied concretely (frozen+slotted dataclasses, a deterministic `FactStore` interface, snapshot-tested output) — later features should follow the same pattern rather than reinvent it.
