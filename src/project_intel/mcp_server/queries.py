"""Pure query functions over FactStore — no MCP, no I/O, fully testable."""

from __future__ import annotations

import dataclasses
from collections import deque
from typing import Any

from ..facts.enums import EntityType
from ..facts.model import EntityRef, Fact
from ..facts.store import FactStore

_CAP_COMPONENT = 1
_CAP_DEPS = 50
_CAP_HOTSPOTS = 50
_CAP_WORKFLOWS = 20
_CAP_PATH_DEPTH = 10
_CAP_INSIGHTS = 50

# Repository-level interpretation facts (Q143) — their subject is the repository, not a file.
INSIGHT_KINDS = {
    "architecture": "architecture_hypothesis",
    "concepts": "business_concept",
    "glossary": "glossary_term",
}


def _fact_to_dict(fact: Fact) -> dict[str, Any]:
    d = dataclasses.asdict(fact)
    d["subject"] = {"type": fact.subject.type.value, "id": fact.subject.id}
    if fact.object:
        d["object"] = {"type": fact.object.type.value, "id": fact.object.id}
    return d


def _run(store: FactStore, fact_type: str, run_id: str | None) -> str | None:
    """Explicit run_id as given; otherwise the latest run holding `fact_type`.

    Type-scoped so a partial run (`atlas analyze --only architecture`) doesn't hide the
    hotspots/graph facts of the run before it.
    """
    return run_id if run_id is not None else store.run_id_with(fact_type, None)


def get_component(
    store: FactStore, name_or_path: str, run_id: str | None = None
) -> dict[str, Any] | None:
    """Return the first FILE entity matching name_or_path (exact or suffix match).

    Without run_id, each fact type comes from the latest run holding that type.
    """
    subject_id = store.find_subject_id(EntityType.FILE, name_or_path, run_id)
    if subject_id is None:
        return None
    ref = EntityRef(EntityType.FILE, subject_id)
    latest: dict[str, str | None] = {}
    facts = []
    for f in store.query_facts(subject=ref, run_id=run_id):
        if run_id is None:
            if f.type not in latest:
                latest[f.type] = store.latest_run_id(type=f.type)
            if f.run_id != latest[f.type]:
                continue
        facts.append(_fact_to_dict(f))
    result: dict[str, Any] = {"id": subject_id}
    entity = store.get_entity(ref)
    if entity:
        result["attributes"] = entity.attributes
    result["facts"] = facts
    return result


def get_dependencies(
    store: FactStore, component: str, limit: int = 20, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Outbound edges (imports/calls) from component. Hard cap: 50."""
    limit = min(limit, _CAP_DEPS)
    run_id = _run(store, "imports", run_id)
    ref = EntityRef(type=EntityType.FILE, id=component)
    results = []
    for fact in store.query_facts(subject=ref, run_id=run_id):
        if fact.type in ("imports", "calls") and fact.object:
            results.append(_fact_to_dict(fact))
            if len(results) >= limit:
                break
    return results


def get_dependents(
    store: FactStore, component: str, limit: int = 20, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Inbound edges (imports/calls) targeting component. Hard cap: 50."""
    limit = min(limit, _CAP_DEPS)
    run_id = _run(store, "imports", run_id)
    results = []
    for fact in store.query_facts(run_id=run_id):
        if fact.type in ("imports", "calls") and fact.object and fact.object.id == component:
            results.append(_fact_to_dict(fact))
            if len(results) >= limit:
                break
    return results


def find_workflow(
    store: FactStore, query: str, limit: int = 10, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Substring search over business_workflow facts. Hard cap: 20."""
    limit = min(limit, _CAP_WORKFLOWS)
    run_id = _run(store, "business_workflow", run_id)
    lower = query.lower()
    results = []
    for fact in store.query_facts(type="business_workflow", run_id=run_id):
        text = ""
        if isinstance(fact.value, dict):
            text = " ".join(str(v) for v in fact.value.values())
        elif fact.value is not None:
            text = str(fact.value)
        if lower in text.lower() or lower in fact.subject.id.lower():
            results.append(_fact_to_dict(fact))
            if len(results) >= limit:
                break
    return results


def get_hotspots(
    store: FactStore,
    top_n: int = 10,
    component: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """hotspot_score facts sorted by combined descending. Hard cap: 50."""
    top_n = min(top_n, _CAP_HOTSPOTS)
    run_id = _run(store, "hotspot_score", run_id)
    facts = list(store.query_facts(type="hotspot_score", run_id=run_id))
    if component:
        facts = [f for f in facts if component in f.subject.id]
    facts.sort(key=lambda f: (f.value or {}).get("combined", 0.0), reverse=True)
    return [_fact_to_dict(f) for f in facts[:top_n]]


def get_path(
    store: FactStore,
    component_a: str,
    component_b: str,
    max_depth: int = 5,
    run_id: str | None = None,
) -> dict[str, Any]:
    """BFS shortest path in imports/calls graph. max_depth hard cap: 10.

    ponytail: BFS over adjacency list built in one pass; adjacency is rebuilt per
    call (no persistent graph), upgrade to a cached NetworkX graph if called in
    hot loops.
    """
    max_depth = min(max_depth, _CAP_PATH_DEPTH)
    run_id = _run(store, "imports", run_id)

    # Build adjacency from facts
    adj: dict[str, list[str]] = {}
    for fact in store.query_facts(run_id=run_id):
        if fact.type in ("imports", "calls") and fact.object:
            adj.setdefault(fact.subject.id, []).append(fact.object.id)

    if component_a not in adj and component_a != component_b:
        return {"found": False, "reason": "no path within bound", "path": []}

    # BFS
    queue: deque[tuple[str, list[str]]] = deque([(component_a, [component_a])])
    visited = {component_a}
    while queue:
        node, path = queue.popleft()
        if len(path) > max_depth + 1:
            break
        for neighbor in adj.get(node, []):
            if neighbor == component_b:
                return {"found": True, "path": path + [neighbor]}
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return {"found": False, "reason": "no path within bound", "path": []}


def where_to_start(
    store: FactStore,
    component: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return onboarding_path facts if present, else top hotspots + high-centrality files."""
    onboarding = list(
        store.query_facts(type="onboarding_path", run_id=_run(store, "onboarding_path", run_id))
    )
    if component:
        onboarding = [f for f in onboarding if component in f.subject.id]

    if onboarding:
        return [_fact_to_dict(f) for f in onboarding[:20]]

    # Fallback: top 5 hotspots + top 5 high in-degree centrality files
    hotspots = get_hotspots(store, top_n=5, component=component, run_id=run_id)

    centrality = list(
        store.query_facts(type="centrality", run_id=_run(store, "centrality", run_id))
    )
    if component:
        centrality = [f for f in centrality if component in f.subject.id]
    centrality.sort(
        key=lambda f: (f.value or {}).get("in_degree", 0.0),
        reverse=True,
    )
    centrality_dicts = [_fact_to_dict(f) for f in centrality[:5]]

    return hotspots + centrality_dicts


def get_insights(
    store: FactStore, kind: str, limit: int = 10, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Repository-level interpretation facts of `kind` (see INSIGHT_KINDS), highest
    confidence first. Hard cap: 50. Raises ValueError for an unknown kind."""
    if kind not in INSIGHT_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(INSIGHT_KINDS)}")
    fact_type = INSIGHT_KINDS[kind]
    facts = list(store.query_facts(type=fact_type, run_id=_run(store, fact_type, run_id)))
    facts.sort(key=lambda f: f.confidence, reverse=True)
    return [_fact_to_dict(f) for f in facts[: min(limit, _CAP_INSIGHTS)]]
