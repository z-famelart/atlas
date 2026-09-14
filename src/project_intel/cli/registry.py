"""Stage registry — explicit ordered list of analysis stages."""

from __future__ import annotations

from ..architecture.stage import STAGE as architecture_stage
from ..code_graph.stage import STAGE as code_graph_stage
from ..discovery.stage import STAGE as discovery_stage
from ..git_analysis.stage import STAGE as git_stage
from ..hotspots.stage import STAGE as hotspots_stage
from .types import Stage

STAGE_REGISTRY: list[Stage] = [
    discovery_stage,
    git_stage,
    code_graph_stage,
    hotspots_stage,
    architecture_stage,
]
