"""Collect synthesis facts and build the LLM prompt — Feature 10."""

from __future__ import annotations

from ..facts.model import Fact
from ..facts.store import FactStore
from ..llm.prompt import alias_ids, bounded_json
from ..llm.types import StructuredPrompt

# Priority order: what survives when the prompt is capped (see llm/prompt.py).
_INPUT_FACT_TYPES = (
    "architecture_hypothesis",
    "business_workflow",
    "business_concept",
    "centrality",
    "hotspot_score",
    "symbol_defined",
)
_RANK_KEY = {  # within a type, most important first
    "centrality": lambda f: -float((f.value or {}).get("in_degree", 0)),
    "hotspot_score": lambda f: -float((f.value or {}).get("combined", 0)),
}

_INSTRUCTIONS = """\
You are synthesizing an onboarding path for a software engineer joining this codebase.
Based on the provided facts (graph centrality, hotspots, architecture hypotheses, business workflows/concepts),
recommend where to start, what workflow to follow, what to avoid initially, and what can be understood in 30 min vs 2 hours.

Rules:
- entry_points: 2-5 most important components to read first (prefer high-centrality, low-hotspot-score components).
- recommended_workflow: reuse a business_workflow fact description where one exists; otherwise synthesize from available facts.
- avoid_initially: components that are high-complexity or low-centrality and irrelevant to a first pass.
- time_boxed_understanding: concrete suggestions for 30-minute and 2-hour reading sessions.
- open_questions: explicit unresolved items — things you cannot determine from the available facts.
- confidence: float in [0.0, 1.0] reflecting how complete the input evidence is.
- fact_ids: top-level citations — ids from the provided facts that most influenced this path.
- All fact_ids fields must only contain ids from the provided facts — do not invent ids.
- If evidence is sparse, lower confidence and list gaps in open_questions rather than guessing.
- Any claim about a specific named component (an entry_points or avoid_initially item) must cite,
  in that item's own fact_ids, the specific fact(s) that support that exact claim — not just any
  fact from the input set. Do not assert that a capability or feature is absent, unconfigured, or
  not implemented unless the provided facts positively support that absence; if you cannot point to
  a fact that supports it, leave the claim out rather than guessing.
"""


def collect_input_facts(store: FactStore, run_id: str | None = None) -> list[Fact]:
    """Return synthesis-input facts from Features 05/06/08/09, each type from its latest run."""
    facts: list[Fact] = []
    for fact_type in _INPUT_FACT_TYPES:
        rid = store.run_id_with(fact_type, run_id)
        batch = list(store.query_facts(type=fact_type, run_id=rid))
        if fact_type in _RANK_KEY:
            batch.sort(key=_RANK_KEY[fact_type])
        facts.extend(batch)
    return facts


def _fact_summary(fact: Fact) -> dict:
    return {
        "id": fact.id,
        "type": fact.type,
        "subject": fact.subject.id,
        "value": fact.value,
    }


def build_prompt(facts: list[Fact]) -> StructuredPrompt:
    summaries = [_fact_summary(f) for f in facts]
    id_map = alias_ids(summaries)
    content = bounded_json(summaries, label="onboarding")
    return StructuredPrompt(
        instructions=_INSTRUCTIONS,
        content=content,
        schema_version="onboarding@1.0",
        category="onboarding",
        estimated_input_tokens=len(content) // 4,
        id_map=id_map,
    )
