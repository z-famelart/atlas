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
evidence: tuple[Evidence, ...] # immutable sequence, see Evidence section below
provenance: Literal["observed", "computed", "inferred", "hypothesis"]  # Q45
confidence: float             # [0,1], Q44
source_analyzer: str
created_at: datetime
schema_version: str           # Q50
run_id: str                   # ties the fact to a specific analysis run, Q46/Q140
```

**Immutability (Décidé Q46):** a `Fact` is never mutated after insertion. Re-analysis produces new `Fact` rows tied to a new `run_id`; nothing is updated or deleted in place. The store's write API must not expose an update/delete-by-id operation for facts — only insert and (for whole-run cleanup, e.g. in tests) delete-by-run_id.

This is enforced at the language level, not only by omitting a mutation method from the store: `Fact` (and `Evidence`, `EntityRef`, `Entity` below) are implemented as `@dataclass(frozen=True, slots=True)`. `frozen=True` makes attribute assignment raise after construction — immutability is a property of the object itself, not just a convention the store API happens to respect. `slots=True` closes the type to any attribute outside the declared fields, so a regenerated version of this feature can't silently grow ad-hoc attributes that later code comes to depend on — the dataclass fields *are* the complete interface (see the [regeneration contract](README.md#regeneration-contract)).

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

`Evidence` and `EntityRef`/`Entity` are, like `Fact`, `@dataclass(frozen=True, slots=True)`. `Fact.evidence`'s declared type is `tuple[Evidence, ...]`, not `list[Evidence]`, precisely so the immutability is visible in the type itself. But a caller is free to construct a `Fact` by passing in a `list[Evidence]` they still hold a reference to (frozen dataclasses don't coerce constructor arguments), so `Fact`'s construction path (a factory function or `__post_init__`-style normalization, since `frozen=True` blocks direct field assignment inside `__init__` too) must convert whatever iterable it's given into a `tuple` before the instance is considered valid — a caller mutating the list they passed in afterward must not be able to affect the already-constructed `Fact`.

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
    def insert_facts(self, facts: Sequence[Fact]) -> None: ...
    def insert_entities(self, entities: Sequence[Entity]) -> None: ...
    def query_facts(self, *, type: str | None = None, subject: EntityRef | None = None,
                     run_id: str | None = None, provenance: str | None = None) -> Iterator[Fact]: ...
    def get_entity(self, ref: EntityRef) -> Entity | None: ...
    def delete_run(self, run_id: str) -> None: ...  # test/debug cleanup only, not a general mutation API
```

**This method signature set is `FactStore`'s stable interface**, per the [regeneration contract](README.md#regeneration-contract): every later feature that touches the store (Features 02–13) is written against exactly these five methods and their documented behavior. Regenerating this feature's implementation from this spec must reproduce this same surface — adding a method is a spec change, not an implementation-time judgment call; removing or changing the signature of one of these five is a breaking change to every feature built on top of it.

**Determinism.** `query_facts` must yield results in a stable, explicit order — `(created_at, id)` ascending — regardless of insertion order or SQLite's incidental row storage order. The query must never rely on unordered `SELECT` output. This is what makes the store's output snapshot-testable (see Acceptance criteria) and what keeps a regenerated implementation behaviorally identical to the one it replaces for the same input data.

Recomputability (**Décidé Q47**) is a direct consequence of this store existing as a standalone, queryable component: any later feature (Calculations, LLM synthesis) must be able to open a `FactStore` from a previous run and read facts without re-invoking any adapter. This feature should include a test that inserts facts under one `run_id`, closes the store, reopens it, and reads them back unchanged — proving the store is the sole source of truth and requires no live analyzer process.

## Explicitly out of scope for this feature

- No adapters, no discovery, no Git/graph/hotspot logic — those are later features and must consume this model, not redefine it.
- No `Project`/multi-repository orchestration logic (feature: not yet scheduled) — only the `Project`/`Repository`/`System`/`Environment` entity *types* need to exist as valid `EntityType` values.
- Anything marked **Ouvert** in Design Decisions (e.g. exact repository-size limits, Q155) is not addressed here; the store must not hard-code assumptions that would need to change once those are decided (e.g. don't assume the whole `facts` table fits in memory).

## Acceptance criteria

- `Fact`, `Evidence`, `EntityRef`, `Entity` are implemented as `@dataclass(frozen=True, slots=True)` matching the shapes above, with `Fact.evidence` typed as `tuple[Evidence, ...]`.
- A test attempts to set an attribute on a constructed `Fact` (and `Evidence`) and asserts it raises (`dataclasses.FrozenInstanceError`) — proving immutability is enforced by the type, not just by the store's API surface.
- A test attempts to set an attribute not in the dataclass's declared fields and asserts it raises (`AttributeError`, from `slots=True`) — proving the type is closed to attribute drift.
- A test mutates the original `list[Evidence]` passed into `Fact(...)` after construction and asserts the constructed `Fact.evidence` is unaffected — proving the store/constructor path defensively copies into the immutable `tuple`.
- `FactStore` backed by SQLite implements exactly the five methods listed above, enforces append-only semantics (no update-by-id), and round-trips through close/reopen.
- `query_facts` determinism: a test inserts facts in a deliberately non-sorted order (e.g. reverse-`created_at`, or via SQLite's default row order) and asserts `query_facts` always returns them in `(created_at, id)` order, on every call, including after reopening the store.
- **Snapshot tests:** a fixed, hand-authored set of `Fact`/`Evidence`/`Entity` instances is serialized (e.g. to JSON) and compared against a checked-in snapshot file (`tests/snapshots/`); a test fails if the serialized shape changes in any way — field added/removed/renamed, type changed, ordering changed — without the snapshot being deliberately updated alongside a spec change. This is what makes this feature regenerable from this spec without silently breaking whatever later feature depends on `Fact`'s exact shape.
- Unit tests cover: insertion + query by type/subject/run_id/provenance, immutability (no update API exists), and the unknown/not-analyzed status values are representable.
- `uv run pytest` and `uv run ruff check .` pass.
