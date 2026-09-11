"""GraphProvider Protocol — Part A only. Concrete implementations gated on Feature 02b."""

from __future__ import annotations

from typing import Protocol

from project_intel.facts.model import Fact
from project_intel.facts.store import FactStore


class GraphProvider(Protocol):
    def extract(self, repository_id: str, scope: object, store: FactStore) -> list[Fact]:
        """Extract graph facts (imports, calls, etc.) and insert into store."""
        ...
