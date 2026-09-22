"""Extension/language scope for the code-graph and complexity adapters.

Not a hand-picked "MVP" subset — Q193 originally hardcoded one (Python, TS/JS,
Go, Java/Kotlin, Ruby, Rust) and it silently drifted out of sync with what the
wrapped tools could actually do: graphify already ships a full PHP and Vue
extractor, lizard already has native PHP/Vue readers, yet both were filtered
out by an Atlas-side whitelist nobody had grown. The rule now: **trust the
wrapped tool's own capability instead of re-curating a subset of it**.

- code_graph/graphify_provider.py applies NO extension filter at all anymore —
  it trusts graphify's own file_type=="code" classification, which already
  covers everything in graphify's extractor dispatch table (Python, TS/JS, Go,
  Java/Kotlin, Ruby, Rust, PHP, Vue, Svelte, Astro, C/C++/C#, Swift, Scala,
  Lua, Zig, JSON, Terraform/HCL, SQL, Fortran, Pascal, ... — and correctly
  excludes Markdown, which graphify itself treats as docs, not code).
- LIZARD_EXTENSIONS below is lizard's own reader coverage, read off each
  bundled Reader class's `ext` attribute — extend here only when lizard ships
  a new reader, never by hand-picking a subset of what it already supports.
- MVP_LANGUAGES is a best-effort tokei-display-name view of that same
  coverage, used only by code_graph.metrics.compute_coverage_gap's advisory
  note. A language lizard/graphify actually support but missing from this
  list just makes that note undersell coverage slightly — it gates nothing.
"""

from __future__ import annotations

LIZARD_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
        ".java", ".cs", ".js", ".cjs", ".mjs", ".py", ".m", ".mm",
        ".rb", ".php", ".swift", ".scala", ".go", ".lua", ".rs", ".ts",
        ".kt", ".kts", ".sol", ".erl", ".hrl", ".zig", ".tsx", ".jsx",
        ".vue", ".pl", ".pm", ".r", ".sql",
    }
)

MVP_LANGUAGES: frozenset[str] = frozenset(
    {
        "Python", "TypeScript", "JavaScript", "TSX", "JSX", "Go", "Java",
        "Kotlin", "Ruby", "Rust", "PHP", "Vue", "C", "C++", "C Header",
        "C++ Header", "C#", "Objective-C", "Objective-C++", "Swift", "Scala",
        "Lua", "R", "SQL", "Solidity", "Erlang", "Zig", "Perl",
    }
)
