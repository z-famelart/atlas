"""LLMProvider protocol + ClaudeCodeProvider + OllamaProvider + DisabledProvider."""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
import types
import typing
import urllib.error
import urllib.request
from typing import Any, Protocol, TypeVar

import cattrs

from .types import LLMCallResult, StructuredPrompt

T = TypeVar("T")

_CONVERTER = cattrs.Converter()
_log = logging.getLogger(__name__)


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

    def __init__(self, model: str = "claude-haiku-4-5-20251001", timeout: int = 120) -> None:
        self.provider_id = f"claude-code:{model}"  # model is part of the cache key
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


def _type_to_schema(tp: Any) -> dict:
    origin = getattr(tp, "__origin__", None)
    if origin is list:
        args = getattr(tp, "__args__", (object,))
        return {"type": "array", "items": _type_to_schema(args[0])}
    if origin is typing.Union or isinstance(tp, types.UnionType):
        non_none = [a for a in tp.__args__ if a is not type(None)]
        return _type_to_schema(non_none[0]) if non_none else {}
    if dataclasses.is_dataclass(tp):
        return _dataclass_json_schema(tp)
    return {"type": {str: "string", float: "number", int: "integer", bool: "boolean"}.get(tp, "string")}


def _dataclass_json_schema(schema: type) -> dict:
    """Build a JSON Schema object from a dataclass — passed to Ollama's format field."""
    if not dataclasses.is_dataclass(schema):
        return {"type": "object"}
    try:
        hints = typing.get_type_hints(schema)
    except Exception:  # noqa: BLE001
        hints = {f.name: f.type for f in dataclasses.fields(schema)}  # type: ignore[misc]
    props = {}
    required = []
    for f in dataclasses.fields(schema):  # type: ignore[arg-type]
        props[f.name] = _type_to_schema(hints.get(f.name, str))
        if "enum" in f.metadata:  # closed vocabulary → constrained decoding, model cannot stray
            props[f.name]["enum"] = list(f.metadata["enum"])
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:  # type: ignore[misc]
            required.append(f.name)
    result: dict = {"type": "object", "properties": props}
    if required:
        result["required"] = required
    return result


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

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: int = 600) -> None:
        if not model:
            raise TypeError(
                "OllamaProvider requires a model name — "
                "set OLLAMA_MODEL (e.g. qwen2.5:14b) or run with --no-llm."
            )
        self.provider_id = f"ollama:{model}"  # model is part of the cache key
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
        fmt = _dataclass_json_schema(schema) if dataclasses.is_dataclass(schema) else "json"
        # Ollama's default num_ctx (4096) silently drops the *start* of a longer prompt —
        # the instructions and the schema. Size the window to the prompt instead.
        est_tokens = len(full_prompt) // 4
        num_ctx = min(65_536, max(8_192, -(-(est_tokens + 4_096) // 1_024) * 1_024))
        payload = json.dumps({
            "model": self._model,
            "prompt": full_prompt,
            "format": fmt,
            "stream": False,
            "options": {"num_ctx": num_ctx},
        }).encode()
        _log.info("Ollama call model=%s prompt_chars=%d num_ctx=%d", self._model, len(full_prompt), num_ctx)
        raw_text = ""
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
            _log.warning("Ollama HTTP %s model=%s: %s", e.code, self._model, e.reason)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except (json.JSONDecodeError, cattrs.errors.ClassValidationError) as e:
            _log.warning("Ollama response rejected model=%s schema=%s: %s\nresponse head: %.400s",
                         self._model, schema.__name__, e, raw_text)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except Exception as e:  # noqa: BLE001
            _log.warning("Ollama call failed model=%s: %s: %s", self._model, type(e).__name__, e)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


def _llama_cpp_get(base_url: str, path: str, timeout: int = 5) -> Any:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as resp:
        return json.loads(resp.read())


def suggest_llama_cpp_budget(base_url: str = "http://localhost:8080") -> int | None:
    """Return a conservative token budget from llama-server's /props, or None on failure."""
    try:
        ctx = _llama_cpp_get(base_url.rstrip("/"), "/props")["default_generation_settings"]["n_ctx"]
        return max(1, int(ctx) - 2048)  # ponytail: leave 2048 tokens for prompt+output
    except Exception:  # noqa: BLE001
        return None


class LlamaCppProvider:
    """HTTP provider for a local llama.cpp `llama-server` (OpenAI-compatible API).

    The loaded model and its context size are fixed at server launch (`-m`, `-c`),
    so `model` is optional and only labels the request.
    """

    def __init__(self, model: str | None = None, base_url: str = "http://localhost:8080", timeout: int = 600) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._connectivity_checked = False
        if not model:  # the cache key must change when a different model is loaded
            try:
                model = _llama_cpp_get(self._base_url, "/v1/models")["data"][0]["id"]
            except Exception:  # noqa: BLE001
                model = "default"
        self._model = model
        self.provider_id = f"llama-cpp:{model}"

    def _check_connectivity(self) -> str | None:
        if self._connectivity_checked:
            return None
        self._connectivity_checked = True
        try:
            _llama_cpp_get(self._base_url, "/health")
            return None
        except (urllib.error.URLError, OSError):
            return (
                f"Could not reach llama-server at {self._base_url} — is it running? "
                "(llama-server -m <model.gguf> -c <ctx>). Falling back to --no-llm behavior for this run."
            )

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        conn_error = self._check_connectivity()
        if conn_error:
            print(conn_error)

        full_prompt = (
            f"{prompt.instructions}\n\n"
            f"<content>\n{prompt.content}\n</content>\n\n"
            f"{_schema_description(schema)}\n"
            "Respond with only valid JSON, no markdown, no explanation."
        )
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": full_prompt}],
            "stream": False,
            "temperature": 0,
        }
        if dataclasses.is_dataclass(schema):
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": _dataclass_json_schema(schema)},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        _log.info("llama.cpp call model=%s prompt_chars=%d", self._model, len(full_prompt))
        raw_text = ""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                envelope = json.loads(resp.read())
            raw_text = envelope["choices"][0]["message"]["content"]
            value = _CONVERTER.structure(json.loads(raw_text), schema)
            return LLMCallResult(status="ok", value=value)
        except urllib.error.HTTPError as e:
            _log.warning("llama.cpp HTTP %s model=%s: %s (prompt may exceed the server's -c context)",
                         e.code, self._model, e.reason)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except (json.JSONDecodeError, cattrs.errors.ClassValidationError) as e:
            _log.warning("llama.cpp response rejected model=%s schema=%s: %s\nresponse head: %.400s",
                         self._model, schema.__name__, e, raw_text)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except Exception as e:  # noqa: BLE001
            _log.warning("llama.cpp call failed model=%s: %s: %s", self._model, type(e).__name__, e)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


def _full_prompt(prompt: StructuredPrompt, schema: type[Any]) -> str:
    return (
        f"{prompt.instructions}\n\n"
        f"<content>\n{prompt.content}\n</content>\n\n"
        f"{_schema_description(schema)}\n"
        "Respond with only valid JSON, no markdown, no explanation."
    )


def _loads_unfenced(text: str) -> Any:
    """Hosted models often wrap JSON in ```json fences despite being told not to."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


class GeminiCliProvider:
    """Shells out to a Google agent CLI in headless mode: `agy` (Antigravity) or `gemini` (Gemini CLI).

    Both take the whole prompt as the `-p` argument. `agy` ignores stdin in print mode,
    so the prompt cannot go through stdin (ceiling: the OS argv limit, ~1 MB on macOS).
    """

    def __init__(self, model: str | None = None, binary: str = "agy", timeout: int = 180) -> None:
        self.provider_id = f"{binary}:{model or 'default'}"
        self._binary = binary
        self._model = model
        self._timeout = timeout

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        cmd = [self._binary, "-p", _full_prompt(prompt, schema) + "\nDo not use any tools."]
        if self._model:
            cmd += ["--model", self._model]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout, check=False
            )
            if proc.returncode != 0:
                _log.warning("%s exited %s: %.400s", self._binary, proc.returncode, proc.stderr)
                return LLMCallResult(status="not_analyzed", reason="llm_failed")
            value = _CONVERTER.structure(_loads_unfenced(proc.stdout), schema)
            return LLMCallResult(status="ok", value=value)
        except Exception as e:  # noqa: BLE001
            _log.warning("%s call failed: %s: %s", self._binary, type(e).__name__, e)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


class OpenAICompatProvider:
    """Any OpenAI-compatible `/chat/completions` endpoint (Gemini API, OpenAI, LM Studio, vLLM…).

    `base_url` includes the version prefix, e.g. https://api.openai.com/v1 or
    https://generativelanguage.googleapis.com/v1beta/openai.
    """

    def __init__(self, model: str, base_url: str, api_key: str | None = None, timeout: int = 600) -> None:
        if not model or not base_url:
            raise TypeError("OpenAICompatProvider requires both a model and a base URL.")
        self.provider_id = f"openai-compat:{model}"
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        # json_object (not json_schema): the widest support across compatible servers.
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": _full_prompt(prompt, schema)}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        raw_text = ""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw_text = json.loads(resp.read())["choices"][0]["message"]["content"]
            value = _CONVERTER.structure(_loads_unfenced(raw_text), schema)
            return LLMCallResult(status="ok", value=value)
        except urllib.error.HTTPError as e:
            _log.warning("OpenAI-compat HTTP %s model=%s: %s (check URL, key and model name)",
                         e.code, self._model, e.reason)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except (json.JSONDecodeError, cattrs.errors.ClassValidationError) as e:
            _log.warning("OpenAI-compat response rejected model=%s schema=%s: %s\nresponse head: %.400s",
                         self._model, schema.__name__, e, raw_text)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")
        except Exception as e:  # noqa: BLE001
            _log.warning("OpenAI-compat call failed model=%s: %s: %s", self._model, type(e).__name__, e)
            return LLMCallResult(status="not_analyzed", reason="llm_failed")


class DisabledProvider:
    """No-op provider — always returns not_analyzed: llm_disabled (Décidé Q95).

    Downstream features handle this the same way as any provider failure,
    so they need no separate disabled-mode code path, but the reason is
    distinguishable from a genuine provider failure (Feature 07c).
    """

    provider_id = "disabled"

    def complete(self, prompt: StructuredPrompt, schema: type[Any]) -> LLMCallResult[Any]:
        return LLMCallResult(status="not_analyzed", reason="llm_disabled")
