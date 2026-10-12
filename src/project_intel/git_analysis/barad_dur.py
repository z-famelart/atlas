from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts.enums import EntityType, RelationType
from ..facts.model import EntityRef, Evidence, Fact
from ..facts.refs import ToolOutputRef
from .churn import _git_prefix

_NAME = "barad-dur"
_VERSION = "1.0.0"
_ANALYZER = f"{_NAME}@{_VERSION}"
_INSTALL_HINT = "cargo install barad-dur --locked"
_MAX_AUTHORS = 5


def _command(ctx: AdapterContext) -> str:
    binary = shutil.which("barad-dur")
    if binary is None:
        raise RuntimeError(f"barad-dur not found — {_INSTALL_HINT}")
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ctx.target_path, capture_output=True, text=True, check=True,
    ).stdout.strip()
    # Barad-dur writes its cache and edits .gitignore inside the analysed tree, so it gets a throwaway clone.
    with tempfile.TemporaryDirectory(prefix="atlas-barad-dur-") as tmp:
        clone = Path(tmp) / "repo"
        subprocess.run(["git", "clone", "-q", top, str(clone)], check=True, capture_output=True)
        proc = subprocess.run(
            [binary, "analyze", str(clone), "--all", "--json"],
            capture_output=True, text=True, timeout=600, check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"barad-dur exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def _fact(ctx: AdapterContext, fact_type: str, key: str, subject: str, value: dict, **kw) -> Fact:
    return Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:{fact_type}:{key}")),
        type=fact_type,
        subject=EntityRef(EntityType.FILE, subject),
        evidence=(
            Evidence(
                kind="tool_output",
                ref=ToolOutputRef(source_analyzer=_ANALYZER, raw_ref=f"{fact_type}:{key}"),
                source_analyzer=_ANALYZER,
                retrieved_at=ctx.timestamp,
            ),
        ),
        provenance="computed",
        confidence=1.0,
        source_analyzer=_ANALYZER,
        created_at=ctx.timestamp,
        schema_version="1.0",
        run_id=ctx.run_id,
        value=value,
        **kw,
    )


def normalize_barad_dur(raw: str, ctx: AdapterContext) -> list[Fact]:
    data = json.loads(raw)
    prefix = _git_prefix(ctx.target_path)

    def rel(path: str) -> str | None:
        if not prefix:
            return path
        return path[len(prefix):] if path.startswith(prefix) else None

    facts: list[Fact] = []
    for o in data.get("author_ownership", []):
        path = rel(o["path"])
        authors = sorted(o["authors"], key=lambda a: -a["pct"])[:_MAX_AUTHORS]
        if path is None or not authors:
            continue
        facts.append(_fact(ctx, "git_ownership", path, path, {
            "top_author": authors[0]["name"],
            "top_pct": authors[0]["pct"],
            "authors": [{"name": a["name"], "pct": a["pct"]} for a in authors],
        }))
    for h in data.get("file_hotspots", []):
        path = rel(h["path"])
        if path is not None:
            facts.append(_fact(ctx, "file_role", path, path, {"role": h["role"]}))
    for a in data.get("file_ages", []):
        path = rel(a["path"])
        if path is not None:
            facts.append(_fact(ctx, "file_age", path, path, {
                "days_since_modified": a["days_since_modified"],
                "last_modified": a["last_modified"],
            }))
    for p in data.get("coupling_pairs", []):
        a, b = rel(p["file_a"]), rel(p["file_b"])
        if a is None or b is None:
            continue
        facts.append(_fact(
            ctx, "git_coupling", f"{a}:{b}", a,
            {
                "co_changes": p["co_changes"],
                "coupling_pct": p["coupling_pct"],
                "is_test_pair": p["is_test_pair"],
                "cross_boundary": p["cross_boundary"],
            },
            predicate=RelationType.CHANGED_IN,
            object=EntityRef(EntityType.FILE, b),
        ))
    return facts


def barad_dur_manifest() -> AdapterManifest:
    return AdapterManifest(
        name=_NAME,
        version=_VERSION,
        category="git",
        normalize=normalize_barad_dur,
        command=_command,
        install_hint=_INSTALL_HINT,
    )
