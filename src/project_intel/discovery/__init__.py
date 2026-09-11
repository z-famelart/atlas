"""Discovery framework — public API."""

from .doc_enumerator import tag_documents
from .git_detector import GIT_MANIFEST
from .runner import DiscoveryResult, run_discovery
from .scope import ScopeConfig, walk_files
from .signatures import match_signatures

__all__ = [
    "GIT_MANIFEST",
    "DiscoveryResult",
    "ScopeConfig",
    "match_signatures",
    "run_discovery",
    "tag_documents",
    "walk_files",
]
