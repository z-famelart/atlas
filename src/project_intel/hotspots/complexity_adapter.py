"""Concrete complexity adapter wrapping the lizard library — Feature 06 Part B."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts import SCHEMA_VERSION, EntityRef, EntityType, Evidence, Fact
from ..facts.refs import FileRef

_NAME = "lizard"
_VERSION = "1.0"
_ANALYZER = f"{_NAME}@{_VERSION}"


_MVP_EXTENSIONS: frozenset[str] = frozenset(
    [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".rb", ".rs", ".c", ".cpp", ".h"]
)

_SKIP_DIRS: frozenset[str] = frozenset(
    [".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
     ".mypy_cache", ".ruff_cache", ".pytest_cache", ".project-intel"]
)


def _lizard_command(ctx: AdapterContext) -> str:
    """Run lizard analysis on target_path and return a JSON string."""
    import lizard  # imported lazily so the adapter is importable even without lizard

    file_paths = [
        str(f)
        for f in ctx.target_path.rglob("*")
        if f.is_file()
        and f.suffix in _MVP_EXTENSIONS
        and not any(part in _SKIP_DIRS for part in f.parts)
    ]

    results = []
    for file_info in lizard.analyze_files(file_paths):
        rel = str(Path(file_info.filename).relative_to(ctx.target_path))
        results.append(
            {
                "filename": rel,
                "nloc": file_info.nloc,
                "average_cyclomatic_complexity": file_info.average_cyclomatic_complexity,
                "functions": [
                    {
                        "name": fn.name,
                        "cyclomatic_complexity": fn.cyclomatic_complexity,
                        "nloc": fn.nloc,
                    }
                    for fn in file_info.function_list
                ],
            }
        )
    return json.dumps(results)


def _normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
    data: list[dict] = json.loads(raw)
    facts: list[Fact] = []

    for entry in data:
        filename: str = entry["filename"]
        avg_cc: float = entry.get("average_cyclomatic_complexity") or 0.0
        if avg_cc == 0.0 and not entry.get("functions"):
            continue  # skip files with no analysable functions

        facts.append(
            Fact(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:complexity:{filename}")),
                type="complexity",
                subject=EntityRef(EntityType.FILE, filename),
                value={"score": avg_cc, "nloc": entry.get("nloc", 0)},
                provenance="observed",
                confidence=1.0,
                source_analyzer=_ANALYZER,
                evidence=(
                    Evidence(
                        kind="file",
                        ref=FileRef(repository_id=ctx.repository_id, path=filename),
                        source_analyzer=_ANALYZER,
                        retrieved_at=ctx.timestamp,
                    ),
                ),
                created_at=ctx.timestamp,
                schema_version=SCHEMA_VERSION,
                run_id=ctx.run_id,
            )
        )

    return facts


def lizard_manifest() -> AdapterManifest:
    return AdapterManifest(
        name=_NAME,
        version=_VERSION,
        category="complexity",
        command=_lizard_command,
        normalize=_normalize,
        supported_ecosystems=[
            "python", "typescript", "javascript", "go",
            "java", "kotlin", "ruby", "rust", "c", "cpp",
        ],
        install_hint="uv add lizard  # or: pip install lizard",
    )
