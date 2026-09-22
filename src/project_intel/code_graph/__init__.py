"""Code graph package — public API."""

from .aggregation import aggregate_to_module
from .graphify_provider import GraphifyProvider
from .metrics import compute_centrality, compute_coverage_gap, detect_communities, detect_cycles
from .provider import GraphProvider

__all__ = [
    "GraphProvider",
    "GraphifyProvider",
    "aggregate_to_module",
    "compute_centrality",
    "compute_coverage_gap",
    "detect_communities",
    "detect_cycles",
]
