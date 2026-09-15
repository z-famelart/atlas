"""Collect observed graph facts and build the LLM prompt — Feature 08."""

from __future__ import annotations

import json

from ..facts.model import Fact
from ..facts.store import FactStore
from ..llm.types import StructuredPrompt
from .schema import CATALOGUE_DESCRIPTION

_GRAPH_FACT_TYPES = ("centrality", "community", "dependency_cycle", "calls", "imports", "inherits_from")

_INSTRUCTIONS = f"""\
You are analyzing the observed code graph of a software repository.
Based on the provided facts (centrality, community clusters, dependency structure),
identify the architectural pattern(s) that best describe this codebase.

{CATALOGUE_DESCRIPTION}

"microservices" means multiple independently deployed processes/services (separate deployables,
separate runtimes) communicating over a network — it does not mean a single codebase that happens
to have a directory or package named services/, service_layer/, or similar. A Django app (or any
single-process application) with an internal services/ module organizing business logic is not
microservices merely because of that name. Only use "microservices" if there's actual evidence of
multiple independently deployed/runnable units (e.g. multiple Dockerfiles, separate deployment
manifests, separate process entry points) — not just a naming convention.

Rules:
- Return 1-3 hypotheses ordered by descending confidence.
- confidence must be a float in [0.0, 1.0].
- fact_ids must only contain ids from the provided facts — do not invent ids.
- If the graph is too sparse to conclude, return one hypothesis with low confidence.
"""


def collect_graph_facts(store: FactStore) -> list[Fact]:
    """Return the graph facts relevant to architecture interpretation."""
    facts: list[Fact] = []
    for fact_type in _GRAPH_FACT_TYPES:
        facts.extend(store.query_facts(type=fact_type))
    return facts


def _fact_summary(fact: Fact) -> dict:
    return {
        "id": fact.id,
        "type": fact.type,
        "subject": fact.subject.id,
        "value": fact.value,
    }


def build_prompt(facts: list[Fact]) -> StructuredPrompt:
    content = json.dumps([_fact_summary(f) for f in facts], default=str)
    return StructuredPrompt(
        instructions=_INSTRUCTIONS,
        content=content,
        schema_version="architecture@1.0",
        category="architecture",
        estimated_input_tokens=len(content) // 4,  # rough token estimate
    )
