"""Concrete GraphProvider wrapping the graphify CLI."""

from __future__ import annotations

import json
import subprocess
import uuid

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

# graphify link relations → our RelationType; others are skipped
_RELATION_MAP: dict[str, RelationType] = {
    "calls": RelationType.CALLS,
    "imports": RelationType.IMPORTS,
    "imports_from": RelationType.IMPORTS,
    "inherits": RelationType.INHERITS_FROM,
}


def _graphify_command(ctx: AdapterContext) -> str:
    """Run `graphify update <path>` and return the resulting graph.json content."""
    subprocess.run(
        ["graphify", "update", str(ctx.target_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    graph_path = ctx.target_path / "graphify-out" / "graph.json"
    return graph_path.read_text()


class GraphifyProvider:
    """Concrete GraphProvider wrapping the graphify CLI."""

    NAME = "graphify"
    VERSION = "1.0"

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            name=self.NAME,
            version=self.VERSION,
            category="code_graph",
            command=_graphify_command,
            normalize=self._normalize,
            install_hint="uv tool install graphifyy  # PyPI package name has two y's",
            # Not an Atlas-curated subset — graphify classifies file_type=="code"
            # for its whole extractor dispatch table; this list is illustrative
            # of that table, not a gate (see language_scope.py).
            supported_ecosystems=[
                "python", "typescript", "javascript", "go", "java", "kotlin",
                "ruby", "rust", "php", "vue", "svelte", "astro", "c", "cpp",
                "csharp", "swift", "scala", "lua", "zig",
            ],
        )

    def _normalize(self, raw: str, ctx: AdapterContext) -> list[Fact]:
        data = json.loads(raw)
        analyzer = f"{self.NAME}@{self.VERSION}"

        # Build slug → node lookup for source_file resolution
        nodes_by_id: dict[str, dict] = {n["id"]: n for n in data.get("nodes", [])}

        facts: list[Fact] = []

        # --- symbol_defined facts (callable nodes in files graphify itself
        # classifies as code — trust graphify's own scope, don't re-narrow it) ---
        for node in nodes_by_id.values():
            if node.get("file_type") != "code":
                continue
            if not (node.get("_callable") or node.get("_callable_class")):
                continue  # skip file-level container nodes
            source_file = node.get("source_file", "")

            symbol_id = node["id"]
            kind = "class" if node.get("_callable_class") else "function"
            facts.append(
                Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:symbol:{symbol_id}")),
                    type="symbol_defined",
                    subject=EntityRef(EntityType.SYMBOL, symbol_id),
                    value={"name": node["label"], "kind": kind, "file": source_file},
                    provenance="observed",
                    confidence=1.0,
                    source_analyzer=analyzer,
                    evidence=(
                        Evidence(
                            kind="symbol",
                            ref=SymbolRef(
                                repository_id=ctx.repository_id,
                                path=source_file,
                                symbol_id=symbol_id,
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

        # --- relation facts (file-level, deduplicated) ---
        seen_edges: set[tuple[str, str, str]] = set()
        for link in data.get("links", []):
            rel_type = _RELATION_MAP.get(link.get("relation", ""))
            if rel_type is None:
                continue

            src_node = nodes_by_id.get(link["source"])
            tgt_node = nodes_by_id.get(link["target"])
            if not src_node or not tgt_node:
                continue

            src_file = src_node.get("source_file", "")
            tgt_file = tgt_node.get("source_file", "")
            if not src_file or not tgt_file or src_file == tgt_file:
                continue

            edge_key = (src_file, tgt_file, rel_type.value)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            facts.append(
                Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:{rel_type.value}:{src_file}:{tgt_file}")),
                    # Use the relation type directly as fact type so metrics can query by type
                    type=rel_type.value,
                    subject=EntityRef(EntityType.FILE, src_file),
                    predicate=rel_type,
                    object=EntityRef(EntityType.FILE, tgt_file),
                    provenance="observed",
                    confidence=1.0,
                    source_analyzer=analyzer,
                    evidence=(
                        Evidence(
                            kind="file",
                            ref=FileRef(repository_id=ctx.repository_id, path=src_file),
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
