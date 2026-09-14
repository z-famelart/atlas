"""LLMProvider protocol + ClaudeCodeProvider + DisabledProvider — Feature 07."""

from __future__ import annotations

import dataclasses
import json
import subprocess
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


class DisabledProvider:
    """No-op provider — always returns not_analyzed: llm_failed (Décidé Q95).

    Downstream features handle this the same way as any provider failure,
    so they need no separate disabled-mode code path.
    """

    provider_id = "disabled"

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        return LLMCallResult(status="not_analyzed", reason="llm_failed")
