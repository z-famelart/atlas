"""Tests for Feature 08 — Architecture interpretation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_intel.architecture import ArchitectureHypothesis, ArchitectureResponse
from project_intel.architecture.analyzer import build_prompt, collect_graph_facts
from project_intel.architecture.stage import STAGE
from project_intel.cli.registry import STAGE_REGISTRY
from project_intel.cli.types import PipelineContext
from project_intel.discovery.scope import ScopeConfig
from project_intel.facts import EntityRef, EntityType, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.llm import DisabledProvider, LLMCallResult, StructuredPrompt

_SCOPE = ScopeConfig(exclude_globs=(".git/*",))


def _store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


def _graph_fact(store: FactStore, run_id: str, fact_type: str = "centrality") -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(EntityType.FILE, "src/a.py"),
        value={"in_degree": 5} if fact_type == "centrality" else {"id": 0},
        provenance="computed",
        confidence=1.0,
        source_analyzer="test",
        evidence=(Evidence(
            kind="file",
            ref=FileRef(repository_id="repo", path="src/a.py"),
            source_analyzer="test",
            retrieved_at=now,
        ),),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )
    store.insert_facts([f])
    return f


def _ctx(tmp_path: Path, llm_provider=None) -> PipelineContext:
    store = _store(tmp_path)
    return PipelineContext(
        store=store,
        repository_path=tmp_path,
        run_id=str(uuid.uuid4()),
        scope=_SCOPE,
        llm_provider=llm_provider,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_architecture_hypothesis_has_fact_ids():
    h = ArchitectureHypothesis(pattern="layered", confidence=0.8, fact_ids=["abc"])
    assert h.fact_ids == ["abc"]


def test_architecture_response_has_hypotheses():
    r = ArchitectureResponse(hypotheses=[
        ArchitectureHypothesis(pattern="layered", confidence=0.9, fact_ids=[]),
    ])
    assert len(r.hypotheses) == 1


def test_uncatalogued_has_description():
    h = ArchitectureHypothesis(
        pattern="uncatalogued",
        confidence=0.5,
        fact_ids=[],
        pattern_description="pipeline",
    )
    assert h.pattern_description == "pipeline"


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def test_collect_graph_facts_returns_centrality(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _graph_fact(store, run_id, "centrality")
    facts = collect_graph_facts(store)
    ids = [x.id for x in facts]
    assert f.id in ids
    store.close()


def test_collect_graph_facts_ignores_other_types(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    # language_detected is NOT a graph fact
    now = datetime.now(UTC)
    lang = Fact(
        id=str(uuid.uuid4()), type="language_detected",
        subject=EntityRef(EntityType.FILE, "a.py"),
        value={"language": "Python", "loc": 10},
        provenance="observed", confidence=1.0, source_analyzer="test",
        evidence=(Evidence(kind="file", ref=FileRef(repository_id="r", path="a.py"), source_analyzer="test", retrieved_at=now),),
        created_at=now, schema_version=SCHEMA_VERSION, run_id=run_id,
    )
    store.insert_facts([lang])
    facts = collect_graph_facts(store)
    assert all(f.type != "language_detected" for f in facts)
    store.close()


def test_build_prompt_contains_fact_ids(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _graph_fact(store, run_id)
    facts = collect_graph_facts(store)
    prompt = build_prompt(facts)
    assert f.id in prompt.content
    assert prompt.category == "architecture"
    assert prompt.schema_version == "architecture@1.0"
    store.close()


# ---------------------------------------------------------------------------
# Stage — disabled provider
# ---------------------------------------------------------------------------


def test_stage_skipped_when_no_llm_provider(tmp_path: Path):
    ctx = _ctx(tmp_path, llm_provider=None)
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "not_analyzed" in (result.detail or "")
    ctx.store.close()


def test_stage_skipped_when_disabled_provider(tmp_path: Path):
    ctx = _ctx(tmp_path, llm_provider=DisabledProvider())
    run_id = ctx.run_id
    _graph_fact(ctx.store, run_id)
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    ctx.store.close()


def test_stage_skipped_when_no_graph_facts(tmp_path: Path):
    """No graph facts → skip without calling the LLM."""
    calls = []

    class _CountProvider:
        provider_id = "count"
        def complete(self, p, s):
            calls.append(1)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")

    ctx = _ctx(tmp_path, llm_provider=_CountProvider())
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert calls == []  # never reached LLM
    ctx.store.close()


# ---------------------------------------------------------------------------
# Stage — valid citation accepted and stored
# ---------------------------------------------------------------------------


def test_stage_valid_citation_stored(tmp_path: Path):
    """A response citing a real fact id → hypothesis fact stored with provenance=hypothesis."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    real_fact = _graph_fact(store, run_id)

    class _OkProvider:
        provider_id = "ok"
        def complete(self, prompt: StructuredPrompt, schema):
            return LLMCallResult(
                status="ok",
                value=ArchitectureResponse(hypotheses=[
                    ArchitectureHypothesis(
                        pattern="layered",
                        confidence=0.85,
                        fact_ids=[real_fact.id],
                    ),
                ]),
            )

    ctx = PipelineContext(
        store=store,
        repository_path=tmp_path,
        run_id=run_id,
        scope=_SCOPE,
        llm_provider=_OkProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"
    assert result.facts_produced == 1

    stored = list(store.query_facts(type="architecture_hypothesis", run_id=run_id))
    assert len(stored) == 1
    assert stored[0].provenance == "hypothesis"
    assert stored[0].value["pattern"] == "layered"
    assert stored[0].value["confidence"] == pytest.approx(0.85)
    store.close()


# ---------------------------------------------------------------------------
# Stage — invalid citation rejected
# ---------------------------------------------------------------------------


def test_stage_invalid_citation_rejected(tmp_path: Path):
    """A response citing a fake fact id → orchestrator rejects it → stage skipped."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    _graph_fact(store, run_id)  # real graph fact exists, but not cited

    class _BadProvider:
        provider_id = "bad"
        def complete(self, prompt, schema):
            return LLMCallResult(
                status="ok",
                value=ArchitectureResponse(hypotheses=[
                    ArchitectureHypothesis(
                        pattern="microservices",
                        confidence=0.7,
                        fact_ids=["ghost-id-does-not-exist"],
                    ),
                ]),
            )

    ctx = PipelineContext(
        store=store,
        repository_path=tmp_path,
        run_id=run_id,
        scope=_SCOPE,
        llm_provider=_BadProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_failed" in (result.detail or "")

    stored = list(store.query_facts(type="architecture_hypothesis", run_id=run_id))
    assert stored == []
    store.close()


# ---------------------------------------------------------------------------
# Stage — multiple hypotheses
# ---------------------------------------------------------------------------


def test_stage_multiple_hypotheses(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _graph_fact(store, run_id)

    class _MultiProvider:
        provider_id = "multi"
        def complete(self, prompt, schema):
            return LLMCallResult(
                status="ok",
                value=ArchitectureResponse(hypotheses=[
                    ArchitectureHypothesis(pattern="layered", confidence=0.7, fact_ids=[f.id]),
                    ArchitectureHypothesis(pattern="modular_monolith", confidence=0.5, fact_ids=[f.id]),
                ]),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_MultiProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"
    assert result.facts_produced == 2
    stored = list(store.query_facts(type="architecture_hypothesis", run_id=run_id))
    assert len(stored) == 2
    store.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_architecture_stage_in_registry():
    names = [s.name for s in STAGE_REGISTRY]
    assert "architecture" in names


def test_architecture_after_code_graph():
    names = [s.name for s in STAGE_REGISTRY]
    assert names.index("code_graph") < names.index("architecture")
