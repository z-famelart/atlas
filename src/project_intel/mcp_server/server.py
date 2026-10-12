"""MCP server — AI-facing entry point over an existing FactStore.

Global server: no db_path at startup. Every tool call carries repo_path;
the server derives <repo_path>/.atlas-cache/facts.sqlite per call.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from ..facts.store import FactStore
from . import queries


def _db_path(repo_path: str) -> Path:
    return Path(repo_path) / ".atlas-cache" / "facts.sqlite"


def _open_store(repo_path: str) -> FactStore | None:
    """Return an open FactStore or None if the database does not exist."""
    p = _db_path(repo_path)
    if not p.exists():
        return None
    return FactStore(p)


def _missing(repo_path: str) -> str:
    return json.dumps({
        "error": "no facts store found",
        "expected_path": str(_db_path(repo_path)),
        "hint": f"run `atlas analyze {repo_path}` first",
    })


def _system_db_path(project_root: str, system_name: str) -> Path:
    return Path(project_root) / ".atlas-cache" / f"system-{system_name}.sqlite"


def _open_system_store(project_root: str, system_name: str) -> FactStore | None:
    """Return an open system FactStore (Feature 13b) or None if it doesn't exist."""
    p = _system_db_path(project_root, system_name)
    if not p.exists():
        return None
    return FactStore(p)


def _missing_system(project_root: str, system_name: str) -> str:
    return json.dumps({
        "error": "no system store found",
        "expected_path": str(_system_db_path(project_root, system_name)),
        "hint": (
            f"run `atlas analyze --config <project.toml>` with 2+ [[repositories]] "
            f'declaring system = "{system_name}" first'
        ),
    })


def create_server() -> MCPServer:
    """Return a configured global MCPServer (repo_path per call, no fixed db_path)."""
    mcp = MCPServer(name="atlas", description="Atlas project-intelligence MCP server")

    @mcp.tool(
        description=(
            "Look up facts about a component (file). Returns the first match. "
            "Each fact type comes from the most recent run that produced it, or a specific run_id if given."
        )
    )
    def get_component(repo_path: str, name_or_path: str, run_id: str | None = None) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_component(store, name_or_path, run_id)
        finally:
            store.close()
        if result is None:
            return json.dumps({"error": f"component not found: {name_or_path}"})
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Outbound imports/calls from a component. limit capped at 50. "
            "Scoped to the most recent run that produced these facts, or a specific run_id if given."
        )
    )
    def get_dependencies(
        repo_path: str, component: str, limit: int = 20, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_dependencies(store, component, limit, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Inbound imports/calls targeting a component. limit capped at 50. "
            "Scoped to the most recent run that produced these facts, or a specific run_id if given."
        )
    )
    def get_dependents(
        repo_path: str, component: str, limit: int = 20, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_dependents(store, component, limit, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Substring search over business_workflow facts. limit capped at 20. "
            "Scoped to the most recent run that produced these facts, or a specific run_id if given."
        )
    )
    def find_workflow(
        repo_path: str, query: str, limit: int = 10, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.find_workflow(store, query, limit, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "hotspot_score facts sorted by combined descending. top_n capped at 50. "
            "Scoped to the most recent run that produced these facts, or a specific run_id if given."
        )
    )
    def get_hotspots(
        repo_path: str, top_n: int = 10, component: str | None = None, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_hotspots(store, top_n, component, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "BFS shortest path between two components in the imports/calls graph. "
            "max_depth capped at 10. Returns {found: false, reason: 'no path within bound'} "
            "when no path exists within the depth limit. Scoped to the most recent run that "
            "produced these facts, or a specific run_id if given."
        )
    )
    def get_path(
        repo_path: str,
        component_a: str,
        component_b: str,
        max_depth: int = 5,
        run_id: str | None = None,
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_path(store, component_a, component_b, max_depth, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Onboarding_path facts if present, else top hotspots + high-centrality files. "
            "Scope to a specific component with the optional component argument. Each fact type "
            "comes from the most recent run that produced it, or a specific run_id if given."
        )
    )
    def where_to_start(
        repo_path: str, component: str | None = None, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.where_to_start(store, component, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Who owns the code under path_prefix (default: whole repo): authors ranked by mean "
            "blame share across files, from git_ownership facts (needs the optional barad-dur "
            "adapter; an empty list means it did not run). top_n capped at 50. Per-file ownership "
            "and age are also in get_component."
        )
    )
    def get_owners(
        repo_path: str, path_prefix: str = "", top_n: int = 5, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_owners(store, path_prefix, top_n, run_id)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Repository-level interpretation facts (LLM hypotheses, provenance + confidence "
            "included). kind: 'architecture' (architecture_hypothesis), 'concepts' "
            "(business_concept) or 'glossary' (glossary_term). Highest confidence first; "
            "limit capped at 50. Defaults to the latest run holding that kind, or a specific "
            "run_id if given. An empty list means no such facts were produced."
        )
    )
    def get_insights(
        repo_path: str, kind: str, limit: int = 10, run_id: str | None = None
    ) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_insights(store, kind, limit, run_id)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "System-level membership (Feature 13b): the System entity, its member "
            "Repository entities (each id is a resolved repo_path, usable directly as "
            "the repo_path argument to every other tool), and the belongs_to facts "
            "declaring membership. Provenance is always 'observed' — declared in the "
            "Project config, never inferred (Q4). Returns a not-analyzed response if "
            "no system with this name/project_root has been orchestrated yet."
        )
    )
    def get_system(project_root: str, system_name: str) -> str:
        store = _open_system_store(project_root, system_name)
        if store is None:
            return _missing_system(project_root, system_name)
        try:
            result = queries.get_system(store)
        finally:
            store.close()
        return json.dumps(result, default=str)

    return mcp


def run_server(port: int = 8765) -> None:
    """Start the global MCP server over stdio (port reserved for future SSE transport)."""
    mcp = create_server()
    mcp.run(transport="stdio")
