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


def test_disabled_provider_returns_llm_disabled():
    result = DisabledProvider().complete(_prompt(), _SimpleResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_disabled"
    assert result.value is None


def test_disabled_provider_distinct_from_real_failure():
    """DisabledProvider's reason must be distinguishable from a genuine provider failure."""
    d = DisabledProvider().complete(_prompt(), _SimpleResult)
    assert d.status == "not_analyzed"
    assert d.reason == "llm_disabled"
    assert d.reason != "llm_failed"


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
    assert result.reason == "llm_disabled"


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

# ---------------------------------------------------------------------------
# OllamaProvider — Feature 07b
# ---------------------------------------------------------------------------


import urllib.error
import urllib.request as _urllib_request

from project_intel.llm import LlamaCppProvider, OllamaProvider
from project_intel.llm.providers import suggest_ollama_budget as _suggest


@dataclasses.dataclass
class _OllamaResult:
    name: str
    confidence: float
    fact_ids: list[str]


def _make_ollama_http_response(body: dict):
    """Build a minimal fake HTTP response object for urlopen mocking."""

    class _Resp:
        def read(self):
            return json.dumps(body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    return _Resp()


def _make_http_error(code: int, body: dict):
    import io
    import urllib.error
    return urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=code,
        msg="error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(body).encode()),
    )


def test_ollama_provider_missing_model():
    """OllamaProvider without model raises TypeError with actionable message."""
    with pytest.raises(TypeError, match="OLLAMA_MODEL"):
        OllamaProvider(model="")


def test_ollama_provider_no_default_model():
    """OllamaProvider requires model — cannot be constructed without it."""
    import inspect
    sig = inspect.signature(OllamaProvider.__init__)
    # 'model' has no default
    assert sig.parameters["model"].default is inspect.Parameter.empty


def test_ollama_provider_ok_response(monkeypatch):
    """Well-formed JSON response is structured into the schema."""
    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True  # skip connectivity check

    response_body = {"response": json.dumps({"name": "hello", "confidence": 0.9, "fact_ids": []})}

    monkeypatch.setattr(_urllib_request, "urlopen", lambda *a, **kw: _make_ollama_http_response(response_body))

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "ok"
    assert isinstance(result.value, _OllamaResult)
    assert result.value.name == "hello"


def test_ollama_provider_malformed_json(monkeypatch):
    """Non-JSON response produces not_analyzed: llm_failed."""
    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True

    class _BadResp:
        def read(self): return b"not json"
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(_urllib_request, "urlopen", lambda *a, **kw: _BadResp())

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_ollama_provider_connection_error(monkeypatch):
    """Connection refused produces not_analyzed: llm_failed."""
    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True

    def _raise(*a, **kw):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(_urllib_request, "urlopen", _raise)

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_ollama_provider_timeout(monkeypatch):
    """Timeout produces not_analyzed: llm_failed."""
    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True

    def _raise(*a, **kw):
        raise TimeoutError("timed out")

    monkeypatch.setattr(_urllib_request, "urlopen", _raise)

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"


def test_ollama_provider_model_not_found_message(monkeypatch, capsys):
    """404 with 'not found' body prints actionable message, returns not_analyzed."""
    provider = OllamaProvider(model="missing-model")
    provider._connectivity_checked = True

    def _raise(*a, **kw):
        raise _make_http_error(404, {"error": "model 'missing-model' not found, try pulling it first"})

    monkeypatch.setattr(_urllib_request, "urlopen", _raise)

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"
    captured = capsys.readouterr()
    assert "ollama pull missing-model" in captured.out


def test_ollama_provider_connectivity_check_prints_message(monkeypatch, capsys):
    """Connection refused on first call prints actionable message."""
    provider = OllamaProvider(model="qwen2.5:14b")

    call_count = [0]

    def _raise(*a, **kw):
        call_count[0] += 1
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(_urllib_request, "urlopen", _raise)

    result = provider.complete(_prompt(), _OllamaResult)
    captured = capsys.readouterr()
    assert "ollama serve" in captured.out
    assert result.status == "not_analyzed"


def test_ollama_connectivity_check_runs_only_once(monkeypatch):
    """_check_connectivity is only called once per instance."""
    provider = OllamaProvider(model="qwen2.5:14b")

    ping_calls = [0]
    generate_calls = [0]

    def _urlopen(url_or_req, *a, **kw):
        url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
        if "api/tags" in url:
            ping_calls[0] += 1
            return _make_ollama_http_response({})
        generate_calls[0] += 1
        # Return valid response
        body = {"response": json.dumps({"name": "x", "confidence": 0.5, "fact_ids": []})}
        return _make_ollama_http_response(body)

    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)

    provider.complete(_prompt(), _OllamaResult)
    provider.complete(_prompt("other"), _OllamaResult)

    assert ping_calls[0] == 1  # checked only once


