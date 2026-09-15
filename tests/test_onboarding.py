"""Tests for Feature 10 — Onboarding path synthesis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.cli.registry import STAGE_REGISTRY
from project_intel.cli.types import PipelineContext
from project_intel.discovery.scope import ScopeConfig
from project_intel.facts import EntityRef, EntityType, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.llm import DisabledProvider, LLMCallResult, StructuredPrompt
from project_intel.onboarding import (
    STAGE,
    AvoidItem,
    EntryPoint,
    OnboardingPathResponse,
    TimeBoxed,
    WorkflowRef,
)
from project_intel.onboarding.analyzer import build_prompt, collect_input_facts

_SCOPE = ScopeConfig(exclude_globs=(".git/*",))


def _store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


def _fact(store: FactStore, run_id: str, fact_type: str, subject: str = "src/a.py") -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()),
        type=fact_type,
        subject=EntityRef(EntityType.FILE, subject),
        value={"score": 0.9} if fact_type == "hotspot_score" else {"in_degree": 5},
        provenance="computed",
        confidence=1.0,
        source_analyzer="test",
        evidence=(Evidence(
            kind="file",
            ref=FileRef(repository_id="repo", path=subject),
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


def _valid_response(fact_ids: list[str]) -> OnboardingPathResponse:
    return OnboardingPathResponse(
        entry_points=[EntryPoint(component="src/main.py", fact_ids=fact_ids, rationale="high centrality")],
        recommended_workflow=WorkflowRef(description="Follow the main pipeline", fact_ids=fact_ids),
        avoid_initially=[AvoidItem(component="src/legacy.py", fact_ids=fact_ids, rationale="low relevance")],
        time_boxed_understanding=TimeBoxed(
            thirty_minutes="Read the entry point and core module",
            two_hours="Trace the main workflow end-to-end",
        ),
        open_questions=["What external services does this depend on?"],
        confidence=0.8,
        fact_ids=fact_ids,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_has_open_questions():
    r = _valid_response(["abc"])
    assert r.open_questions == ["What external services does this depend on?"]


def test_schema_has_time_boxed():
    r = _valid_response(["abc"])
    assert r.time_boxed_understanding.thirty_minutes
    assert r.time_boxed_understanding.two_hours


# ---------------------------------------------------------------------------
# Analyzer — only reads from FactStore, no filesystem
# ---------------------------------------------------------------------------


def test_collect_input_facts_reads_from_store_only(tmp_path: Path):
    """Input assembly pulls only from FactStore — no filesystem access."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _fact(store, run_id, "centrality")
    facts = collect_input_facts(store)
    assert any(x.id == f.id for x in facts)
    store.close()


