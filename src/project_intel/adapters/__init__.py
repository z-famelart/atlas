"""Adapter framework — public API."""

from .language_scope import MVP_EXTENSIONS, MVP_LANGUAGES
from .manifest import AdapterContext, AdapterManifest
from .result import AdapterResult, AdapterStatus
from .runner import run_adapters
from .testing import assert_normalizes

__all__ = [
    "MVP_EXTENSIONS",
    "MVP_LANGUAGES",
    "AdapterContext",
    "AdapterManifest",
    "AdapterResult",
    "AdapterStatus",
    "assert_normalizes",
    "run_adapters",
]
