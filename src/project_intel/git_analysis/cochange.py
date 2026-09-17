"""Git co-change adapter: file pairs that change together above a threshold."""

from __future__ import annotations

import subprocess
from itertools import combinations
from pathlib import Path

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts.enums import EntityType, RelationType
from ..facts.model import EntityRef, Evidence, Fact
from ..facts.refs import CommitRef
from .window import AnalysisWindow

_NAME = "git-cochange"
_VERSION = "1.0.0"


def _is_commit_hash(s: str) -> bool:
    return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)


def _parse_name_only(output: str) -> list[tuple[str, list[str]]]:
    """Parse git log --name-only --format=%H output.

    Returns list of (commit_hash, [files_in_commit]).
    """
    commits: list[tuple[str, list[str]]] = []
    current_hash: str | None = None
    current_files: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_commit_hash(line):
            if current_hash is not None and current_files:
                commits.append((current_hash, current_files))
            current_hash = line
            current_files = []
        elif current_hash is not None:
            current_files.append(line)

    if current_hash is not None and current_files:
        commits.append((current_hash, current_files))

    return commits


def _git_prefix(target_path: Path) -> str:
    """Return the path prefix git uses relative to the repo root (e.g. 'backend/').

    Returns '' on any failure (non-existent path, not a git repo).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-prefix"],
            cwd=target_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except OSError:
        return ""


def _strip_prefix(path: str, prefix: str) -> str:
    return path[len(prefix):] if prefix and path.startswith(prefix) else path


def normalize_cochange(
    raw: str,
    ctx: AdapterContext,
    threshold: int = 2,
) -> list[Fact]:
    """Normalize git log --name-only output into git_co_change Facts."""
    analyzer = f"{_NAME}@{_VERSION}"
    commits = _parse_name_only(raw)
    prefix = _git_prefix(ctx.target_path)

    # Accumulate co-occurrence counts and evidence per pair (a < b alphabetically)
    pair_counts: dict[tuple[str, str], int] = {}
    pair_hashes: dict[tuple[str, str], list[str]] = {}

    for commit_hash, files in commits:
        unique_files = sorted({_strip_prefix(f, prefix) for f in files})
        for file_a, file_b in combinations(unique_files, 2):
            key = (file_a, file_b)  # already sorted by combinations over sorted list
            pair_counts[key] = pair_counts.get(key, 0) + 1
            hashes = pair_hashes.setdefault(key, [])
            if commit_hash not in hashes:
                hashes.append(commit_hash)

    facts: list[Fact] = []
    for (path_a, path_b), count in sorted(pair_counts.items()):
        if count < threshold:
            continue
        hashes = pair_hashes[(path_a, path_b)]
        evidence = tuple(
            Evidence(
                kind="commit",
                ref=CommitRef(repository_id=ctx.repository_id, commit_hash=h),
                source_analyzer=analyzer,
                retrieved_at=ctx.timestamp,
            )
            for h in hashes
        )
        facts.append(
            Fact(
                id=f"git_co_change:{ctx.repository_id}:{path_a}:{path_b}:{ctx.run_id}",
                type="git_co_change",
                subject=EntityRef(type=EntityType.FILE, id=path_a),
                predicate=RelationType.CHANGED_IN,
                object=EntityRef(type=EntityType.FILE, id=path_b),
                evidence=evidence,
                provenance="computed",
                confidence=1.0,
                source_analyzer=analyzer,
                created_at=ctx.timestamp,
                schema_version="1.0",
                run_id=ctx.run_id,
                value={"co_occurrences": count},
            )
        )

    return facts


def cochange_manifest(
    window: AnalysisWindow | None = None,
    include_merges: bool = False,
    threshold: int = 2,
) -> AdapterManifest:
    """Return an AdapterManifest for git co-change analysis."""
    _window = window or AnalysisWindow()

    def _command(ctx: AdapterContext) -> str:
        cmd = ["git", "log", "--name-only", "--format=%H"]
        if not include_merges:
            cmd.append("--no-merges")
        cmd.extend(_window.since_arg())
        cmd.append("--")
        result = subprocess.run(cmd, cwd=ctx.target_path, capture_output=True, text=True, check=True)
        return result.stdout

    def _normalize(raw: str, ctx: AdapterContext) -> list[Fact]:
        return normalize_cochange(raw, ctx, threshold=threshold)

    return AdapterManifest(
        name=_NAME,
        version=_VERSION,
        category="git",
        normalize=_normalize,
        command=_command,
        output_format="text",
    )
