"""LLMProvider protocol + ClaudeCodeProvider + OllamaProvider + DisabledProvider."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import urllib.error
import urllib.request
from typing import Any, Protocol, TypeVar

import cattrs

from .types import LLMCallResult, StructuredPrompt

T = TypeVar("T")

_CONVERTER = cattrs.Converter()


def _schema_description(schema: type) -> str:
    """Generate a minimal field description from a dataclass for use in prompts."""
    if not dataclasses.is_dataclass(schema):
        return schema.__name__
    fields = dataclasses.fields(schema)  # type: ignore[arg-type]
    lines = ["Return a JSON object with these fields:"]
    for f in fields:
        lines.append(f"  - {f.name}: {f.type}")
    return "\n".join(lines)


class LLMProvider(Protocol):
    """Raw LLM provider — wrap with LLMOrchestrator for caching/budget/citations."""

    provider_id: str

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        ...


class ClaudeCodeProvider:
    """Shells out to the `claude` CLI in non-interactive print mode."""

    provider_id = "claude-code"

    def __init__(self, model: str = "claude-haiku-4-5-20251001", timeout: int = 120) -> None:
        self._model = model
        self._timeout = timeout

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        schema_desc = _schema_description(schema)
        full_prompt = (
            f"{prompt.instructions}\n\n"
            f"<content>\n{prompt.content}\n</content>\n\n"
            f"{schema_desc}\n"
            "Respond with only valid JSON, no markdown, no explanation."
        )
        cmd = ["claude", "-p", "--output-format", "json", "--model", self._model]
        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
            if proc.returncode != 0:
                return LLMCallResult(status="not_analyzed", reason="llm_failed")

            envelope = json.loads(proc.stdout)
            if envelope.get("is_error"):
                return LLMCallResult(status="not_analyzed", reason="llm_failed")

            raw_text: str = envelope.get("result", "")
            payload = json.loads(raw_text)
            value = _CONVERTER.structure(payload, schema)
            return LLMCallResult(status="ok", value=value)
        except Exception:  # noqa: BLE001
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


def suggest_ollama_budget(model: str, base_url: str = "http://localhost:11434") -> int | None:
    """Return a conservative token budget from Ollama's /api/show, or None on failure."""
    try:
        req = urllib.request.Request(
            f"{base_url}/api/show",
            data=json.dumps({"model": model}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read())
        ctx = info.get("model_info", {}).get("llama.context_length") or info.get("context_length")
        if ctx:
            return max(1, int(ctx) - 2048)  # ponytail: leave 2048 tokens for prompt+output
        return None
    except Exception:  # noqa: BLE001
        return None


class OllamaProvider:
    """HTTP provider for a local Ollama server."""

    provider_id = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: int = 120) -> None:
        if not model:
            raise TypeError(
                "OllamaProvider requires a model name — "
                "set OLLAMA_MODEL (e.g. qwen2.5:14b) or run with --no-llm."
            )
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._connectivity_checked = False

    def _check_connectivity(self) -> str | None:
        """Ping /api/tags once; return an error message string or None if reachable."""
        if self._connectivity_checked:
            return None
        self._connectivity_checked = True
        try:
            urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=5)
            return None
        except (urllib.error.URLError, OSError):
            return (
                f"Could not reach Ollama at {self._base_url} — is it running? "
                "(ollama serve). Falling back to --no-llm behavior for this run."
            )

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        conn_error = self._check_connectivity()
        if conn_error:
            print(conn_error)

        schema_desc = _schema_description(schema)
        full_prompt = (
            f"{prompt.instructions}\n\n"
            f"<content>\n{prompt.content}\n</content>\n\n"
            f"{schema_desc}\n"
            "Respond with only valid JSON, no markdown, no explanation."
        )
        payload = json.dumps({
            "model": self._model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
        }).encode()
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read())
            raw_text: str = body.get("response", "")
            parsed = json.loads(raw_text)
            value = _CONVERTER.structure(parsed, schema)
            return LLMCallResult(status="ok", value=value)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                try:
                    err_body = json.loads(e.read())
                except Exception:  # noqa: BLE001
                    err_body = {}
                if "not found" in err_body.get("error", "").lower():
                    print(f"Model '{self._model}' not found in Ollama — run: ollama pull {self._model}.")
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except Exception:  # noqa: BLE001
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


class DisabledProvider:
    """No-op provider — always returns not_analyzed: llm_failed (Décidé Q95).

    Downstream features handle this the same way as any provider failure,
    so they need no separate disabled-mode code path.
    """

    provider_id = "disabled"

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        return LLMCallResult(status="not_analyzed", reason="llm_failed")
