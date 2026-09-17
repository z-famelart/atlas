"""Tests for Feature 09 — Domain understanding."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.cli.registry import STAGE_REGISTRY
from project_intel.cli.types import PipelineContext
from project_intel.discovery.scope import ScopeConfig
from project_intel.domain import (
    BusinessConcept,
    BusinessWorkflow,
    CandidateContent,
    DomainResponse,
    GlossaryTerm,
)
from project_intel.domain.analyzer import build_prompt
from project_intel.domain.selector import select_candidates
from project_intel.domain.stage import STAGE
from project_intel.facts import EntityRef, EntityType, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.llm import DisabledProvider, LLMCallResult, StructuredPrompt

_SCOPE = ScopeConfig(exclude_globs=(".git/*",))


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


def _ctx(tmp_path: Path, llm_provider=None) -> PipelineContext:
    return PipelineContext(
        store=_store(tmp_path),
        repository_path=tmp_path,
        run_id=str(uuid.uuid4()),
        scope=_SCOPE,
        llm_provider=llm_provider,
    )


# ---------------------------------------------------------------------------
# CandidateContent dataclass
# ---------------------------------------------------------------------------


def test_candidate_content_fields():
    c = CandidateContent(path="src/a.py", content="x = 1", source_fact_ids=["abc"])
    assert c.path == "src/a.py"
    assert c.content == "x = 1"
    assert c.source_fact_ids == ["abc"]


# ---------------------------------------------------------------------------
# Selector — bounded by top_n
# ---------------------------------------------------------------------------


def test_selector_returns_top_n(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    for i in range(50):
        _hotspot_fact(store, run_id, f"src/f{i}.py", float(i) / 50)
    candidates = select_candidates(store, tmp_path, top_n=10)
    assert len(candidates) <= 20  # top_n * 2 max
    store.close()


def test_selector_bounded_regardless_of_repo_size(tmp_path: Path):
    """Increasing the number of hotspot facts does not grow the result beyond top_n."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    top_n = 5
    for i in range(200):
        _hotspot_fact(store, run_id, f"src/module_{i}.py", float(i) / 200)
    candidates = select_candidates(store, tmp_path, top_n=top_n)
    assert len(candidates) <= top_n * 2
    store.close()


def test_selector_includes_entrypoints(tmp_path: Path):
    """Files with in_degree=0 are included even if not in top hotspots."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.py").write_text("# stub\n")
    (tmp_path / "src" / "main.py").write_text("# stub\n")
    _hotspot_fact(store, run_id, "src/core.py", 0.9)
    _centrality_fact(store, run_id, "src/main.py", in_degree=0)  # entrypoint, no hotspot fact
    candidates = select_candidates(store, tmp_path, top_n=5)
    paths = {c.path for c in candidates}
    assert "src/main.py" in paths
    store.close()


def test_selector_empty_store(tmp_path: Path):
    store = _store(tmp_path)
    candidates = select_candidates(store, tmp_path)
    assert candidates == []
    store.close()


def test_selector_reads_file_content(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 42")
    _hotspot_fact(store, run_id, "src/a.py", 0.8)
    candidates = select_candidates(store, tmp_path, top_n=5)
    by_path = {c.path: c for c in candidates}
    assert by_path["src/a.py"].content == "x = 42"
    store.close()


def test_selector_missing_file_excluded(tmp_path: Path):
    """A candidate whose file does not exist on disk is excluded (not sent as empty content)."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    _hotspot_fact(store, run_id, "src/ghost.py", 0.9)
    candidates = select_candidates(store, tmp_path, top_n=5)
    assert candidates == []
    store.close()


# ---------------------------------------------------------------------------
# Analyzer — prompt structure
# ---------------------------------------------------------------------------


def test_build_prompt_category_and_schema():
    c = CandidateContent(path="src/a.py", content="class Order: pass", source_fact_ids=["fid1"])
    prompt = build_prompt([c])
    assert prompt.category == "domain"
    assert prompt.schema_version == "domain@1.0"


