# Feature 01 — Facts & Evidence model

## Why this is first

Every other feature (adapters, discovery, Git analysis, code graph, hotspots, LLM synthesis, report, MCP) produces or consumes `Fact` records. Nothing else can be built until this model and its persistence exist. This feature has no dependency on any other feature.

## Goal

Implement the core data model (`Fact`, `Evidence`, entity/relation types) and its persistent store, exactly as decided in [Design Decisions §D](../Design%20Decisions.md#d-normalized-facts). This feature is data-model-only: no adapters, no analyzers, no CLI wiring yet.

## Scope

### `Fact`

Per **Décidé Q34**, a `Fact` has:

```
id: str                       # stable unique id
type: str                     # fact type discriminator (e.g. "file_exists", "depends_on", "loc")
subject: EntityRef            # entity the fact is about
predicate: str | None         # present for relation facts
object: EntityRef | None      # present for relation facts
value: Any | None             # present for scalar/metric facts
evidence: list[Evidence]
provenance: Literal["observed", "computed", "inferred", "hypothesis"]  # Q45
confidence: float             # [0,1], Q44
source_analyzer: str
created_at: datetime
schema_version: str           # Q50
run_id: str                   # ties the fact to a specific analysis run, Q46/Q140
```

**Immutability (Décidé Q46):** a `Fact` is never mutated after insertion. Re-analysis produces new `Fact` rows tied to a new `run_id`; nothing is updated or deleted in place. The store's write API must not expose an update/delete-by-id operation for facts — only insert and (for whole-run cleanup, e.g. in tests) delete-by-run_id.

### Entities (Décidé Q35)

MVP entity types: `System`, `Environment`, `Repository`, `Project`, `Directory`, `File`, `Symbol`, `Commit`, `Contributor`, `Service`, `Database`, `Queue`, `ExternalSource`, `Tool`, `Document`.

An `EntityRef` is `{ type: EntityType, id: str }` — a lightweight pointer, not the full entity record. Entities themselves (name, path, metadata) are stored separately from facts about them; a `Fact` never duplicates entity attributes it can reference by id.

### Relations (Décidé Q36)

MVP relation types (used as `predicate` on relation facts): `depends_on`, `calls`, `imports`, `inherits_from`, `contains`, `belongs_to`, `changed_in`, `authored_by`, `deployed_by`, `communicates_with`, `documents`, `tests`.

### `Evidence` (Décidé Q37–Q42)

```
kind: Literal["file", "line", "symbol", "commit", "config", "tool_output", "documentation", "external"]
ref: EvidenceRef              # shape depends on kind, see below
source_analyzer: str
retrieved_at: datetime
```

`EvidenceRef` shapes, per kind:
- `file` → `{ repository_id, path }` (Q38: relative path, never absolute)
- `line` → `{ repository_id, path, line_start, line_end?, commit_hash }` (Q39: commit hash pinned for invalidation)
- `symbol` → `{ repository_id, path, symbol_id, line_start?, line_end? }` (Q40: qualified name from the graph provider)
- `commit` → `{ repository_id, commit_hash }` (Q41: full hash only)
- `config` → `{ repository_id, path }`
- `tool_output` → `{ source_analyzer, raw_ref }` (opaque pointer into the analyzer's captured output)
- `documentation` → `{ repository_id, path }`
- `external` → `{ source_type, identifier, url? }` (Q42: reference only, never stores extracted sensitive content)

No `Fact` may omit `evidence` — an empty list is invalid for anything above a trivial `observed` discovery fact (e.g. "this file exists" may cite itself as its own evidence).

### Unknown / not-analyzed state (Décidé Q6, Q7, Q19, Q29, Q119)

A field is never left implicitly empty. Where a value is expected but unavailable, the fact's `value` is explicitly `None` and `type` or an accompanying `status` field carries one of: `unknown`, `not_analyzed`, `insufficient_evidence`, `skipped:tool_not_found`, `skipped:version_mismatch`, `failed`. This feature only needs to define these as a closed enum used consistently by later features (adapters, section C) — it does not itself produce any of these statuses.

## Store

Per **Décidé Q48/Q49**: facts are persisted in **SQLite**. Schema:

- `facts` table — one row per `Fact`, with `evidence` stored as a normalized child table (`fact_evidence`) rather than a JSON blob, so evidence is queryable (needed later by the HTML report's click-to-evidence requirement and by the MCP server).
- `entities` table — one row per known entity (`type`, `id`, `attributes` as JSON for type-specific fields, `repository_id` where applicable).
- Both tables carry `schema_version` (Q50); the store checks this against the code's expected version on open and refuses to write with a mismatched schema rather than silently upgrading.

Store API surface for this feature (Python, `project_intel.facts`):

```python
class FactStore:
    def __init__(self, path: Path) -> None: ...
    def insert_facts(self, facts: list[Fact]) -> None: ...
    def insert_entities(self, entities: list[Entity]) -> None: ...
    def query_facts(self, *, type: str | None = None, subject: EntityRef | None = None,
                     run_id: str | None = None, provenance: str | None = None) -> Iterator[Fact]: ...
    def get_entity(self, ref: EntityRef) -> Entity | None: ...
    def delete_run(self, run_id: str) -> None: ...  # test/debug cleanup only, not a general mutation API
```

Recomputability (**Décidé Q47**) is a direct consequence of this store existing as a standalone, queryable component: any later feature (Calculations, LLM synthesis) must be able to open a `FactStore` from a previous run and read facts without re-invoking any adapter. This feature should include a test that inserts facts under one `run_id`, closes the store, reopens it, and reads them back unchanged — proving the store is the sole source of truth and requires no live analyzer process.

## Explicitly out of scope for this feature

- No adapters, no discovery, no Git/graph/hotspot logic — those are later features and must consume this model, not redefine it.
- No `Project`/multi-repository orchestration logic (feature: not yet scheduled) — only the `Project`/`Repository`/`System`/`Environment` entity *types* need to exist as valid `EntityType` values.
- Anything marked **Ouvert** in Design Decisions (e.g. exact repository-size limits, Q155) is not addressed here; the store must not hard-code assumptions that would need to change once those are decided (e.g. don't assume the whole `facts` table fits in memory).

## Acceptance criteria

- `Fact`, `Evidence`, `EntityRef`, `Entity` are implemented as typed dataclasses (or equivalent) matching the shapes above.
- `FactStore` backed by SQLite implements insert/query for facts and entities, enforces append-only semantics (no update-by-id), and round-trips through close/reopen.
- Unit tests cover: insertion + query by type/subject/run_id/provenance, immutability (no update API exists), and the unknown/not-analyzed status values are representable.
- `uv run pytest` and `uv run ruff check .` pass.
