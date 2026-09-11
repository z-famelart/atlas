"""Graph metric computations over facts in FactStore.

Operates on relation facts already inserted by a GraphProvider. Emits computed
centrality, community, and cycle facts back into the store's in-memory usage
(callers insert the returned list if desired).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import networkx as nx

from project_intel.facts.enums import EntityType, RelationType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore

SOURCE_ANALYZER = "code_graph_metrics@1.0"

# Relation types that constitute the code graph edges
_GRAPH_RELATION_TYPES = {
    RelationType.IMPORTS.value,
    RelationType.CALLS.value,
    RelationType.DEPENDS_ON.value,
    RelationType.INHERITS_FROM.value,
}


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _file_evidence(repository_id: str, path: str) -> Evidence:
    return Evidence(
        kind="file",
        ref=FileRef(repository_id=repository_id, path=path),
        source_analyzer=SOURCE_ANALYZER,
        retrieved_at=_now(),
    )


def _build_graph(store: FactStore) -> nx.DiGraph:
    """Build a DiGraph from relation facts in store."""
    g: nx.DiGraph = nx.DiGraph()
    for rel_type in _GRAPH_RELATION_TYPES:
        for fact in store.query_facts(type=rel_type):
            if fact.object is not None:
                g.add_edge(fact.subject.id, fact.object.id, relation=rel_type)
    return g


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


def compute_centrality(store: FactStore, repository_id: str, run_id: str) -> list[Fact]:
    """Emit one centrality fact per node (file/symbol) in the graph."""
    g = _build_graph(store)
    if not g.nodes:
        return []
    in_deg = nx.in_degree_centrality(g)
    out_deg = nx.out_degree_centrality(g)
    facts = []
    for node in g.nodes:
        evidence = (_file_evidence(repository_id, node),)
        facts.append(
            _make_fact(
                fact_type="centrality",
                subject=EntityRef(EntityType.FILE, node),
                value={"in_degree": in_deg[node], "out_degree": out_deg[node]},
                evidence=evidence,
                run_id=run_id,
            )
        )
    return facts


def detect_communities(store: FactStore, repository_id: str, run_id: str) -> list[Fact]:
    """Emit one community fact per node using Louvain over undirected projection.

    Community IDs are stable integers: communities sorted by their sorted member
    list, then indexed 0-based.
    """
    g = _build_graph(store)
    if not g.nodes:
        return []
    undirected = g.to_undirected()
    # ponytail: seed=42 for determinism; Louvain is still heuristic — result may
    # differ across networkx versions if the algorithm changes.
    communities = nx.algorithms.community.louvain_communities(undirected, seed=42)
    # Stable ordering: sort each community, then sort the list of communities
    sorted_communities = sorted(sorted(c) for c in communities)
    node_to_community = {
        node: idx for idx, members in enumerate(sorted_communities) for node in members
    }
    facts = []
    for node, community_id in node_to_community.items():
        evidence = (_file_evidence(repository_id, node),)
        facts.append(
            _make_fact(
                fact_type="community",
                subject=EntityRef(EntityType.FILE, node),
                value={"community_id": community_id},
                evidence=evidence,
                run_id=run_id,
            )
        )
    return facts


def detect_cycles(store: FactStore, repository_id: str, run_id: str) -> list[Fact]:
    """Emit one dependency_cycle fact per node that belongs to a cycle (SCC size > 1)."""
    g = _build_graph(store)
    if not g.nodes:
        return []
    facts = []
    for scc in nx.strongly_connected_components(g):
        if len(scc) <= 1:
            continue
        members = sorted(scc)
        evidence = tuple(_file_evidence(repository_id, m) for m in members)
        for node in members:
            facts.append(
                _make_fact(
                    fact_type="dependency_cycle",
                    subject=EntityRef(EntityType.FILE, node),
                    value={"cycle_members": members},
                    evidence=evidence,
                    run_id=run_id,
                )
            )
    return facts
