"""Bounded prompt content — keeps synthesis prompts inside a local model's context window.

Ollama silently truncates a prompt longer than num_ctx by dropping its *beginning* — the
instructions and the schema — which is exactly how "empty hypotheses" and invented fact ids
happen. Callers pass facts in priority order; we keep a prefix that fits.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

# ponytail: ~24k tokens at 4 chars/token; fits a 32k-context local model with room for
# instructions, schema and output. Raise when a provider exposes its real window.
MAX_CONTENT_CHARS = 96_000


def bounded_json(items: list[dict[str, Any]], max_chars: int = MAX_CONTENT_CHARS, *, label: str = "") -> str:
    """JSON-encode a prefix of `items` (priority order) whose encoded size stays under max_chars."""
    kept: list[str] = []
    size = 2  # brackets
    for item in items:
        enc = json.dumps(item, default=str)
        if size + len(enc) + 1 > max_chars:
            break
        kept.append(enc)
        size += len(enc) + 1
    if len(kept) < len(items):
        _log.warning("%s prompt: kept %d/%d facts to stay under %d chars",
                     label or "LLM", len(kept), len(items), max_chars)
    return "[" + ",".join(kept) + "]"


def alias_ids(items: list[dict[str, Any]], key: str = "id") -> dict[str, str]:
    """Replace each item[key] with a short alias ("f1", "f2", …) in place; return alias → real id.

    Local models mangle 36-char UUIDs when copying them into fact_ids; short aliases are
    copied reliably and mapped back by the orchestrator before citation validation.
    """
    id_map: dict[str, str] = {}
    for n, item in enumerate(items, 1):
        real = item.get(key)
        if real:
            alias = f"f{n}"
            id_map[alias] = str(real)
            item[key] = alias
    return id_map
