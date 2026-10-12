"""Git Analysis — public API."""

from .churn import churn_manifest, normalize_churn
from .window import AnalysisWindow

__all__ = [
    "AnalysisWindow",
    "churn_manifest",
    "normalize_churn",
]
