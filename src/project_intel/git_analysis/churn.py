"""Git churn adapter: commits + lines changed per file via git log --numstat."""

from __future__ import annotations

import subprocess

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts.enums import EntityType
from ..facts.model import EntityRef, Evidence, Fact
from ..facts.refs import CommitRef
from .window import AnalysisWindow

_NAME = "git-churn"
_VERSION = "1.0.0"


def _is_commit_hash(s: str) -> bool:
    return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)


def _parse_numstat(output: str) -> dict[str, tuple[int, list[str]]]:
    """Parse git log --numstat --format=%H output.

    Returns {path: (lines_changed, [unique_commit_hashes])}
    """
    file_lines: dict[str, int] = {}
    file_hashes: dict[str, list[str]] = {}
    current_hash: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_commit_hash(line):
            current_hash = line
        elif "\t" in line and current_hash is not None:
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            adds_str, dels_str, path = parts
            if adds_str == "-" or dels_str == "-":
                continue  # binary file
            try:
                delta = int(adds_str) + int(dels_str)
            except ValueError:
                continue
            file_lines[path] = file_lines.get(path, 0) + delta
            hashes = file_hashes.setdefault(path, [])
            if current_hash not in hashes:
                hashes.append(current_hash)

    return {path: (file_lines[path], file_hashes[path]) for path in file_lines}


def normalize_churn(raw: str, ctx: AdapterContext) -> list[Fact]:
    """Normalize git log --numstat output into git_churn Facts."""
    analyzer = f"{_NAME}@{_VERSION}"
    file_data = _parse_numstat(raw)
    facts: list[Fact] = []

    for path, (lines_changed, hashes) in sorted(file_data.items()):
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
                id=f"git_churn:{ctx.repository_id}:{path}:{ctx.run_id}",
                type="git_churn",
                subject=EntityRef(type=EntityType.FILE, id=path),
                evidence=evidence,
                provenance="computed",
                confidence=1.0,
                source_analyzer=analyzer,
                created_at=ctx.timestamp,
                schema_version="1.0",
                run_id=ctx.run_id,
                value={"commits": len(hashes), "lines_changed": lines_changed},
            )
        )

    return facts


def churn_manifest(
    window: AnalysisWindow | None = None,
    include_merges: bool = False,
) -> AdapterManifest:
    """Return an AdapterManifest for git churn analysis.

    Args:
        window: optional time window; None = full history.
        include_merges: if False (default), passes --no-merges to git log.
    """
    _window = window or AnalysisWindow()

    def _command(ctx: AdapterContext) -> str:
        cmd = ["git", "log", "--numstat", "--format=%H"]
        if not include_merges:
            cmd.append("--no-merges")
        cmd.extend(_window.since_arg())
        cmd.append("--")
        result = subprocess.run(cmd, cwd=ctx.target_path, capture_output=True, text=True, check=True)
        return result.stdout

    return AdapterManifest(
        name=_NAME,
        version=_VERSION,
        category="git",
        normalize=normalize_churn,
        command=_command,
        output_format="text",
    )
