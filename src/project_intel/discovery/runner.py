"""Discovery pipeline: scope → signatures → git → docs → unrecognized."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..adapters.manifest import AdapterContext
from ..adapters.runner import _run_one
from ..facts import EntityRef, EntityType, Evidence, Fact, FileRef
from ..facts.store import SCHEMA_VERSION
from .doc_enumerator import tag_documents
from .git_detector import GIT_MANIFEST
from .scope import ScopeConfig, walk_files
from .signatures import match_signatures
from .tokei_adapter import TOKEI_MANIFEST

_RUNNER_NAME = "discovery.runner"
_RUNNER_VERSION = "1.0.0"


@dataclass
class DiscoveryResult:
    facts: list[Fact] = field(default_factory=list)
    matched_signatures: list[dict] = field(default_factory=list)
    tagged_documents: list[dict] = field(default_factory=list)
    unrecognized_paths: list[str] = field(default_factory=list)


def run_discovery(
    root: Path,
    repository_id: str,
    run_id: str,
    scope: ScopeConfig | None = None,
    timestamp: datetime | None = None,
) -> DiscoveryResult:
    """Run the full Part A discovery pipeline and return all produced Facts."""
    scope = scope or ScopeConfig()
    timestamp = timestamp or datetime.now(UTC)
    source = f"{_RUNNER_NAME}@{_RUNNER_VERSION}"

    ctx = AdapterContext(
        target_path=root,
        run_id=run_id,
        repository_id=repository_id,
        timestamp=timestamp,
    )

    # 1. Walk the filesystem through the scope filter.
    rel_paths = walk_files(root, scope)

    # 2. Match signatures.
    sigs = match_signatures(root, rel_paths)
    matched_paths = {s["matched_path"] for s in sigs}

    # 3. Tag documents.
    docs = tag_documents(rel_paths)
    doc_paths = {d["path"] for d in docs}

    # 4. Unrecognized: passes scope, matches nothing.
    recognized = matched_paths | doc_paths
    unrecognized = [p for p in rel_paths if p not in recognized]

    facts: list[Fact] = []

    # 5. Emit technology_detected facts for each signature match.
    for sig in sigs:
        ev = Evidence(
            kind="file",
            ref=FileRef(repository_id=repository_id, path=sig["matched_path"]),
            source_analyzer=source,
            retrieved_at=timestamp,
        )
        facts.append(Fact(
            id=str(uuid.uuid4()),
            type="technology_detected",
            subject=EntityRef(EntityType.REPOSITORY, repository_id),
            evidence=(ev,),
            provenance="observed",
            confidence=1.0,
            source_analyzer=source,
            created_at=timestamp,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            value={"category": sig["category"], "name": sig["name"]},
        ))

    # 6. Emit document_detected facts.
    for doc in docs:
        ev = Evidence(
            kind="file",
            ref=FileRef(repository_id=repository_id, path=doc["path"]),
            source_analyzer=source,
            retrieved_at=timestamp,
        )
        facts.append(Fact(
            id=str(uuid.uuid4()),
            type="document_detected",
            subject=EntityRef(EntityType.DOCUMENT, doc["path"]),
            evidence=(ev,),
            provenance="observed",
            confidence=1.0,
            source_analyzer=source,
            created_at=timestamp,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            value={"role": doc["role"]},
        ))

    # 7. Emit unrecognized_artifact facts.
    for rel in unrecognized:
        ev = Evidence(
            kind="file",
            ref=FileRef(repository_id=repository_id, path=rel),
            source_analyzer=source,
            retrieved_at=timestamp,
        )
        facts.append(Fact(
            id=str(uuid.uuid4()),
            type="unrecognized_artifact",
            subject=EntityRef(EntityType.FILE, rel),
            evidence=(ev,),
            provenance="observed",
            confidence=1.0,
            source_analyzer=source,
            created_at=timestamp,
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
        ))

    # 8. Git detection (callable adapter — run directly).
    git_output = GIT_MANIFEST.command(ctx)
    facts.extend(GIT_MANIFEST.normalize(git_output, ctx))

    # 9. Tokei language/LOC detection — via _run_one so a missing binary
    # degrades to skipped rather than failing discovery outright.
    tokei_result = _run_one(TOKEI_MANIFEST, ctx)
    facts.extend(tokei_result.facts)

    return DiscoveryResult(
        facts=facts,
        matched_signatures=sigs,
        tagged_documents=docs,
        unrecognized_paths=unrecognized,
    )
