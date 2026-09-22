"""Single source of truth for the MVP code-graph/complexity language scope.

Per Décidé Q193 (Design Decisions.md, resolved via Feature 02b): the languages
whose files get symbol/relation extraction (code graph) and complexity scoring.
Previously duplicated independently in graphify_provider.py and
complexity_adapter.py — extend *here* when Q193 changes, not per-adapter.

This does NOT gate language *detection* (tokei/discovery) — that stage reports
every language found, MVP or not, precisely so code_graph.metrics.compute_coverage_gap
can tell you what's outside this scope instead of silently dropping it.
"""

from __future__ import annotations

MVP_LANGUAGES: frozenset[str] = frozenset(
    {"Python", "TypeScript", "JavaScript", "Go", "Java", "Kotlin", "Ruby", "Rust", "PHP"}
)

MVP_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".rb", ".rs", ".php"}
)
