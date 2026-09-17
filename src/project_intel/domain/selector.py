"""Deterministic file selector for domain understanding — Feature 09.

Produces a bounded list[CandidateContent] from hotspot scores and graph
entrypoints, leaving a seam for a secrets-scanning pass before LLM send.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ..facts.store import FactStore

_TEST_STEM_RE = re.compile(r"^test_(.+)$|^(.+)_test$")
_WORKFLOW_KEYWORDS = ("workflow", "process", "service", "domain", "handler", "controller")


@dataclasses.dataclass
class CandidateContent:
    path: str
    content: str
    source_fact_ids: list[str]


def _read(repository_path: Path, path: str) -> str:
    try:
        return (repository_path / path).read_text(errors="replace")
    except OSError:
        return ""


def _test_base(stem: str) -> str | None:
    """Return the source base name a test stem refers to, or None."""
    m = _TEST_STEM_RE.match(stem)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _is_test_path(path: str) -> bool:
    """Return True if the path is a test file by name/directory convention."""
    p = Path(path)
    return _test_base(p.stem) is not None or "tests" in p.parts


def select_candidates(
    store: FactStore,
    repository_path: Path,
    top_n: int = 20,
    run_id: str | None = None,
) -> list[CandidateContent]:
    """Return a bounded candidate set for domain synthesis."""
    run_id = store.run_id_with("hotspot_score", run_id)
    # ── 1. Hotspot files (top_n by combined score) ──────────────────────────
    hotspot_facts = store.query_facts(type="hotspot_score", run_id=run_id)
    scored: list[tuple[float, str, str]] = []  # (score, path, fact_id)
    for f in hotspot_facts:
        if f.value and "combined" in f.value:
            scored.append((float(f.value["combined"]), f.subject.id, f.id))
    scored.sort(key=lambda t: t[0], reverse=True)
    top_files = {path: fact_id for _, path, fact_id in scored[:top_n]}

    # ── 2. Entrypoints: centrality facts with in_degree == 0 (graph roots) ──
    if len(top_files) < top_n:
        entrypoint_facts = store.query_facts(type="centrality", run_id=run_id)
        for f in entrypoint_facts:
            if len(top_files) >= top_n:
                break
            if f.value and f.value.get("in_degree", 1) == 0 and f.subject.id not in top_files:
                top_files[f.subject.id] = f.id

    # ── 3. Test files: name-match to selected source files ──────────────────
    if len(top_files) < top_n:
        selected_stems = {Path(p).stem for p in top_files}
        test_facts = store.query_facts(type="hotspot_score", run_id=run_id)  # test files also have hotspot scores
        for f in test_facts:
            if len(top_files) >= top_n:
                break
            path = f.subject.id
            stem = Path(path).stem
            base = _test_base(stem)
            is_workflow_test = (
                _is_test_path(path)
                and any(kw in path.lower() for kw in _WORKFLOW_KEYWORDS)
            )
            if ((base and base in selected_stems) or is_workflow_test) and path not in top_files:
                top_files[path] = f.id

    # ── 4. Build CandidateContent (read file content once) ──────────────────
    results = []
    for path, fact_id in top_files.items():
        content = _read(repository_path, path)
        if content:
            results.append(CandidateContent(path=path, content=content, source_fact_ids=[fact_id]))
    return results
