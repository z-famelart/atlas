"""Tests for surfacing code_graph_coverage gaps in the Code Map section."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef, ToolOutputRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.html_report import generate_report

_RUN = "test-run-coverage"
_REPO = "test-repo"


def _now() -> datetime:
    return datetime.now(UTC)


def _symbol_fact(path: str) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="symbol_defined",
        subject=EntityRef(EntityType.SYMBOL, f"{path}::fn"),
        value={"name": "fn", "kind": "function", "file": path},
        evidence=(
            Evidence(
                kind="file",
                ref=FileRef(repository_id=_REPO, path=path),
                source_analyzer="test",
                retrieved_at=_now(),
            ),
        ),
        provenance="observed",
        confidence=1.0,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def _coverage_fact(out_of_scope: dict) -> Fact:
    return Fact(
        id=str(uuid.uuid4()),
        type="code_graph_coverage",
        subject=EntityRef(EntityType.REPOSITORY, _REPO),
        value={
            "in_scope_loc": 300,
            "out_of_scope_loc": sum(out_of_scope.values()),
            "out_of_scope_languages": out_of_scope,
            "coverage_ratio": 300 / (300 + sum(out_of_scope.values())) if out_of_scope else 1.0,
        },
        evidence=(
            Evidence(
                kind="tool_output",
                ref=ToolOutputRef(source_analyzer="test", raw_ref="test"),
                source_analyzer="test",
                retrieved_at=_now(),
            ),
        ),
        provenance="computed",
        confidence=1.0,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=_RUN,
    )


def _block(html: str, section_id: str) -> str:
    start = html.index(f'id="{section_id}"')
    end = html.index("</section>", start)
    return html[start:end]


def test_out_of_scope_language_surfaced_in_code_map(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _symbol_fact("src/a.py"),
        _coverage_fact({"PHP": 4200}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")
    assert "PHP" in block
    assert "4,200 LOC" in block


def test_full_coverage_produces_no_gap_note(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _symbol_fact("src/a.py"),
        _coverage_fact({}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")
    assert "not covered by the code graph" not in block.lower()
