"""Citation validator — Feature 07.

Every interpretive schema carries fact_ids fields; after schema validation this
module checks that every cited id is a real Fact already in the FactStore.
A response citing an unknown id is rejected (Décidé Q81).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..facts.store import FactStore


def _collect_fact_ids(obj: Any) -> list[str]:
    """Recursively collect all fact_ids values from a dataclass (or list/dict)."""
    ids: list[str] = []
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for field in dataclasses.fields(obj):
            child = getattr(obj, field.name)
            if field.name == "fact_ids" and isinstance(child, list):
                ids.extend(str(x) for x in child)
            else:
                ids.extend(_collect_fact_ids(child))
    elif isinstance(obj, list):
        for item in obj:
            ids.extend(_collect_fact_ids(item))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "fact_ids" and isinstance(v, list):
                ids.extend(str(x) for x in v)
            else:
                ids.extend(_collect_fact_ids(v))
    return ids


def validate_citations(response: Any, store: FactStore) -> tuple[bool, list[str]]:
    """Return (valid, unknown_ids).

    valid is True when every cited fact_id exists in store.
    unknown_ids lists the ids that could not be found.
    """
    cited = _collect_fact_ids(response)
    if not cited:
        return True, []
    unknown = [fid for fid in cited if not store.fact_exists(fid)]
    return len(unknown) == 0, unknown


def resolve_aliases(obj: Any, id_map: dict[str, str]) -> None:
    """Map aliased ids in every fact_ids list back to real ids, in place (unknown ids untouched)."""
    if not id_map:
        return
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for field in dataclasses.fields(obj):
            child = getattr(obj, field.name)
            if field.name == "fact_ids" and isinstance(child, list):
                child[:] = [id_map.get(str(x), str(x)) for x in child]
            else:
                resolve_aliases(child, id_map)
    elif isinstance(obj, list):
        for item in obj:
            resolve_aliases(item, id_map)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "fact_ids" and isinstance(v, list):
                v[:] = [id_map.get(str(x), str(x)) for x in v]
            else:
                resolve_aliases(v, id_map)
