"""LLM-stage robustness: run fallback, bounded prompts, retry, model-aware cache key."""

from __future__ import annotations

import dataclasses
import json
import urllib.request as _urllib_request
import uuid
from datetime import UTC, datetime
from pathlib import Path

from project_intel.facts.enums import EntityType
from project_intel.facts.model import EntityRef, Fact
from project_intel.facts.store import SCHEMA_VERSION, FactStore
from project_intel.llm.budget import BudgetTracker
from project_intel.llm.cache import LLMCache
from project_intel.llm.orchestrator import LLMOrchestrator
from project_intel.llm.prompt import bounded_json
from project_intel.llm.providers import OllamaProvider
from project_intel.llm.types import BudgetConfig, LLMCallResult, StructuredPrompt


def _fact(store: FactStore, run_id: str, type_: str, subject: str = "a.py") -> Fact:
    now = datetime.now(UTC)
    f = Fact(
        id=str(uuid.uuid4()), type=type_, subject=EntityRef(EntityType.FILE, subject),
        value={"combined": 0.5, "in_degree": 1}, provenance="observed", confidence=1.0,
        source_analyzer="test", evidence=(), created_at=now, schema_version=SCHEMA_VERSION, run_id=run_id,
    )
    store.insert_facts([f])
    return f


def test_run_id_with_falls_back_to_latest_run_holding_type(tmp_path: Path) -> None:
    store = FactStore(tmp_path / "f.sqlite")
    old, fresh = "run-old", "run-fresh"
    _fact(store, old, "hotspot_score")
    assert store.run_id_with("hotspot_score", fresh) == old  # `--only domain` case
    assert store.run_id_with("hotspot_score", old) == old
    assert store.run_id_with("centrality", fresh) is None
    store.close()


def test_bounded_json_keeps_priority_prefix() -> None:
    items = [{"id": str(i), "v": "x" * 50} for i in range(100)]
    out = json.loads(bounded_json(items, max_chars=500))
    assert 0 < len(out) < 100
    assert [d["id"] for d in out] == [str(i) for i in range(len(out))]
    assert json.loads(bounded_json(items, max_chars=10**6)) == items


@dataclasses.dataclass
class _R:
    label: str
    fact_ids: list[str]


def test_orchestrator_retries_once_on_llm_failed(tmp_path: Path) -> None:
    calls = []

    class _Flaky:
        provider_id = "flaky"
        def complete(self, prompt, schema):
            calls.append(1)
            if len(calls) == 1:
                return LLMCallResult(status="not_analyzed", reason="llm_failed")
            return LLMCallResult(status="ok", value=_R(label="x", fact_ids=[]))

    orch = LLMOrchestrator(_Flaky(), FactStore(tmp_path / "f.sqlite"), LLMCache(tmp_path / "c.sqlite"),
                           BudgetTracker(BudgetConfig.unlimited()))
    result = orch.complete(StructuredPrompt("i", "c", "v1", "test"), _R)
    assert result.status == "ok" and len(calls) == 2


def test_ollama_cache_key_and_num_ctx_follow_model_and_prompt(monkeypatch) -> None:
    assert OllamaProvider(model="a").provider_id != OllamaProvider(model="b").provider_id
    seen = {}

    def _urlopen(req, *a, **kw):
        seen.update(json.loads(req.data))
        class _Resp:
            def read(self): return json.dumps({"response": json.dumps({"label": "x", "fact_ids": []})}).encode()
            def __enter__(self): return self
            def __exit__(self, *_): pass
        return _Resp()

    monkeypatch.setattr(_urllib_request, "urlopen", _urlopen)
    p = OllamaProvider(model="m")
    p._connectivity_checked = True
    assert p.complete(StructuredPrompt("i", "x" * 80_000, "v1", "test"), _R).status == "ok"
    assert seen["options"]["num_ctx"] >= 20_000 + 4_096


def test_orchestrator_maps_aliases_back_to_real_ids(tmp_path: Path) -> None:
    store = FactStore(tmp_path / "f.sqlite")
    real = _fact(store, "r", "centrality")

    class _P:
        provider_id = "alias"
        def complete(self, prompt, schema):
            return LLMCallResult(status="ok", value=_R(label="x", fact_ids=["f1"]))

    orch = LLMOrchestrator(_P(), store, LLMCache(tmp_path / "c.sqlite"), BudgetTracker(BudgetConfig.unlimited()))
    result = orch.complete(StructuredPrompt("i", "c", "v1", "test", id_map={"f1": real.id}), _R)
    assert result.status == "ok" and result.value.fact_ids == [real.id]
    store.close()


def test_enum_metadata_reaches_json_schema() -> None:
    from project_intel.architecture.schema import _CATALOGUE, ArchitectureResponse
    from project_intel.llm.providers import _dataclass_json_schema
    hyp = _dataclass_json_schema(ArchitectureResponse)["properties"]["hypotheses"]["items"]
    assert hyp["properties"]["pattern"]["enum"] == _CATALOGUE
    assert hyp["properties"]["pattern_description"]["type"] == "string"
