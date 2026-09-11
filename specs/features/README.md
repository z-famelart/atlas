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
