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


def create_server() -> MCPServer:
    """Return a configured global MCPServer (repo_path per call, no fixed db_path)."""
    mcp = MCPServer(name="atlas", description="Atlas project-intelligence MCP server")

    @mcp.tool(description="Look up facts about a component (file). Returns the first match.")
    def get_component(repo_path: str, name_or_path: str) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_component(store, name_or_path)
        finally:
            store.close()
        if result is None:
            return json.dumps({"error": f"component not found: {name_or_path}"})
        return json.dumps(result, default=str)

    @mcp.tool(description="Outbound imports/calls from a component. limit capped at 50.")
    def get_dependencies(repo_path: str, component: str, limit: int = 20) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_dependencies(store, component, limit)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(description="Inbound imports/calls targeting a component. limit capped at 50.")
    def get_dependents(repo_path: str, component: str, limit: int = 20) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_dependents(store, component, limit)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(description="Substring search over business_workflow facts. limit capped at 20.")
    def find_workflow(repo_path: str, query: str, limit: int = 10) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.find_workflow(store, query, limit)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(description="hotspot_score facts sorted by combined_score. top_n capped at 50.")
    def get_hotspots(repo_path: str, top_n: int = 10, component: str | None = None) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_hotspots(store, top_n, component)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "BFS shortest path between two components in the imports/calls graph. "
            "max_depth capped at 10. Returns {found: false, reason: 'no path within bound'} "
            "when no path exists within the depth limit."
        )
    )
    def get_path(repo_path: str, component_a: str, component_b: str, max_depth: int = 5) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.get_path(store, component_a, component_b, max_depth)
        finally:
            store.close()
        return json.dumps(result, default=str)

    @mcp.tool(
        description=(
            "Onboarding_path facts if present, else top hotspots + high-centrality files. "
            "Scope to a specific component with the optional component argument."
        )
    )
    def where_to_start(repo_path: str, component: str | None = None) -> str:
        store = _open_store(repo_path)
        if store is None:
            return _missing(repo_path)
        try:
            result = queries.where_to_start(store, component)
        finally:
            store.close()
        return json.dumps(result, default=str)

    return mcp


def run_server(port: int = 8765) -> None:
    """Start the global MCP server over stdio (port reserved for future SSE transport)."""
    mcp = create_server()
    mcp.run(transport="stdio")
