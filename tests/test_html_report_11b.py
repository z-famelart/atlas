"""Tests for Feature 11b — Mermaid inline + narrative prose."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.html_report import generate_report

_RUN = "test-run-11b"


def _now() -> datetime:
    return datetime.now(UTC)


def _make_fact(
    fact_type: str,
    subject_id: str,
    value: dict,
    provenance: str = "observed",
    confidence: float = 0.9,
) -> Fact:
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
        confidence=confidence,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
        value=value,
    )


# ---------------------------------------------------------------------------
# Mermaid vendoring
# ---------------------------------------------------------------------------


def test_no_mermaid_hint_in_output(tmp_path: Path) -> None:
    """Acceptance criterion 1: no .mermaid-hint text in generated HTML."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("centrality", "src/core.py", {"score": 0.9}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    assert "mermaid-hint" not in html
    assert "Load mermaid.js locally" not in html


def test_no_external_mermaid_script(tmp_path: Path) -> None:
    """Acceptance criterion 2: no <script src="http..."> for Mermaid."""
    s = FactStore(tmp_path / "facts.db")
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    assert '<script src="http' not in html
    assert "<script src='http" not in html


def test_mermaid_script_inlined(tmp_path: Path) -> None:
    """Mermaid JS is embedded inline in the HTML."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("centrality", "src/core.py", {"score": 0.9}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    # mermaid.initialize call proves the init script is present
    assert "mermaid.initialize" in html
    # The pre.mermaid block is still emitted
    assert 'class="mermaid"' in html


# ---------------------------------------------------------------------------
# Narrative prose
# ---------------------------------------------------------------------------


def test_discovery_section_has_narrative(tmp_path: Path) -> None:
    """Acceptance criterion 3a: Discovery/ExecutiveSummary has section-narrative."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("language_detected", "src/main.py", {"language": "Python"}),
        _make_fact("technology_detected", "pyproject.toml", {"technology": "fastapi"}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    # Narrative paragraph must appear before the fact-list in executive-summary
    exec_start = html.index('id="executive-summary"')
    exec_end = html.index("</section>", exec_start)
    block = html[exec_start:exec_end]
    assert 'class="section-narrative"' in block
    assert "Python" in block
    assert "fastapi" in block


def test_hotspots_section_has_narrative(tmp_path: Path) -> None:
    """Acceptance criterion 3b: Hotspots section has section-narrative."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("hotspot_score", "src/main.py", {"score": 0.87}),
        _make_fact("hotspot_score", "src/utils.py", {"score": 0.42}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    hs_start = html.index('id="hotspots"')
    hs_end = html.index("</section>", hs_start)
    block = html[hs_start:hs_end]
    assert 'class="section-narrative"' in block
    assert "src/main.py" in block
    assert "0.87" in block


def test_narrative_before_fact_list(tmp_path: Path) -> None:
    """Narrative <p> must appear before the <div class="fact-list">."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("hotspot_score", "src/core.py", {"score": 0.75}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    hs_start = html.index('id="hotspots"')
    hs_end = html.index("</section>", hs_start)
    block = html[hs_start:hs_end]
    narrative_pos = block.index('class="section-narrative"')
    fact_list_pos = block.index('class="fact-list"')
    assert narrative_pos < fact_list_pos


def test_empty_section_no_broken_narrative(tmp_path: Path) -> None:
    """Section with no facts uses existing not-analyzed state, no empty <p>."""
    s = FactStore(tmp_path / "facts.db")
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    hs_start = html.index('id="hotspots"')
    hs_end = html.index("</section>", hs_start)
    block = html[hs_start:hs_end]
    # No narrative in empty section
    assert 'class="section-narrative"' not in block
    assert "Not analyzed" in block


# ---------------------------------------------------------------------------
# Architecture interpretive section
# ---------------------------------------------------------------------------


def test_architecture_pattern_description_rendered(tmp_path: Path) -> None:
    """Acceptance criterion 4: pattern_description from architecture_hypothesis appears as prose."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "architecture_hypothesis",
            ".",
            {
                "pattern": "layered",
                "pattern_description": "The codebase follows a strict layered architecture with clear separation of concerns.",
            },
            provenance="hypothesis",
            confidence=0.85,
        )
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    arch_start = html.index('id="architecture"')
    arch_end = html.index("</section>", arch_start)
    block = html[arch_start:arch_end]
    assert "strict layered architecture" in block
    assert 'class="section-narrative"' in block


def test_architecture_fallback_when_no_description(tmp_path: Path) -> None:
    """When pattern_description absent, fallback to pattern + confidence sentence."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact(
            "architecture_hypothesis",
            ".",
            {"pattern": "microservices"},
            provenance="hypothesis",
            confidence=0.7,
        )
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    arch_start = html.index('id="architecture"')
    arch_end = html.index("</section>", arch_start)
    block = html[arch_start:arch_end]
    assert "microservices" in block
    assert 'class="section-narrative"' in block


# ---------------------------------------------------------------------------
# No LLM import / call
# ---------------------------------------------------------------------------


def test_renderer_has_no_llm_import() -> None:
    """Acceptance criterion 5: renderer.py must not import the llm module."""
    import inspect

    from project_intel.html_report import renderer
    src = inspect.getsource(renderer)
    assert "from project_intel.llm" not in src
    assert "import project_intel.llm" not in src


def test_none_provider_still_produces_narrative(tmp_path: Path) -> None:
    """Narrative is produced even when no LLM provider is available (no call needed)."""
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("language_detected", "main.py", {"language": "Go"}),
    ])
    # generate_report takes no llm_provider arg — this just proves it works without one
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    assert "Go" in html
    assert 'class="section-narrative"' in html


# ---------------------------------------------------------------------------
# Git evolution and risks narrative
# ---------------------------------------------------------------------------


def test_git_evolution_narrative(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("git_churn", "src/hot.py", {"commits": 42}),
        _make_fact("git_churn", "src/cold.py", {"commits": 3}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    ge_start = html.index('id="git-evolution"')
    ge_end = html.index("</section>", ge_start)
    block = html[ge_start:ge_end]
    assert 'class="section-narrative"' in block
    assert "src/hot.py" in block
    assert "42" in block


def test_risks_narrative(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("dependency_cycle", "src/a.py", {}),
        _make_fact("dependency_cycle", "src/b.py", {}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    risks_start = html.index('id="risks-anomalies"')
    risks_end = html.index("</section>", risks_start)
    block = html[risks_start:risks_end]
    assert 'class="section-narrative"' in block
    assert "cycle" in block