def test_collect_input_facts_includes_symbol_defined(tmp_path: Path):
    """Feature 10b: the model must see which symbols actually exist."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _fact(store, run_id, "symbol_defined")
    facts = collect_input_facts(store)
    assert any(x.id == f.id for x in facts)
    store.close()


def test_collect_input_facts_includes_all_upstream_types(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    types = [
        "centrality", "hotspot_score", "architecture_hypothesis",
        "business_workflow", "business_concept", "symbol_defined",
    ]
    inserted = [_fact(store, run_id, t) for t in types]
    facts = collect_input_facts(store)
    ids = {f.id for f in facts}
    for ins in inserted:
        assert ins.id in ids
    store.close()


def test_collect_input_facts_ignores_other_types(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    _fact(store, run_id, "language_detected")
    facts = collect_input_facts(store)
    assert all(f.type != "language_detected" for f in facts)
    store.close()


def test_build_prompt_contains_fact_ids(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _fact(store, run_id, "centrality")
    facts = collect_input_facts(store)
    prompt = build_prompt(facts)
    assert f.id in prompt.content
    assert prompt.category == "onboarding"
    assert prompt.schema_version == "onboarding@1.0"
    store.close()


def test_build_prompt_forbids_unsupported_claims(tmp_path: Path):
    """Feature 10b: prompt must require citations for component claims and forbid
    unsupported absence/capability claims."""
    store = _store(tmp_path)
    _fact(store, str(uuid.uuid4()), "centrality")
    facts = collect_input_facts(store)
    prompt = build_prompt(facts)
    assert "cite" in prompt.instructions.lower()
    assert "absent" in prompt.instructions.lower() or "unconfigured" in prompt.instructions.lower()
    store.close()


# ---------------------------------------------------------------------------
# Stage — degrade paths
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
    _fact(ctx.store, run_id, "centrality")
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_disabled" in (result.detail or "")
    ctx.store.close()


def test_stage_skipped_when_no_input_facts(tmp_path: Path):
    """No upstream facts → skip without calling the LLM."""
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


def test_stage_without_architecture_facts_still_produces_path(tmp_path: Path):
    """No architecture_hypothesis facts → still produces a path at lower confidence."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    # Only centrality + hotspot (no architecture or domain facts)
    c = _fact(store, run_id, "centrality")
    h = _fact(store, run_id, "hotspot_score")

    class _PartialProvider:
        provider_id = "partial"
        def complete(self, prompt: StructuredPrompt, schema):
            return LLMCallResult(
                status="ok",
                value=_valid_response([c.id, h.id]),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_PartialProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"
    assert result.facts_produced == 1
    stored = list(store.query_facts(type="onboarding_path", run_id=run_id))
    assert len(stored) == 1
    store.close()


# ---------------------------------------------------------------------------
# Stage — citation validation (same mechanism as F08/F09)
# ---------------------------------------------------------------------------


def test_stage_valid_citation_stored(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    real_fact = _fact(store, run_id, "centrality")

    class _OkProvider:
        provider_id = "ok"
        def complete(self, prompt: StructuredPrompt, schema):
            return LLMCallResult(
                status="ok",
                value=_valid_response([real_fact.id]),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_OkProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"
    assert result.facts_produced == 1

    stored = list(store.query_facts(type="onboarding_path", run_id=run_id))
    assert len(stored) == 1
    assert stored[0].provenance == "hypothesis"
    assert stored[0].value["open_questions"]
    store.close()


def test_stage_invalid_citation_rejected(tmp_path: Path):
    """A response citing a fake fact id → orchestrator rejects it → stage skipped."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    _fact(store, run_id, "centrality")

    class _BadProvider:
        provider_id = "bad"
        def complete(self, prompt, schema):
            return LLMCallResult(
                status="ok",
                value=_valid_response(["ghost-id-does-not-exist"]),
            )

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_BadProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_failed" in (result.detail or "")

    stored = list(store.query_facts(type="onboarding_path", run_id=run_id))
    assert stored == []
    store.close()


# ---------------------------------------------------------------------------
# Stage — ungrounded component-claim filter (Feature 10b)
# ---------------------------------------------------------------------------


def test_stage_drops_ungrounded_items_keeps_grounded(tmp_path: Path):
    """An entry_point/avoid_initially item with empty fact_ids is dropped; a sibling
    item with valid fact_ids in the same response is still stored."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    real_fact = _fact(store, run_id, "centrality")

    response = OnboardingPathResponse(
        entry_points=[
            EntryPoint(component="src/main.py", fact_ids=[real_fact.id], rationale="high centrality"),
            EntryPoint(component="src/ghost.py", fact_ids=[], rationale="unsupported claim"),
        ],
        recommended_workflow=WorkflowRef(description="Follow the main pipeline", fact_ids=[real_fact.id]),
        avoid_initially=[
            AvoidItem(component="src/legacy.py", fact_ids=[real_fact.id], rationale="low relevance"),
            AvoidItem(component="src/team.py", fact_ids=[], rationale="not configured"),
        ],
        time_boxed_understanding=TimeBoxed(thirty_minutes="Read main.py", two_hours="Trace the pipeline"),
        open_questions=["What external services does this depend on?"],
        confidence=0.8,
        fact_ids=[real_fact.id],
    )

    class _MixedProvider:
        provider_id = "mixed"
        def complete(self, prompt, schema):
            return LLMCallResult(status="ok", value=response)

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_MixedProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "ok"

    stored = next(iter(store.query_facts(type="onboarding_path", run_id=run_id)))
    entry_components = [e["component"] for e in stored.value["entry_points"]]
    avoid_components = [a["component"] for a in stored.value["avoid_initially"]]
    assert entry_components == ["src/main.py"]
    assert "src/ghost.py" not in entry_components
    assert avoid_components == ["src/legacy.py"]
    assert "src/team.py" not in avoid_components
    store.close()


def test_ungrounded_filter_runs_after_citation_validation(tmp_path: Path):
    """The Feature 10b filter is additive: a response citing a nonexistent fact_id is
    still rejected by Feature 07's citation validation exactly as before, before the
    stage-local empty-fact_ids filter ever runs."""
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    _fact(store, run_id, "centrality")

    class _BadProvider:
        provider_id = "bad"
        def complete(self, prompt, schema):
            return LLMCallResult(status="ok", value=_valid_response(["ghost-id-does-not-exist"]))

    ctx = PipelineContext(
        store=store, repository_path=tmp_path, run_id=run_id,
        scope=_SCOPE, llm_provider=_BadProvider(),
    )
    result = STAGE.run(ctx)
    assert result.status == "skipped"
    assert "llm_failed" in (result.detail or "")
    stored = list(store.query_facts(type="onboarding_path", run_id=run_id))
    assert stored == []
    store.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_onboarding_stage_in_registry():
    names = [s.name for s in STAGE_REGISTRY]
    assert "onboarding" in names


def test_onboarding_stage_last():
    names = [s.name for s in STAGE_REGISTRY]
    assert names[-1] == "onboarding"


def test_onboarding_after_domain():
    names = [s.name for s in STAGE_REGISTRY]
    assert names.index("domain") < names.index("onboarding")
