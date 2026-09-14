"""Hotspot scoring engine — Feature 06 Part A.

Reads complexity/size/centrality/churn facts from FactStore and emits:
  - hotspot_<component>_score facts (independently queryable sub-scores)
  - hotspot_score facts (decomposed combined score)

Missing components are excluded from the combination and flagged explicitly —
never treated as zero (Décidé Q74).
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from ..facts.enums import EntityType
from ..facts.model import EntityRef, Evidence, Fact
from ..facts.refs import FileRef
from ..facts.store import SCHEMA_VERSION, FactStore
from .weights import HotspotWeights

_ANALYZER = "hotspot_scorer@1.0"

_COMPONENT_NAMES = ("complexity", "size", "centrality", "churn")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _percentile_rank(values: list[float]) -> list[float]:
    """Return percentile rank in [0, 1] for each value (ties share mean rank)."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    # Sort indices by value
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        mean_rank = (i + j - 1) / 2 / (n - 1)
        for k in range(i, j):
            ranks[order[k]] = mean_rank
        i = j
    return ranks


# ---------------------------------------------------------------------------
# Component extraction
# ---------------------------------------------------------------------------


def _collect_complexity(store: FactStore) -> dict[str, float]:
    return {f.subject.id: float(f.value["score"]) for f in store.query_facts(type="complexity") if f.value}


def _collect_size(store: FactStore) -> dict[str, float]:
    # log1p-normalize before storing raw (Décidé Q68)
    return {
        f.subject.id: math.log1p(float(f.value.get("loc", 0)))
        for f in store.query_facts(type="language_detected")
        if f.value
    }


def _collect_centrality(store: FactStore) -> dict[str, float]:
    return {
        f.subject.id: float(f.value.get("in_degree", 0))
        for f in store.query_facts(type="centrality")
        if f.value
    }


def _collect_churn(store: FactStore) -> dict[str, float]:
    return {
        f.subject.id: float(f.value.get("commits", 0))
        for f in store.query_facts(type="git_churn")
        if f.value
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_hotspots(
    store: FactStore,
    repository_id: str,
    run_id: str,
    weights: HotspotWeights | None = None,
) -> list[Fact]:
    """Compute hotspot scores for all files that have at least one component fact."""
    weights = weights or HotspotWeights()
    now = datetime.now(UTC)

    raw: dict[str, dict[str, float]] = {
        "complexity": _collect_complexity(store),
        "size": _collect_size(store),
        "centrality": _collect_centrality(store),
        "churn": _collect_churn(store),
    }

    # Union of all files that appear in any component
    all_files = sorted({path for component in raw.values() for path in component})
    if not all_files:
        return []

    # Percentile-rank each component over its own distribution
    normalized: dict[str, dict[str, float]] = {}
    for name, values_by_file in raw.items():
        files_with_data = sorted(values_by_file)
        vals = [values_by_file[f] for f in files_with_data]
        ranks = _percentile_rank(vals)
        normalized[name] = dict(zip(files_with_data, ranks))

    weight_map = {
        "complexity": weights.complexity,
        "size": weights.size,
        "centrality": weights.centrality,
        "churn": weights.churn,
    }

    facts: list[Fact] = []

    for file_path in all_files:
        file_ref = FileRef(repository_id=repository_id, path=file_path)
        subject = EntityRef(EntityType.FILE, file_path)
        ev = (Evidence(kind="file", ref=file_ref, source_analyzer=_ANALYZER, retrieved_at=now),)

        components: dict[str, dict] = {}
        source_fact_ids: list[str] = []

        for name in _COMPONENT_NAMES:
            norm_val = normalized[name].get(file_path)
            raw_val = raw[name].get(file_path)
            if norm_val is None:
                components[name] = {"raw": None, "normalized": None, "weight": weight_map[name], "present": False}
            else:
                components[name] = {
                    "raw": raw_val,
                    "normalized": norm_val,
                    "weight": weight_map[name],
                    "present": True,
                }
                # Emit independent sub-score fact
                sub_fact = Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:hotspot_{name}:{file_path}")),
                    type=f"hotspot_{name}_score",
                    subject=subject,
                    value={"raw": raw_val, "normalized": norm_val, "weight": weight_map[name]},
                    provenance="computed",
                    confidence=1.0,
                    source_analyzer=_ANALYZER,
                    created_at=now,
                    schema_version=SCHEMA_VERSION,
                    run_id=run_id,
                    evidence=ev,
                )
                facts.append(sub_fact)
                source_fact_ids.append(sub_fact.id)

        present = [n for n in _COMPONENT_NAMES if components[n]["present"]]
        components_available = len(present)
        if components_available == 0:
            continue

        total_weight = sum(weight_map[n] for n in present)
        if total_weight == 0:
            combined = 0.0
        else:
            combined = sum(components[n]["normalized"] * weight_map[n] for n in present) / total_weight

        facts.append(
            Fact(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:hotspot_score:{file_path}")),
                type="hotspot_score",
                subject=subject,
                value={
                    "combined": combined,
                    "components_available": f"{components_available}/{len(_COMPONENT_NAMES)}",
                    "components": {
                        n: {
                            "raw": components[n]["raw"],
                            "normalized": components[n]["normalized"],
                            "weight": components[n]["weight"],
                            "present": components[n]["present"],
                        }
                        for n in _COMPONENT_NAMES
                    },
                },
                provenance="computed",
                confidence=1.0,
                source_analyzer=_ANALYZER,
                created_at=now,
                schema_version=SCHEMA_VERSION,
                run_id=run_id,
                evidence=ev,
            )
        )

    return facts
