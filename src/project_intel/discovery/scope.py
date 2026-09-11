"""ScopeConfig — filesystem walk filter for discovery."""

from __future__ import annotations

import dataclasses
import fnmatch
from pathlib import Path


@dataclasses.dataclass(frozen=True, slots=True)
class ScopeConfig:
    include_globs: tuple[str, ...] = ()  # empty = include all
    exclude_globs: tuple[str, ...] = ()
    max_depth: int | None = None


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def walk_files(root: Path, scope: ScopeConfig) -> list[str]:
    """Return repo-relative paths of all files that pass the scope filter."""
    results: list[str] = []
    _walk(root, root, scope, 0, results)
    return results


def _walk(root: Path, current: Path, scope: ScopeConfig, depth: int, out: list[str]) -> None:
    if scope.max_depth is not None and depth > scope.max_depth:
        return
    try:
        entries = list(current.iterdir())
    except PermissionError:
        return
    for entry in entries:
        rel = str(entry.relative_to(root))
        if scope.exclude_globs and _matches_any(rel, scope.exclude_globs):
            continue
        if entry.is_dir():
            _walk(root, entry, scope, depth + 1, out)
        elif entry.is_file():
            if scope.include_globs and not _matches_any(rel, scope.include_globs):
                continue
            out.append(rel)
