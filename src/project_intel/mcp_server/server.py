"""MCP server — AI-facing entry point over an existing FactStore."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from ..facts.store import FactStore
from . import queries


def create_server(db_path: str | Path) -> MCPServer:
    """Return a configured MCPServer that reads from db_path."""
    store = FactStore(Path(db_path))
    mcp = MCPServer(name="atlas", description="Atlas project-intelligence MCP server")

    @mcp.tool(description="Look up facts about a component (file). Returns the first match.")
    def get_component(name_or_path: str) -> str:
        result = queries.get_component(store, name_or_path)
        if result is None:
            return json.dumps({"error": f"component not found: {name_or_path}"})
        return json.dumps(result, default=str)

    @mcp.tool(description="Outbound imports/calls from a component. limit capped at 50.")
    def get_dependencies(component: str, limit: int = 20) -> str:
        return json.dumps(queries.get_dependencies(store, component, limit), default=str)

    @mcp.tool(description="Inbound imports/calls targeting a component. limit capped at 50.")
    def get_dependents(component: str, limit: int = 20) -> str:
        return json.dumps(queries.get_dependents(store, component, limit), default=str)

    @mcp.tool(description="Substring search over business_workflow facts. limit capped at 20.")
    def find_workflow(query: str, limit: int = 10) -> str:
        return json.dumps(queries.find_workflow(store, query, limit), default=str)

    @mcp.tool(description="hotspot_score facts sorted by combined_score. top_n capped at 50.")
    def get_hotspots(top_n: int = 10, component: str | None = None) -> str:
        return json.dumps(queries.get_hotspots(store, top_n, component), default=str)

    @mcp.tool(
        description=(
            "BFS shortest path between two components in the imports/calls graph. "
            "max_depth capped at 10. Returns {found: false, reason: 'no path within bound'} "
            "when no path exists within the depth limit."
        )
    )
    def get_path(component_a: str, component_b: str, max_depth: int = 5) -> str:
        return json.dumps(queries.get_path(store, component_a, component_b, max_depth), default=str)

    @mcp.tool(
        description=(
            "Onboarding_path facts if present, else top hotspots + high-centrality files. "
            "Scope to a specific component with the optional component argument."
        )
    )
    def where_to_start(component: str | None = None) -> str:
        return json.dumps(queries.where_to_start(store, component), default=str)

    return mcp


def run_server(db_path: str | Path, host: str = "localhost", port: int = 8765) -> None:
    """Start the MCP server over stdio (host/port reserved for future SSE transport)."""
    mcp = create_server(db_path)
    mcp.run(transport="stdio")
