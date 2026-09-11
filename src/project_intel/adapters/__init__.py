"""Adapter framework — public API."""

from .manifest import AdapterContext, AdapterManifest
from .result import AdapterResult, AdapterStatus
from .runner import run_adapters
from .testing import assert_normalizes

__all__ = [
    "AdapterContext",
    "AdapterManifest",
    "AdapterResult",
    "AdapterStatus",
    "assert_normalizes",
    "run_adapters",
]
