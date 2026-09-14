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


def _fact_to_dict(fact: Fact) -> dict[str, Any]:
    d = dataclasses.asdict(fact)
    d["subject"] = {"type": fact.subject.type.value, "id": fact.subject.id}
    if fact.object:
        d["object"] = {"type": fact.object.type.value, "id": fact.object.id}
    return d


def get_component(store: FactStore, name_or_path: str) -> dict[str, Any] | None:
    """Return the first FILE entity matching name_or_path (exact or suffix match)."""
    lower = name_or_path.lower()
    for fact in store.query_facts():
        if fact.subject.type != EntityType.FILE:
            continue
        sid = fact.subject.id.lower()
        if sid == lower or sid.endswith("/" + lower):
            entity = store.get_entity(fact.subject)
            result: dict[str, Any] = {"id": fact.subject.id}
            if entity:
                result["attributes"] = entity.attributes
            facts = [
                _fact_to_dict(f)
                for f in store.query_facts(subject=fact.subject)
            ]
            result["facts"] = facts
            return result
    return None


def get_dependencies(store: FactStore, component: str, limit: int = 20) -> list[dict[str, Any]]:
    """Outbound edges (imports/calls) from component. Hard cap: 50."""
    limit = min(limit, _CAP_DEPS)
    ref = EntityRef(type=EntityType.FILE, id=component)
    results = []
    for fact in store.query_facts(subject=ref):
        if fact.type in ("imports", "calls") and fact.object:
            results.append(_fact_to_dict(fact))
            if len(results) >= limit:
                break
    return results


def get_dependents(store: FactStore, component: str, limit: int = 20) -> list[dict[str, Any]]:
    """Inbound edges (imports/calls) targeting component. Hard cap: 50."""
    limit = min(limit, _CAP_DEPS)
    results = []
    for fact in store.query_facts():
        if fact.type in ("imports", "calls") and fact.object and fact.object.id == component:
            results.append(_fact_to_dict(fact))
            if len(results) >= limit:
                break
    return results


def find_workflow(store: FactStore, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Substring search over business_workflow facts. Hard cap: 20."""
    limit = min(limit, _CAP_WORKFLOWS)
    lower = query.lower()
    results = []
    for fact in store.query_facts(type="business_workflow"):
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
) -> list[dict[str, Any]]:
    """hotspot_score facts sorted by combined_score descending. Hard cap: 50."""
    top_n = min(top_n, _CAP_HOTSPOTS)
    facts = list(store.query_facts(type="hotspot_score"))
    if component:
        facts = [f for f in facts if component in f.subject.id]
    facts.sort(key=lambda f: (f.value or {}).get("combined_score", 0.0), reverse=True)
    return [_fact_to_dict(f) for f in facts[:top_n]]


def get_path(
    store: FactStore,
    component_a: str,
    component_b: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    """BFS shortest path in imports/calls graph. max_depth hard cap: 10.

    ponytail: BFS over adjacency list built in one pass; adjacency is rebuilt per
    call (no persistent graph), upgrade to a cached NetworkX graph if called in
    hot loops.
    """
    max_depth = min(max_depth, _CAP_PATH_DEPTH)

    # Build adjacency from facts
    adj: dict[str, list[str]] = {}
    for fact in store.query_facts():
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
) -> list[dict[str, Any]]:
    """Return onboarding_path facts if present, else top hotspots + high-centrality files."""
    onboarding = list(store.query_facts(type="onboarding_path"))
    if component:
        onboarding = [f for f in onboarding if component in f.subject.id]

    if onboarding:
        return [_fact_to_dict(f) for f in onboarding[:20]]

    # Fallback: top 5 hotspots + top 5 high in-degree centrality files
    hotspots = get_hotspots(store, top_n=5, component=component)

    centrality = list(store.query_facts(type="centrality"))
    if component:
        centrality = [f for f in centrality if component in f.subject.id]
    centrality.sort(
        key=lambda f: (f.value or {}).get("in_degree", 0.0),
        reverse=True,
    )
    centrality_dicts = [_fact_to_dict(f) for f in centrality[:5]]

    return hotspots + centrality_dicts
