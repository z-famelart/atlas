"""Tests for Feature 13b — multi-repository System orchestration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from project_intel.cli.main import _write_system_facts
from project_intel.facts.enums import EntityType, RelationType
from project_intel.facts.model import EntityRef
from project_intel.facts.store import FactStore


def _repo_entry(tmp_path: Path, name: str, system: str | None = None) -> dict:
    repo = tmp_path / name
    repo.mkdir()
    entry = {"path": str(repo), "name": name}
    if system is not None:
        entry["system"] = system
    return entry


def _system_store_path(project_root: Path, system_name: str) -> Path:
    return project_root / ".atlas-cache" / f"system-{system_name}.sqlite"


# ---------------------------------------------------------------------------
# _write_system_facts — direct unit tests
# ---------------------------------------------------------------------------


def test_writes_system_store_for_two_plus_members(tmp_path: Path) -> None:
    config_path = tmp_path / ".atlas.toml"
    config_path.write_text("")
    repos_cfg = [
        _repo_entry(tmp_path, "frontend", system="myapp"),
        _repo_entry(tmp_path, "backend", system="myapp"),
    ]

    _write_system_facts(tmp_path, repos_cfg, config_path)

    db = _system_store_path(tmp_path, "myapp")
    assert db.exists()
    store = FactStore(db)
    facts = list(store.query_facts(type=RelationType.BELONGS_TO.value))
    store.close()

    assert len(facts) == 2
    for f in facts:
        assert f.provenance == "observed"
        assert f.confidence == 1.0
        assert f.object == EntityRef(EntityType.SYSTEM, "myapp")
        assert len(f.evidence) == 1
        assert f.evidence[0].kind == "config"


def test_skips_system_with_single_member(tmp_path: Path) -> None:
    config_path = tmp_path / ".atlas.toml"
    config_path.write_text("")
    repos_cfg = [_repo_entry(tmp_path, "solo", system="myapp")]

    _write_system_facts(tmp_path, repos_cfg, config_path)

    assert not _system_store_path(tmp_path, "myapp").exists()


def test_ignores_entries_without_system(tmp_path: Path) -> None:
    config_path = tmp_path / ".atlas.toml"
    config_path.write_text("")
    repos_cfg = [_repo_entry(tmp_path, "a"), _repo_entry(tmp_path, "b")]

    _write_system_facts(tmp_path, repos_cfg, config_path)

    assert not (tmp_path / ".atlas-cache").exists()


def test_excludes_repo_with_no_system_declared(tmp_path: Path) -> None:
    """Two repos share a system, a third declares none — only the two are members."""
    config_path = tmp_path / ".atlas.toml"
    config_path.write_text("")
    repos_cfg = [
        _repo_entry(tmp_path, "frontend", system="myapp"),
        _repo_entry(tmp_path, "backend", system="myapp"),
        _repo_entry(tmp_path, "unrelated"),
    ]

    _write_system_facts(tmp_path, repos_cfg, config_path)

    store = FactStore(_system_store_path(tmp_path, "myapp"))
    facts = list(store.query_facts(type=RelationType.BELONGS_TO.value))
    store.close()

    repo_ids = {f.subject.id for f in facts}
    assert len(repo_ids) == 2
    assert not any("unrelated" in rid for rid in repo_ids)


# ---------------------------------------------------------------------------
# End-to-end CLI wiring
# ---------------------------------------------------------------------------


def test_cli_analyze_multi_repo_writes_system_store(tmp_path: Path) -> None:
    """A --config run with 2 repositories sharing `system` produces the system
    store, and each repository still gets its own, unchanged facts.sqlite."""
    for name in ("svc-a", "svc-b"):
        repo = tmp_path / name
        repo.mkdir()
        (repo / "main.py").write_text("def hello():\n    return 1\n")

    config_path = tmp_path / "project.toml"
    config_path.write_text(f"""
[[repositories]]
path = "{tmp_path / "svc-a"}"
name = "svc-a"
system = "myapp"

[[repositories]]
path = "{tmp_path / "svc-b"}"
name = "svc-b"
system = "myapp"
""")

    result = subprocess.run(
        [sys.executable, "-m", "project_intel.cli.main", "analyze", "--no-llm", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert (tmp_path / "svc-a" / ".atlas-cache" / "facts.sqlite").exists()
    assert (tmp_path / "svc-b" / ".atlas-cache" / "facts.sqlite").exists()
    assert _system_store_path(tmp_path, "myapp").exists()
    assert "System 'myapp': 2 repositories" in result.stdout