def test_build_prompt_contains_fact_id():
    c = CandidateContent(path="src/a.py", content="hello", source_fact_ids=["unique-fact-id"])
    prompt = build_prompt([c])
    assert "unique-fact-id" in prompt.content


def test_build_prompt_empty_candidates():
    prompt = build_prompt([])
    assert prompt.content is not None


# ---------------------------------------------------------------------------
# Stage — disabled / no candidates
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
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("# stub\n")
    _hotspot_fact(ctx.store, run_id, "src/a.py", 0.8)
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_disabled" in (result.detail or "")
    ctx.store.close()


def test_stage_skipped_when_no_candidates(tmp_path: Path):
    """Empty store → no candidates → skip without LLM call."""
    calls = []

    class _CountProvider:
        provider_id = "count"
        def complete(self, p, s):
            calls.append(1)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")

    ctx = _ctx(tmp_path, llm_provider=_CountProvider())
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert calls == []
    ctx.store.close()


# ---------------------------------------------------------------------------
# Stage — citation validation
# ---------------------------------------------------------------------------


def test_stage_valid_citations_stored(tmp_path: Path):
    """Valid citations → domain facts stored with provenance=hypothesis."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "order.py").write_text("# stub\n")
    real_fact = _hotspot_fact(store, run_id, "src/order.py", 0.9)

    class _OkProvider:
        provider_id = "ok"
        def complete(self, prompt: StructuredPrompt, schema):
            return LLMCallResult(
                status="ok",
                value=DomainResponse(
                    concepts=[BusinessConcept(name="Order", description="A customer order", fact_ids=[real_fact.id])],
                    workflows=[BusinessWorkflow(name="checkout", description="Checkout flow", fact_ids=[real_fact.id])],
                    glossary=[GlossaryTerm(term="SKU", definition="Stock-keeping unit", fact_ids=[real_fact.id])],
                ),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_OkProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"
    assert result.facts_produced == 3

    concepts = list(store.query_facts(type="business_concept", run_id=run_id))
    workflows = list(store.query_facts(type="business_workflow", run_id=run_id))
    glossary = list(store.query_facts(type="glossary_term", run_id=run_id))
    assert len(concepts) == 1
    assert concepts[0].provenance == "hypothesis"
    assert len(workflows) == 1
    assert workflows[0].provenance == "hypothesis"
    assert len(glossary) == 1
    assert glossary[0].provenance == "hypothesis"
    store.close()


def test_stage_invalid_citation_rejected(tmp_path: Path):
    """Fake fact_id → orchestrator rejects → stage skipped, nothing stored."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.py").write_text("# stub\n")
    _hotspot_fact(store, run_id, "src/a.py", 0.8)

    class _BadProvider:
        provider_id = "bad"
        def complete(self, prompt, schema):
            return LLMCallResult(
                status="ok",
                value=DomainResponse(
                    concepts=[BusinessConcept(name="X", description="y", fact_ids=["ghost-id"])],
                    workflows=[],
                    glossary=[],
                ),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_BadProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_failed" in (result.detail or "")
    assert list(store.query_facts(type="business_concept", run_id=run_id)) == []
    store.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_domain_response_fields():
    r = DomainResponse(
        concepts=[BusinessConcept(name="Order", description="desc", fact_ids=["f1"])],
        workflows=[BusinessWorkflow(name="checkout", description="desc", fact_ids=["f1"])],
        glossary=[GlossaryTerm(term="SKU", definition="def", fact_ids=["f1"])],
    )
    assert len(r.concepts) == 1
    assert len(r.workflows) == 1
    assert len(r.glossary) == 1


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_domain_stage_in_registry():
    names = [s.name for s in STAGE_REGISTRY]
    assert "domain" in names


def test_domain_after_hotspots_and_code_graph():
    names = [s.name for s in STAGE_REGISTRY]
    assert names.index("hotspots") < names.index("domain")
    assert names.index("code_graph") < names.index("domain")
