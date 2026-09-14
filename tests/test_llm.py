"""Tests for Feature 07 — LLM orchestration framework."""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from project_intel.facts import EntityRef, EntityType, Evidence, Fact
from project_intel.facts.refs import FileRef
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.llm import (
    BudgetConfig,
    ClaudeCodeProvider,
    DisabledProvider,
    Hypothesis,
    LLMCallResult,
    LLMOrchestrator,
    StructuredPrompt,
)
from project_intel.llm.budget import BudgetTracker
from project_intel.llm.cache import LLMCache, cache_key
from project_intel.llm.citation import validate_citations
from project_intel.llm.providers import _schema_description

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _SimpleResult:
    name: str
    confidence: float
    fact_ids: list[str]


@dataclasses.dataclass
class _HypothesisResult:
    hypotheses: list[Hypothesis]


def _prompt(category: str = "test", tokens: int = 0) -> StructuredPrompt:
    return StructuredPrompt(
        instructions="Return the schema as JSON.",
        content="{}",
        schema_version="v1",
        category=category,
        estimated_input_tokens=tokens,
    )


def _store(tmp_path: Path) -> FactStore:
    return FactStore(tmp_path / "facts.sqlite")


def _fact(store: FactStore, run_id: str) -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()),
        type="test_fact",
        subject=EntityRef(EntityType.FILE, "src/a.py"),
        value={},
        provenance="observed",
        confidence=1.0,
        source_analyzer="test",
        evidence=(Evidence(kind="file", ref=FileRef(repository_id="r", path="src/a.py"), source_analyzer="test", retrieved_at=now),),
        created_at=now,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
    )
    store.insert_facts([f])
    return f


# ---------------------------------------------------------------------------
# DisabledProvider
# ---------------------------------------------------------------------------


def test_disabled_provider_returns_llm_failed():
    result = DisabledProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"
    assert result.value is None


def test_disabled_provider_same_as_real_failure():
    """DisabledProvider must be indistinguishable from a real provider failure."""
    d = DisabledProvider().complete(_prompt(), _SimpleResult)
    assert d.status == "not_analyzed"
    assert d.reason == "llm_failed"


# ---------------------------------------------------------------------------
# ClaudeCodeProvider — tested against a fixture (no claude binary needed)
# ---------------------------------------------------------------------------


FIXTURE = Path(__file__).parent / "fixtures" / "claude_output.json"


def test_claude_provider_normalize_fixture(tmp_path: Path, monkeypatch):
    """ClaudeCodeProvider parses the captured CLI output into the schema."""
    raw_envelope = FIXTURE.read_text()

    def _fake_run(*args, **kwargs):
        class _R:
            returncode = 0
            stdout = raw_envelope
        return _R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = ClaudeCodeProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "ok"
    assert isinstance(result.value, _SimpleResult)
    assert result.value.name == "hello"
    assert result.value.confidence == pytest.approx(0.9)


