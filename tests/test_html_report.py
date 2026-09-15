"""Tests for Feature 11 — HTML report generator."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.html_report import generate_report

_RUN = "test-run-html"


def _now() -> datetime:
    return datetime.now(UTC)


def _make_fact(fact_type: str, subject_id: str, value: dict, provenance: str = "observed") -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(type=EntityType.FILE, id=subject_id),
        evidence=(
            Evidence(
                kind="file",
                ref=FileRef(repository_id="test-repo", path=subject_id),
                source_analyzer="test",
                retrieved_at=_now(),
            ),
        ),
        provenance=provenance,
        confidence=0.9,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
        value=value,
    )


@pytest.fixture
def store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.db")


@pytest.fixture
def store_with_discovery_and_hotspots(tmp_path: Path) -> FactStore:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("language_detected", "src/main.py", {"language": "Python"}),
        _make_fact("technology_detected", "pyproject.toml", {"category": "framework", "name": "fastapi"}),
        _make_fact("hotspot_score", "src/main.py", {"combined": 0.87}),
        _make_fact("hotspot_score", "src/utils.py", {"combined": 0.42}),
    ])
    return s


def test_generate_report_returns_path(store: FactStore, tmp_path: Path) -> None:
    path = generate_report(store, _RUN, output_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".html"
    assert _RUN in path.name


def test_all_17_sections_present(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    section_ids = [
        "executive-summary", "system-map", "architecture", "code-map",
        "hotspots", "domain-understanding", "runtime", "infrastructure",
        "ci-cd", "data-architecture", "observability", "tests",
        "git-evolution", "risks-anomalies", "onboarding-path", "glossary", "evidence",
    ]
    for sid in section_ids:
        assert f'id="{sid}"' in html, f"section {sid!r} missing from report"


def test_empty_store_shows_not_analyzed(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    assert "Not analyzed" in html


def test_architecture_not_analyzed_without_arch_facts(store_with_discovery_and_hotspots: FactStore, tmp_path: Path) -> None:
    html = generate_report(store_with_discovery_and_hotspots, _RUN, output_dir=tmp_path).read_text()
    # architecture section should be "not analyzed"
    arch_start = html.index('id="architecture"')
    arch_end = html.index('</section>', arch_start)
    arch_block = html[arch_start:arch_end]
    assert "Not analyzed" in arch_block


def test_hotspots_render_when_facts_present(store_with_discovery_and_hotspots: FactStore, tmp_path: Path) -> None:
    html = generate_report(store_with_discovery_and_hotspots, _RUN, output_dir=tmp_path).read_text()
    assert "src/main.py" in html
    assert "0.87" in html


def test_shared_provenance_badge_used_across_sections(store_with_discovery_and_hotspots: FactStore, tmp_path: Path) -> None:
    html = generate_report(store_with_discovery_and_hotspots, _RUN, output_dir=tmp_path).read_text()
    # prov-badge is the shared CSS class — must appear in at least 2 fact-rows
    assert html.count('class="prov-badge"') >= 2


def test_every_fact_row_has_data_evidence(store_with_discovery_and_hotspots: FactStore, tmp_path: Path) -> None:
    html = generate_report(store_with_discovery_and_hotspots, _RUN, output_dir=tmp_path).read_text()
    rows = html.split('class="fact-row"')
    # first element is before any row; all subsequent must have data-evidence
    for chunk in rows[1:]:
        assert "data-evidence=" in chunk, "fact-row missing data-evidence attribute"


def test_no_external_urls(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    assert "<script src=\"http" not in html
    assert "<script src='http" not in html
    assert "<link href=\"http" not in html
    assert "<link href='http" not in html


def test_embeds_run_id_and_timestamp(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    assert f'content="{_RUN}"' in html
    assert 'atlas-generated-at' in html


def test_output_dir_defaults_to_cwd(store: FactStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = generate_report(store, _RUN)
    assert path.parent == tmp_path


def test_search_input_present(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    assert 'id="search-input"' in html


def test_evidence_panel_present(store: FactStore, tmp_path: Path) -> None:
    html = generate_report(store, _RUN, output_dir=tmp_path).read_text()
    assert 'id="evidence-panel"' in html
