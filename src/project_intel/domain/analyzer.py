"""Build the LLM prompt for domain understanding — Feature 09."""

from __future__ import annotations

import json

from ..llm.types import StructuredPrompt
from .selector import CandidateContent

_INSTRUCTIONS = """\
You are analyzing a software repository to identify its business domain.
Based on the provided file contents (selected as the most structurally significant files),
identify the business concepts, workflows, and glossary terms present in this codebase.

Rules:
- fact_ids must only contain ids from the provided candidate facts — do not invent ids.
- Each concept, workflow, and glossary entry must cite at least one fact_id.
- Return empty lists when no evidence supports a category.
- Concepts are named domain entities (e.g. "Order", "User", "Invoice").
- Workflows are named processes or sequences of steps (e.g. "checkout flow", "user registration").
- Glossary terms are domain-specific words with precise meanings in this codebase.
"""


def build_prompt(candidates: list[CandidateContent]) -> StructuredPrompt:
    entries = [
        {
            "fact_id": c.source_fact_ids[0] if c.source_fact_ids else "",
            "path": c.path,
            "content": c.content[:4000],  # cap per-file to avoid ballooning
        }
        for c in candidates
    ]
    content = json.dumps(entries, default=str)
    return StructuredPrompt(
        instructions=_INSTRUCTIONS,
        content=content,
        schema_version="domain@1.0",
        category="domain",
        estimated_input_tokens=len(content) // 4,
    )