def test_claude_provider_nonzero_returncode(monkeypatch):
    def _fake_run(*args, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
        return _R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = ClaudeCodeProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_claude_provider_malformed_json(monkeypatch):
    def _fake_run(*args, **kwargs):
        class _R:
            returncode = 0
            stdout = "not json"
        return _R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = ClaudeCodeProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_claude_provider_is_error_flag(monkeypatch):
    def _fake_run(*args, **kwargs):
        class _R:
            returncode = 0
            stdout = json.dumps({"type": "result", "is_error": True, "result": ""})
        return _R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = ClaudeCodeProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"


# ---------------------------------------------------------------------------
# Citation validator
# ---------------------------------------------------------------------------


def test_citation_valid(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _fact(store, run_id)

    @dataclasses.dataclass
    class _Cited:
        label: str
        fact_ids: list[str]

    response = _Cited(label="x", fact_ids=[f.id])
    valid, unknown = validate_citations(response, store)
    assert valid is True
    assert unknown == []
    store.close()


def test_citation_unknown_id_rejected(tmp_path: Path):
    store = _store(tmp_path)

    @dataclasses.dataclass
    class _Cited:
        label: str
        fact_ids: list[str]

    response = _Cited(label="x", fact_ids=["nonexistent-id"])
    valid, unknown = validate_citations(response, store)
    assert valid is False
    assert "nonexistent-id" in unknown
    store.close()


def test_citation_no_fact_ids_always_valid(tmp_path: Path):
    store = _store(tmp_path)

    @dataclasses.dataclass
    class _NoCitations:
        label: str

    valid, unknown = validate_citations(_NoCitations(label="y"), store)
    assert valid is True
    assert unknown == []
    store.close()


def test_citation_nested_hypothesis(tmp_path: Path):
    store = _store(tmp_path)
    run_id = str(uuid.uuid4())
    f = _fact(store, run_id)

    result = _HypothesisResult(hypotheses=[
        Hypothesis(value="api_gateway", confidence=0.8, fact_ids=[f.id]),
    ])
    valid, _ = validate_citations(result, store)
    assert valid is True
    store.close()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_miss_returns_none(tmp_path: Path):
    cache = LLMCache(tmp_path / "cache.sqlite")
    assert cache.get("not-a-key") is None
    cache.close()


def test_cache_set_get(tmp_path: Path):
    cache = LLMCache(tmp_path / "cache.sqlite")
    cache.set("k1", '{"x": 1}')
    assert cache.get("k1") == '{"x": 1}'
    cache.close()


def test_cache_key_changes_with_content():
    p1 = StructuredPrompt(instructions="a", content="b", schema_version="v1", category="c")
    p2 = StructuredPrompt(instructions="a", content="CHANGED", schema_version="v1", category="c")
    assert cache_key(p1, "provider") != cache_key(p2, "provider")


def test_cache_key_changes_with_provider():
    p = StructuredPrompt(instructions="a", content="b", schema_version="v1", category="c")
    assert cache_key(p, "provider-a") != cache_key(p, "provider-b")


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


def test_budget_within_limit():
    tracker = BudgetTracker(BudgetConfig(tokens_per_category={"arch": 1000}))
    assert tracker.within_budget("arch", 500) is True


def test_budget_exceeded():
    tracker = BudgetTracker(BudgetConfig(tokens_per_category={"arch": 100}))
    tracker.record("arch", 90)
    assert tracker.within_budget("arch", 20) is False


def test_budget_unlimited_category():
    tracker = BudgetTracker(BudgetConfig.unlimited())
    assert tracker.within_budget("anything", 999_999) is True


def test_budget_record_accumulates():
    tracker = BudgetTracker(BudgetConfig(tokens_per_category={"arch": 1000}))
    tracker.record("arch", 300)
    tracker.record("arch", 400)
    assert tracker.used("arch") == 700


# ---------------------------------------------------------------------------
# LLMOrchestrator — fake provider for call-counting
# ---------------------------------------------------------------------------


class _FakeProvider:
    provider_id = "fake"

    def __init__(self, value: Any = None, fail: bool = False) -> None:
        self.calls = 0
        self._value = value
        self._fail = fail

    def complete(self, prompt: StructuredPrompt, schema: type) -> LLMCallResult:
        self.calls += 1
        if self._fail:
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        return LLMCallResult(status="ok", value=self._value or schema(name="x", confidence=0.5, fact_ids=[]))


def _orchestrator(provider, tmp_path, budget_config=None) -> LLMOrchestrator:
    store = FactStore(tmp_path / "facts.sqlite")
    return LLMOrchestrator(
        provider=provider,
        store=store,
        cache=LLMCache(tmp_path / "cache.sqlite"),
        budget=BudgetTracker(budget_config or BudgetConfig.unlimited()),
    )


def test_orchestrator_cache_hit_no_second_call(tmp_path: Path):
    """Same prompt returns cached result — provider called only once."""
    provider = _FakeProvider()
    orch = _orchestrator(provider, tmp_path)

    p = _prompt()
    r1 = orch.complete(p, _SimpleResult)
    r2 = orch.complete(p, _SimpleResult)

    assert r1.status == "ok"
    assert r2.status == "ok"
    assert provider.calls == 1  # second hit from cache


def test_orchestrator_cache_miss_on_different_prompt(tmp_path: Path):
    provider = _FakeProvider()
    orch = _orchestrator(provider, tmp_path)

    p1 = StructuredPrompt(instructions="a", content="1", schema_version="v1", category="c")
    p2 = StructuredPrompt(instructions="a", content="2", schema_version="v1", category="c")
    orch.complete(p1, _SimpleResult)
    orch.complete(p2, _SimpleResult)

    assert provider.calls == 2


def test_orchestrator_budget_exceeded_skips_provider(tmp_path: Path):
    provider = _FakeProvider()
    cfg = BudgetConfig(tokens_per_category={"test": 10})
    orch = _orchestrator(provider, tmp_path, cfg)

    result = orch.complete(_prompt("test", 100), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "budget_exceeded"
    assert provider.calls == 0


def test_orchestrator_provider_failure_passthrough(tmp_path: Path):
    provider = _FakeProvider(fail=True)
    orch = _orchestrator(provider, tmp_path)
    result = orch.complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_orchestrator_citation_invalid_rejected(tmp_path: Path):
    """A response with unknown fact_ids is rejected by the orchestrator."""
    @dataclasses.dataclass
    class _R:
        label: str
        fact_ids: list[str]

    class _BadProvider:
        provider_id = "bad"
        calls = 0
        def complete(self, prompt, schema):
            self.__class__.calls += 1
            return LLMCallResult(status="ok", value=_R(label="x", fact_ids=["ghost-id"]))

    provider = _BadProvider()
    orch = _orchestrator(provider, tmp_path)
    result = orch.complete(_prompt(), _R)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_orchestrator_disabled_provider(tmp_path: Path):
    orch = _orchestrator(DisabledProvider(), tmp_path)
    result = orch.complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


# ---------------------------------------------------------------------------
# Hypothesis schema (multiple concurrent hypotheses)
# ---------------------------------------------------------------------------


def test_hypothesis_list_supported(tmp_path: Path):
    """Hypothesis lists are a first-class schema shape in the framework."""
    h = Hypothesis(value="event_driven", confidence=0.8, fact_ids=[])
    result = _HypothesisResult(hypotheses=[h])
    valid, _ = validate_citations(result, _store(tmp_path))
    assert valid is True


# ---------------------------------------------------------------------------
# Schema description helper
# ---------------------------------------------------------------------------


def test_schema_description_lists_fields():
    desc = _schema_description(_SimpleResult)
    assert "name" in desc
    assert "confidence" in desc
    assert "fact_ids" in desc
