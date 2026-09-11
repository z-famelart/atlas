"""Concrete GraphProvider wrapping the graphify CLI."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts import (
    SCHEMA_VERSION,
    EntityRef,
    EntityType,
    Evidence,
    Fact,
    FileRef,
    RelationType,
    SymbolRef,
)

_MVP_EXTENSIONS: frozenset[str] = frozenset(
    [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".rb", ".rs"]
)


def _is_mvp_file(path: str) -> bool:
    return Path(path).suffix in _MVP_EXTENSIONS


class GraphifyProvider:
    """Concrete GraphProvider wrapping the graphify CLI."""

    NAME = "graphify"
    VERSION = "1.0"

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            name=self.NAME,
            version=self.VERSION,
            category="code_graph",
            command=[self.NAME, "--format", "json", "{target_path}"],
            min_version="0.1.0",
            normalize=self._normalize,
            install_hint="pip install graphify  # or: cargo install graphify",
            supported_ecosystems=[
                "python", "typescript", "javascript", "go",
                "java", "kotlin", "ruby", "rust",
            ],
        )

    def _normalize(self, raw: str, ctx: AdapterContext) -> list[Fact]:
        data = json.loads(raw)
        analyzer = f"{self.NAME}@{self.VERSION}"
        facts: list[Fact] = []

        for node in data.get("nodes", []):
            if not _is_mvp_file(node["file"]):
                continue
            facts.append(
                Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:symbol:{node['id']}")),
                    type="symbol_defined",
                    subject=EntityRef(EntityType.SYMBOL, node["id"]),
                    value={"name": node["name"], "kind": node["kind"]},
                    provenance="observed",
                    confidence=1.0,
                    source_analyzer=analyzer,
                    evidence=(
                        Evidence(
                            kind="symbol",
                            ref=SymbolRef(
                                repository_id=ctx.repository_id,
                                path=node["file"],
                                symbol_id=node["id"],
                            ),
                            source_analyzer=analyzer,
                            retrieved_at=ctx.timestamp,
                        ),
                    ),
                    created_at=ctx.timestamp,
                    schema_version=SCHEMA_VERSION,
                    run_id=ctx.run_id,
                )
            )

        for edge in data.get("edges", []):
            kind = edge["kind"]
            src, tgt = edge["source"], edge["target"]

            if kind == "imports":
                if not (_is_mvp_file(src) and _is_mvp_file(tgt)):
                    continue
                facts.append(
                    Fact(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:imports:{src}:{tgt}")),
                        type="relation",
                        subject=EntityRef(EntityType.FILE, src),
                        predicate=RelationType.IMPORTS,
                        object=EntityRef(EntityType.FILE, tgt),
                        provenance="observed",
                        confidence=1.0,
                        source_analyzer=analyzer,
                        evidence=(
                            Evidence(
                                kind="file",
                                ref=FileRef(repository_id=ctx.repository_id, path=src),
                                source_analyzer=analyzer,
                                retrieved_at=ctx.timestamp,
                            ),
                        ),
                        created_at=ctx.timestamp,
                        schema_version=SCHEMA_VERSION,
                        run_id=ctx.run_id,
                    )
                )
            elif kind == "calls":
                src_file = src.split("::")[0] if "::" in src else src
                tgt_file = tgt.split("::")[0] if "::" in tgt else tgt
                if not (_is_mvp_file(src_file) and _is_mvp_file(tgt_file)):
                    continue
                facts.append(
                    Fact(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:calls:{src}:{tgt}")),
                        type="relation",
                        subject=EntityRef(EntityType.SYMBOL, src),
                        predicate=RelationType.CALLS,
                        object=EntityRef(EntityType.SYMBOL, tgt),
                        provenance="observed",
                        confidence=1.0,
                        source_analyzer=analyzer,
                        evidence=(
                            Evidence(
                                kind="symbol",
                                ref=SymbolRef(
                                    repository_id=ctx.repository_id,
                                    path=src_file,
                                    symbol_id=src,
                                ),
                                source_analyzer=analyzer,
                                retrieved_at=ctx.timestamp,
                            ),
                        ),
                        created_at=ctx.timestamp,
                        schema_version=SCHEMA_VERSION,
                        run_id=ctx.run_id,
                    )
                )

        return facts
