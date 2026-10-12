from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from project_intel.adapters import AdapterContext
from project_intel.facts.store import FactStore
from project_intel.facts.value_schemas import (
    file_age_value,
    file_role_value,
    git_coupling_value,
    git_ownership_value,
)
from project_intel.git_analysis.barad_dur import normalize_barad_dur
from project_intel.mcp_server import queries

_RAW = json.dumps({
    "author_ownership": [
        {"path": "a.py", "authors": [{"name": "Ann", "pct": 70.0}, {"name": "Bob", "pct": 30.0}]},
        {"path": "b.py", "authors": [{"name": "Bob", "pct": 100.0}]},
    ],
    "file_ages": [{"path": "a.py", "days_since_modified": 4, "last_modified": "2026-01-01T00:00:00Z"}],
    "file_hotspots": [{"path": "a.py", "role": "source"}],
    "coupling_pairs": [
        {"file_a": "a.py", "file_b": "b.py", "co_changes": 3, "coupling_pct": 50.0,
         "is_test_pair": False, "cross_boundary": True},
    ],
})


def _facts(tmp_path: Path):
    ctx = AdapterContext(target_path=tmp_path, run_id="r", repository_id="repo", timestamp=datetime.now(UTC))
    return normalize_barad_dur(_RAW, ctx)


def test_normalize_matches_typed_schemas(tmp_path: Path) -> None:
    by_type = {f.type: f for f in reversed(_facts(tmp_path))}
    assert git_ownership_value(by_type["git_ownership"]).top_author == "Ann"
    assert file_age_value(by_type["file_age"]).days_since_modified == 4
    assert file_role_value(by_type["file_role"]).role == "source"
    coupling = by_type["git_coupling"]
    assert git_coupling_value(coupling).coupling_pct == 50.0
    assert coupling.object is not None and coupling.object.id == "b.py"


def test_get_owners_ranks_by_mean_share(tmp_path: Path) -> None:
    store = FactStore(":memory:")
    store.insert_facts(_facts(tmp_path))
    assert queries.get_owners(store) == [
        {"author": "Bob", "mean_pct": 65.0, "files": 2},
        {"author": "Ann", "mean_pct": 35.0, "files": 2},
    ]
