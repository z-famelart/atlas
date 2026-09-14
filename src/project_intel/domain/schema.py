"""Response schema for domain understanding — Feature 09."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class BusinessConcept:
    name: str
    description: str
    fact_ids: list[str]


@dataclasses.dataclass
class BusinessWorkflow:
    name: str
    description: str
    fact_ids: list[str]


@dataclasses.dataclass
class GlossaryTerm:
    term: str
    definition: str
    fact_ids: list[str]


@dataclasses.dataclass
class DomainResponse:
    concepts: list[BusinessConcept]
    workflows: list[BusinessWorkflow]
    glossary: list[GlossaryTerm]