def test_ollama_citation_validator_applied(tmp_path: Path, monkeypatch):
    """OllamaProvider output with unknown fact_ids is rejected by orchestrator citation check."""
    from project_intel.llm import LLMOrchestrator
    from project_intel.llm.budget import BudgetTracker
    from project_intel.llm.cache import LLMCache

    @dataclasses.dataclass
    class _Cited:
        label: str
        fact_ids: list[str]

    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True

    def _urlopen(*a, **kw):
        body = {"response": json.dumps({"label": "x", "fact_ids": ["ghost-id"]})}
        return _make_ollama_http_response(body)

    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)

    store = FactStore(tmp_path / "facts.sqlite")
    orch = LLMOrchestrator(
        provider=provider,
        store=store,
        cache=LLMCache(tmp_path / "cache.sqlite"),
        budget=BudgetTracker(BudgetConfig.unlimited()),
    )
    result = orch.complete(_prompt(), _Cited)
    assert result.status == "not_analyzed"
    assert result.reason == "llm_failed"
    store.close()


def test_suggest_ollama_budget_from_fixture(monkeypatch):
    """suggest_ollama_budget returns int derived from context_length fixture."""
    show_response = {
        "model_info": {"llama.context_length": 32768},
    }

    def _urlopen(*a, **kw):
        return _make_ollama_http_response(show_response)

    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)

    result = _suggest("qwen2.5:14b")
    assert isinstance(result, int)
    assert result == 32768 - 2048


def test_suggest_ollama_budget_failure_returns_none(monkeypatch):
    """suggest_ollama_budget returns None (not raises) on network failure."""
    def _raise(*a, **kw):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(_urllib_request, "urlopen", _raise)

    assert _suggest("any-model") is None


def test_suggest_budget_not_called_in_complete(monkeypatch):
    """complete() makes no /api/show call — suggest_ollama_budget is advisory only."""
    provider = OllamaProvider(model="qwen2.5:14b")
    provider._connectivity_checked = True

    show_called = [False]

    def _urlopen(url_or_req, *a, **kw):
        url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
        if "api/show" in url:
            show_called[0] = True
        body = {"response": json.dumps({"name": "x", "confidence": 0.5, "fact_ids": []})}
        return _make_ollama_http_response(body)

    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)

    provider.complete(_prompt(), _OllamaResult)
    assert show_called[0] is False


def test_llama_cpp_provider_ok_response_and_schema(monkeypatch):
    sent = {}

    def _urlopen(req, *a, **kw):
        sent.update(json.loads(req.data))
        content = json.dumps({"name": "hello", "confidence": 0.9, "fact_ids": []})
        return _make_ollama_http_response({"choices": [{"message": {"content": content}}]})

    provider = LlamaCppProvider(model="m")
    provider._connectivity_checked = True
    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)

    result = provider.complete(_prompt(), _OllamaResult)
    assert result.status == "ok" and result.value.name == "hello"
    assert sent["response_format"]["json_schema"]["schema"]["required"] == ["name", "confidence", "fact_ids"]
    assert provider.provider_id == "llama-cpp:m"


def test_llama_cpp_provider_http_error_is_llm_failed(monkeypatch):
    provider = LlamaCppProvider(model="m")
    provider._connectivity_checked = True

    def _boom(*a, **kw):
        raise _make_http_error(400, {})

    monkeypatch.setattr(_urllib_request, "urlopen", _boom)
    assert provider.complete(_prompt(), _OllamaResult).reason == "llm_failed"

