"""Level roll-up: aggregate file-level facts to module (directory) or system level.

Uses `belongs_to` relation facts already in FactStore to discover the containing
directory for each file.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import UTC, datetime

from project_intel.facts.enums import EntityType, RelationType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore

SOURCE_ANALYZER = "code_graph_metrics@1.0"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_fact(
    *,
    fact_type: str,
    subject: EntityRef,
    value: object,
    evidence: tuple[Evidence, ...],
    run_id: str,
) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=subject,
        value=value,
        evidence=evidence,
        provenance="computed",
        confidence=1.0,
        source_analyzer=SOURCE_ANALYZER,
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )


def _find_parent(file_id: str, store: FactStore) -> str | None:
    """Return the parent entity ID for a file by querying belongs_to facts."""
    for fact in store.query_facts(
        type=RelationType.BELONGS_TO.value,
        subject=EntityRef(EntityType.FILE, file_id),
    ):
        if fact.object is not None:
            return fact.object.id
    return None


def aggregate_to_module(facts: list[Fact], store: FactStore, level: str) -> list[Fact]:
    """Roll up file-level facts to 'module' (directory) or 'system' level.

    Groups input facts by their containing entity (via belongs_to relations in
    store). For 'system' level, all facts are grouped under a single "." root.

    Supported input fact types:
    - "centrality": aggregates mean in/out degree per parent entity
    - "community": lists unique community IDs per parent entity
    - "dependency_cycle": lists unique cycle members per parent entity
    """
    if level not in ("module", "system"):
        raise ValueError(f"level must be 'module' or 'system', got {level!r}")

    # Group facts by parent entity
    groups: dict[str, list[Fact]] = {}
    for fact in facts:
        if level == "system":
            parent_id = "."
        else:
            parent_id = _find_parent(fact.subject.id, store)
        if parent_id is None:
            continue
        groups.setdefault(parent_id, []).append(fact)

    if not facts:
        return []

    run_id = facts[0].run_id
    parent_entity_type = EntityType.SYSTEM if level == "system" else EntityType.DIRECTORY

    result: list[Fact] = []
    for parent_id, group in groups.items():
        # Collect file refs for evidence
        evidence = tuple(
            Evidence(
                kind="file",
                ref=FileRef(repository_id="", path=f.subject.id),
                source_analyzer=SOURCE_ANALYZER,
                retrieved_at=_now(),
            )
            for f in group
        )
        # Aggregate by fact type (all facts in a group should share a type)
        fact_type = group[0].type
        if fact_type == "centrality":
            in_degs = [f.value["in_degree"] for f in group if isinstance(f.value, dict)]
            out_degs = [f.value["out_degree"] for f in group if isinstance(f.value, dict)]
            value: object = {
                "mean_in_degree": statistics.mean(in_degs) if in_degs else 0.0,
                "mean_out_degree": statistics.mean(out_degs) if out_degs else 0.0,
                "file_count": len(group),
            }
        elif fact_type == "community":
            community_ids = sorted(
                {f.value["community_id"] for f in group if isinstance(f.value, dict)}
            )
            value = {"community_ids": community_ids, "file_count": len(group)}
        elif fact_type == "dependency_cycle":
            all_members: list[str] = []
            seen: set[str] = set()
            for f in group:
                if isinstance(f.value, dict):
                    for m in f.value.get("cycle_members", []):
                        if m not in seen:
                            all_members.append(m)
                            seen.add(m)
            value = {"cycle_members": sorted(all_members), "file_count": len(group)}
        else:
            value = {"file_count": len(group)}

        result.append(
            _make_fact(
                fact_type=fact_type,
                subject=EntityRef(parent_entity_type, parent_id),
                value=value,
                evidence=evidence,
                run_id=run_id,
            )
        )
    return result
