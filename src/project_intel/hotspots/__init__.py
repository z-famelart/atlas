"""Hotspots package — public API."""

from .scorer import compute_hotspots
from .weights import HotspotWeights

__all__ = ["HotspotWeights", "compute_hotspots"]
