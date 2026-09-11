"""Discovery framework — public API."""

from .doc_enumerator import tag_documents
from .git_detector import GIT_MANIFEST
from .runner import DiscoveryResult, run_discovery
from .scope import ScopeConfig, walk_files
from .signatures import match_signatures
from .tokei_adapter import TOKEI_MANIFEST

__all__ = [
    "GIT_MANIFEST",
    "TOKEI_MANIFEST",
    "DiscoveryResult",
    "ScopeConfig",
    "match_signatures",
    "run_discovery",
    "tag_documents",
    "walk_files",
]
