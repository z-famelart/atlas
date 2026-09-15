"""Tests for Feature 11d — Code Map community graph (size, links, importance)."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.html_report import generate_report

_RUN = "test-run-11d"


def _now() -> datetime:
    return datetime.now(UTC)


def _make_fact(
    fact_type: str,
    subject_id: str,
    value: dict,
    *,
    object_id: str | None = None,
    run_id: str = _RUN,
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
        provenance="computed",
        confidence=0.9,
        source_analyzer="test",
        created_at=_now(),
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        value=value,
    )


def _block(html: str, section_id: str) -> str:
    start = html.index(f'id="{section_id}"')
    end = html.index("</section>", start)
    return html[start:end]


def _community_facts(cid: int, n_files: int) -> list[Fact]:
    return [
        _make_fact("community", f"src/c{cid}/f{i}.py", {"community_id": cid}) for i in range(n_files)
    ]


def test_top_20_selected_and_omitted_count_in_prose(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    facts: list[Fact] = []
    for cid in range(25):
        facts.extend(_community_facts(cid, n_files=cid + 1))  # distinct sizes 1..25
    s.insert_facts(facts)
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")

    bubbles = re.findall(r'class="community-bubble"', block)
    assert len(bubbles) == 20
    assert "5 smaller communities not pictured" in block
    assert "25 community clusters detected" in block


def test_bubble_radius_proportional_to_sqrt_size(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([*_community_facts(1, 4), *_community_facts(2, 16)])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")

    # Bubbles are laid out in community_id order, so circle order matches label order.
    circles = re.findall(r'<circle[^>]*r="([\d.]+)"', block)
    labels = re.findall(r"C(\d) — (\d+) files", block)
    radii = {int(cid): float(r) for (cid, _size), r in zip(labels, circles, strict=True)}

    ratio = radii[2] / radii[1]
    assert math.isclose(ratio, math.sqrt(16 / 4), rel_tol=1e-6)
    assert not math.isclose(ratio, 16 / 4, rel_tol=1e-6)


def test_different_importance_produces_different_colors(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        *_community_facts(1, 2),
        *_community_facts(2, 2),
        _make_fact("centrality", "src/c1/f0.py", {"in_degree": 1, "out_degree": 1}),  # importance 2
        _make_fact("centrality", "src/c1/f1.py", {"in_degree": 0, "out_degree": 0}),
        _make_fact("centrality", "src/c2/f0.py", {"in_degree": 5, "out_degree": 5}),  # importance 10
        _make_fact("centrality", "src/c2/f1.py", {"in_degree": 0, "out_degree": 0}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")

    fills = re.findall(r'<circle[^>]*fill="(#[0-9a-f]{6})"', block)
    assert len(set(fills)) == 2
    # min importance (community 1, t=0) must render as the light end of the scale,
    # max importance (community 2, t=1) as the dark end.
    assert fills[0] == "#e3f2fd"
    assert fills[1] == "#0d47a1"


def test_cross_community_edge_drawn_only_for_selected_communities(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    facts: list[Fact] = []
    for cid in range(21):  # 21 communities -> community 20 (smallest) is unselected
        facts.extend(_community_facts(cid, n_files=25 - cid))
    facts.append(_make_fact("imports", "src/c0/f0.py", {}, object_id="src/c1/f0.py"))
    facts.append(_make_fact("imports", "src/c1/f0.py", {}, object_id="src/c20/f0.py"))
    s.insert_facts(facts)
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")

    lines = re.findall(r'<line[^>]*/>', block)
    assert len(lines) == 1  # only the c0<->c1 edge; c1<->c20 is dropped (c20 unselected)


def test_bubble_evidence_contains_community_and_centrality_facts(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        *_community_facts(1, 2),
        _make_fact("centrality", "src/c1/f0.py", {"in_degree": 1, "out_degree": 1}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")

    m = re.search(r"data-evidence='(\[.*?\])' onclick=\"showEvidence\(this\)\"", block)
    assert m is not None
    evidence = json.loads(m.group(1))
    paths = {e["path"] for e in evidence}
    assert "src/c1/f0.py" in paths
    assert "src/c1/f1.py" in paths


def test_no_community_facts_falls_back_to_gap_message(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([
        _make_fact("symbol_defined", "sym:1", {"name": "Foo", "kind": "class", "file": "a.py"}),
    ])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")
    assert "community-graph" not in block
    assert "Foo" in block


def test_gap_message_when_truly_empty(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    block = _block(html, "code-map")
    assert "Not analyzed" in block


def test_no_external_script_or_link_references(tmp_path: Path) -> None:
    s = FactStore(tmp_path / "facts.db")
    s.insert_facts([*_community_facts(1, 3), *_community_facts(2, 4)])
    html = generate_report(s, _RUN, output_dir=tmp_path).read_text()
    assert '<script src="http' not in html
    assert "<script src='http" not in html
    assert '<link href="http' not in html
    assert "<link href='http" not in html
