"""Git-presence adapter — detects whether a repository is tracked by git."""

from __future__ import annotations

import uuid

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts import EntityRef, EntityType, Evidence, Fact, FileRef
from ..facts.store import SCHEMA_VERSION

_NAME = "discovery.git"
_VERSION = "1.0.0"


def _normalize(output: str, ctx: AdapterContext) -> list[Fact]:
    """Produce a git_repository_detected Fact when git rev-parse --git-dir succeeds.

    output: the raw stdout from `git rev-parse --git-dir` (e.g. ".git\n").
    Empty or whitespace-only output means the command produced nothing — no fact.
    """
    git_dir = output.strip()
    if not git_dir:
        return []

    source = f"{_NAME}@{_VERSION}"
    evidence = Evidence(
        kind="file",
        ref=FileRef(repository_id=ctx.repository_id, path=git_dir),
        source_analyzer=source,
        retrieved_at=ctx.timestamp,
    )
    fact = Fact(
        id=str(uuid.uuid4()),
        type="git_repository_detected",
        subject=EntityRef(EntityType.REPOSITORY, ctx.repository_id),
        evidence=(evidence,),
        provenance="observed",
        confidence=1.0,
        source_analyzer=source,
        created_at=ctx.timestamp,
        schema_version=SCHEMA_VERSION,
        run_id=ctx.run_id,
        value={"git_dir": git_dir},
    )
    return [fact]


def _command(ctx: AdapterContext) -> str:
    """Run git rev-parse --git-dir; return stdout or empty string on failure."""
    import subprocess

    proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=ctx.target_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


GIT_MANIFEST = AdapterManifest(
    name=_NAME,
    version=_VERSION,
    category="git",
    normalize=_normalize,
    command=_command,
)
