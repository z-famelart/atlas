"""Tests for Feature 09b — domain candidate selection fixes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.domain.analyzer import _INSTRUCTIONS, build_prompt
from project_intel.domain.selector import CandidateContent, select_candidates
from project_intel.facts import EntityRef, EntityType, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore


def _store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


def _hotspot_fact(store: FactStore, run_id: str, path: str, score: float) -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()),
        type="hotspot_score",
        subject=EntityRef(EntityType.FILE, path),
        value={"combined": score, "components_available": "1/4", "components": {}},
        provenance="computed",
        confidence=1.0,
        source_analyzer="test",
        evidence=(Evidence(
            kind="file",
            ref=FileRef(repository_id="repo", path=path),
            source_analyzer="test",
            retrieved_at=now,
        ),),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )
    store.insert_facts([f])
    return f


def _centrality_fact(store: FactStore, run_id: str, path: str, in_degree: int) -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()),
        type="centrality",
        subject=EntityRef(EntityType.FILE, path),
        value={"in_degree": in_degree, "out_degree": 3},
        provenance="computed",
        confidence=1.0,
        source_analyzer="test",
        evidence=(Evidence(
            kind="file",
            ref=FileRef(repository_id="repo", path=path),
            source_analyzer="test",
            retrieved_at=now,
        ),),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )
    store.insert_facts([f])
    return f


# ---------------------------------------------------------------------------
# A. Cumulative top_n budget
# ---------------------------------------------------------------------------


def test_top_n_is_hard_cumulative_budget(tmp_path: Path):
    """20 hotspot + 15 entrypoint candidates + workflow-keyword test hits → exactly 20."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    top_n = 20

    # Step 1: 20 hotspot files (exactly fills the budget)
    for i in range(top_n):
        _hotspot_fact(store, run_id, f"src/module_{i}.py", float(top_n - i))

    # Step 2: 15 additional entrypoint-only files
    for i in range(15):
        _centrality_fact(store, run_id, f"src/entry_{i}.py", in_degree=0)

    # Step 3: several test files whose stems contain workflow keywords
    for i in range(5):
        _hotspot_fact(store, run_id, f"tests/test_service_{i}.py", 0.1)

    candidates = select_candidates(store, tmp_path, top_n=top_n, run_id=run_id)
    assert len(candidates) == top_n
    store.close()


# ---------------------------------------------------------------------------
# B. is_workflow_test requires a real test-file signal
# ---------------------------------------------------------------------------


def test_non_test_workflow_path_not_added(tmp_path: Path):
    """.github/workflows/ci.yml must not be added via the workflow-keyword step.

    ci.yml has 'workflow' in its path but is not a test file. Step 3 should
    not add it. The fixture gives it only a hotspot score below the top_n
    threshold: step 1 picks the high-scoring source files, step 3 sees ci.yml
    and must skip it because it is not a test file.
    """
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())

    # Fill the budget with high-scoring source files so step 1 is exhausted
    for i in range(5):
        _hotspot_fact(store, run_id, f"src/module_{i}.py", float(10 - i))

    # ci.yml: has 'workflow' in path but is NOT a test file — score below the top 5
    _hotspot_fact(store, run_id, ".github/workflows/ci.yml", 0.01)

    # top_n=5 exhausts the budget at step 1; step 3 must not add ci.yml
    candidates = select_candidates(store, tmp_path, top_n=5, run_id=run_id)
    paths = {c.path for c in candidates}
    assert ".github/workflows/ci.yml" not in paths
    store.close()


def test_real_test_file_with_workflow_keyword_is_added(tmp_path: Path):
    """tests/festivals/test_services.py (real test file, stem matches source) is still added."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())

    # Source file already selected via step 1
    _hotspot_fact(store, run_id, "festivals/services.py", 0.9)
    # Real test file: in tests/ directory, stem matches source stem — eligible via step 3
    _hotspot_fact(store, run_id, "tests/festivals/test_services.py", 0.05)

    candidates = select_candidates(store, tmp_path, top_n=10, run_id=run_id)
    paths = {c.path for c in candidates}
    assert "tests/festivals/test_services.py" in paths
    store.close()


# ---------------------------------------------------------------------------
# C. Multi-file coverage instruction in _INSTRUCTIONS / build_prompt
# ---------------------------------------------------------------------------


def test_instructions_include_coverage_requirement():
    """_INSTRUCTIONS must tell the model to examine every candidate file."""
    assert "every file" in _INSTRUCTIONS.lower() or "examine every" in _INSTRUCTIONS.lower()


def test_build_prompt_output_includes_coverage_instruction():
    """build_prompt result's instructions string includes the coverage requirement."""
    candidates = [
        CandidateContent(path="src/a.py", content="class Order: pass", source_fact_ids=["fid1"]),
        CandidateContent(path="src/b.py", content="class Invoice: pass", source_fact_ids=["fid2"]),
    ]
    prompt = build_prompt(candidates)
    assert "every file" in prompt.instructions.lower() or "examine every" in prompt.instructions.lower()


# ---------------------------------------------------------------------------
# D. run_id scoping
# ---------------------------------------------------------------------------


def test_select_candidates_scoped_to_run_id(tmp_path: Path):
    """Facts from a different run_id must not appear in the candidates."""
    store = _store(tmp_path)
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())

    # run_a: one hotspot file
    _hotspot_fact(store, run_a, "src/run_a_module.py", 0.9)
    # run_b: a different hotspot file
    _hotspot_fact(store, run_b, "src/run_b_module.py", 0.8)
    # run_b: one centrality entrypoint
    _centrality_fact(store, run_b, "src/run_b_entry.py", in_degree=0)

    candidates_a = select_candidates(store, tmp_path, top_n=20, run_id=run_a)
    paths_a = {c.path for c in candidates_a}
    assert "src/run_a_module.py" in paths_a
    assert "src/run_b_module.py" not in paths_a
    assert "src/run_b_entry.py" not in paths_a

    candidates_b = select_candidates(store, tmp_path, top_n=20, run_id=run_b)
    paths_b = {c.path for c in candidates_b}
    assert "src/run_b_module.py" in paths_b
    assert "src/run_b_entry.py" in paths_b
    assert "src/run_a_module.py" not in paths_b

    store.close()
