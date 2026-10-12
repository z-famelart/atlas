"""Tests for Feature 11c — report fidelity fixes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.html_report import generate_report

_RUN = "test-run-11c"


def _now() -> datetime:
    return datetime.now(UTC)


def _make_fact(
    fact_type: str,
    subject_id: str,
    value: dict,
    *,
    object_id: str | None = None,
    provenance: str = "observed",
    confidence: float = 0.9,
    run_id: str = _RUN,
    created_at: datetime | None = None,
) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(type=EntityType.FILE, id=subject_id),
        object=EntityRef(type=EntityType.FILE, id=object_id) if object_id else None,
        evidence=(
            Evidence(
                kind="file",
                ref=FileRef(repository_id="test-repo", path=subject_id),
                source_analyzer="test",
                retrieved_at=_now(),
            ),
        ),
        provenance=provenance,
        confidence=confidence,
        source_analyzer="test",
        created_at=created_at or _now(),
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        value=value,
    )


def _block(html: str, section_id: str) -> str:
    start = html.index(f'id="{section_id}"')
    end = html.index("</section>", start)
    return html[start:end]


# ---------------------------------------------------------------------------
# A. Field-mapping fixes
# ---------------------------------------------------------------------------


def test_executive_summary_reads_name_not_technology(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("technology_detected", "/repo/pyproject.toml", {"category": "build_system", "name": "make"}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "executive-summary")
    assert "make" in block
    assert "/repo/pyproject.toml" not in block.split("Technology:")[1][:5]  # no path leaking as name


def test_hotspots_reads_combined_not_score(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("hotspot_score", "src/a.py", {"combined": 0.82, "components": {}}),
        _make_fact("hotspot_score", "src/b.py", {"combined": 0.10, "components": {}}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "hotspots")
    assert "0.82" in block
    assert "score: 0.00" not in block
    # top hotspot must be the highest combined score, not the first inserted
    assert "Top hotspot: src/a.py" in block


def test_system_map_sorts_by_in_out_degree_not_score(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("centrality", "src/low.py", {"in_degree": 0.01, "out_degree": 0.01}),
        _make_fact("centrality", "src/high.py", {"in_degree": 0.5, "out_degree": 0.4}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "system-map")
    assert "Top file: src/high.py" in block


# ---------------------------------------------------------------------------
# B. Diagram edges + stable node IDs
# ---------------------------------------------------------------------------


def test_diagram_has_real_edge_between_top_nodes(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("centrality", "src/a.py", {"in_degree": 0.9, "out_degree": 0.1}),
        _make_fact("centrality", "src/b.py", {"in_degree": 0.5, "out_degree": 0.1}),
        _make_fact("imports", "src/a.py", {}, object_id="src/b.py"),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "system-map")
    assert "-->" in block


def test_same_basename_different_path_get_distinct_node_ids(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("centrality", "pkg1/archive.py", {"in_degree": 0.9, "out_degree": 0.1}),
        _make_fact("centrality", "pkg2/archive.py", {"in_degree": 0.5, "out_degree": 0.1}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "system-map")
    mermaid = block[block.index('class="mermaid"'):]
    node_lines = [line for line in mermaid.splitlines() if "[archive.py]" in line]
    assert len(node_lines) == 2
    ids = [line.strip().split("[")[0] for line in node_lines]
    assert ids[0] != ids[1]


# ---------------------------------------------------------------------------
# C. Structured data
# ---------------------------------------------------------------------------


def test_dependency_cycle_renders_all_members(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("dependency_cycle", "src/a.py", {"cycle_members": ["a.py", "b.py", "c.py"]}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "risks-anomalies")
    assert "a.py" in block and "b.py" in block and "c.py" in block


def test_git_coupling_shows_co_changes(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("git_coupling", "src/a.py", {"co_changes": 7, "coupling_pct": 50.0, "is_test_pair": False, "cross_boundary": False}, object_id="src/b.py"),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "git-evolution")
    assert "7" in block


def test_symbol_defined_uses_structured_fields(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "symbol_defined",
            "sym:1",
            {"name": "PluginDownloader", "kind": "class", "file": "core/plugin/downloader.py"},
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")
    assert "PluginDownloader" in block
    assert "class" in block
    assert "core/plugin/downloader.py" in block


# ---------------------------------------------------------------------------
# D. Onboarding narrative punctuation
# ---------------------------------------------------------------------------


def test_onboarding_narrative_has_sentence_separation(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "onboarding_path",
            "onboarding:1",
            {
                "recommended_workflow": {"description": "Start with the core module"},
                "time_boxed_understanding": {
                    "thirty_minutes": "read the README",
                    "two_hours": "trace the main request path",
                },
            },
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "onboarding-path")
    # No run-on: each assembled part must be followed by a period before the next starts
    assert "module. First 30 minutes" in block
    assert "README. First 2 hours" in block


# ---------------------------------------------------------------------------
# E. Cross-run fallback
# ---------------------------------------------------------------------------


def test_architecture_falls_back_to_older_run(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    old_run = "f34001286789"
    old_ts = _now() - timedelta(hours=2)
    s.insert_facts([
        _make_fact(
            "architecture_hypothesis",
            "arch:1",
            {"pattern": "layered"},
            run_id=old_run,
            created_at=old_ts,
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "architecture")
    assert "Showing results from a previous analysis" in block
    assert old_run[:8] in block
    assert "layered" in block


# ---------------------------------------------------------------------------
# F. Distinct not-analyzed states
# ---------------------------------------------------------------------------


def test_no_stage_run_result_shows_generic_message(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "architecture")
    assert "Not analyzed" in block


def test_llm_disabled_shows_specific_message(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "stage_run_result",
            "repo:1",
            {
                "stage": "architecture",
                "status": "skipped",
                "facts_produced": 0,
                "detail": "not_analyzed: llm_disabled",
            },
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "architecture")
    assert "LLM analysis was disabled for this run." in block


def test_llm_failed_shows_failure_detail(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "stage_run_result",
            "repo:1",
            {
                "stage": "architecture",
                "status": "skipped",
                "facts_produced": 0,
                "detail": "not_analyzed: llm_failed",
            },
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "architecture")
    assert "not_analyzed: llm_failed" in block
    assert "Atlas attempted this analysis but it failed" in block


def test_ok_with_zero_facts_shows_found_nothing_message(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "stage_run_result",
            "repo:1",
            {"stage": "architecture", "status": "ok", "facts_produced": 0, "detail": None},
        ),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "architecture")
    assert "found nothing to report" in block
