"""`atlas doctor` and `atlas setup` — one-command onboarding per harness."""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
from importlib import resources
from pathlib import Path

import click

from ..code_graph.graphify_provider import GraphifyProvider
from ..discovery import TOKEI_MANIFEST
from ..git_analysis.barad_dur import barad_dur_manifest

_MCP_ARGS = ["atlas", "atlas", "mcp-serve"]

# ponytail: gemini and codex invocations come from their docs, not from a tested install;
# claude and agy were run for real.
_HARNESSES: dict[str, dict] = {
    "claude": {"binary": "claude", "provider": "claude-code",
               "mcp": ["claude", "mcp", "add", "--scope", "user", "atlas", "--", "atlas", "mcp-serve"]},
    "agy": {"binary": "agy", "provider": "agy", "mcp": ["agy", "mcp", "add", *_MCP_ARGS]},
    "gemini": {"binary": "gemini", "provider": "gemini-cli",
               "mcp": ["gemini", "mcp", "add", "--scope", "user", *_MCP_ARGS]},
    "codex": {"binary": "codex", "provider": None,
              "mcp": ["codex", "mcp", "add", "atlas", "--", "atlas", "mcp-serve"]},
}


def _analyzers() -> list[tuple[str, str, str]]:
    graphify = GraphifyProvider().manifest()
    barad = barad_dur_manifest()
    return [
        ("tokei", "tokei", TOKEI_MANIFEST.install_hint or ""),
        ("graphify", "graphify", graphify.install_hint or ""),
        ("barad-dur", "barad-dur", barad.install_hint or ""),
    ]


def _llama_server_up(url: str = "http://localhost:8080") -> bool:
    try:
        urllib.request.urlopen(f"{url}/health", timeout=1)
        return True
    except OSError:
        return False


def _line(ok: bool, name: str, detail: str = "") -> None:
    click.echo(f"  {'✓' if ok else '✗'} {name:<14}{detail}")


@click.command()
def doctor() -> None:
    """Check the external tools and LLM backends Atlas can use."""
    click.echo("Analyzers")
    _line(bool(shutil.which("git")), "git", "" if shutil.which("git") else "required")
    for name, binary, hint in _analyzers():
        found = shutil.which(binary)
        _line(bool(found), name, "" if found else f"missing → {hint}")
    click.echo("LLM backends (any one is enough; none = use --no-llm)")
    backends = [
        ("llama-server", _llama_server_up(), "atlas analyze .  (default)"),
        ("claude", bool(shutil.which("claude")), "--llm-provider claude-code"),
        ("agy", bool(shutil.which("agy")), "--llm-provider agy"),
        ("gemini", bool(shutil.which("gemini")), "--llm-provider gemini-cli"),
        ("ollama", bool(shutil.which("ollama")), "--llm-provider ollama --ollama-model <tag>"),
    ]
    for name, ok, how in backends:
        _line(ok, name, how if ok else "")


def _register_mcp(harness: str) -> None:
    cmd = _HARNESSES[harness]["mcp"]
    if not shutil.which(cmd[0]):
        click.echo(f"  ✗ MCP: `{cmd[0]}` not found — install it, or run: {' '.join(cmd)}")
        return
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0 or "already exists" in out.lower():
        click.echo(f"  ✓ MCP server `atlas` registered in {harness}")
    else:
        click.echo(f"  ✗ MCP registration failed ({out[:200]}). Run by hand: {' '.join(cmd)}")


def _install_recipe(home: Path) -> None:
    dest = home / ".claude" / "agents" / "atlas-synthesis.md"
    recipe = resources.files("project_intel").joinpath("data/atlas-synthesis.md").read_text()
    if dest.exists() and dest.read_text() != recipe:
        click.echo(f"  ⊘ {dest} exists and differs — left untouched")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(recipe)
    click.echo(f"  ✓ synthesis agent installed at {dest}")


@click.command()
@click.option("--harness", required=True, type=click.Choice(sorted(_HARNESSES)),
              help="The coding agent you use.")
def setup(harness: str) -> None:
    """Wire Atlas into a coding agent: MCP server, synthesis agent, LLM hint."""
    info = _HARNESSES[harness]
    click.echo(f"Setting up Atlas for {harness}")
    _register_mcp(harness)
    if harness == "claude":
        _install_recipe(Path.home())
    else:
        click.echo("  ⊘ synthesis agent: Claude Code only for now — the MCP tools work as is")
    click.echo("")
    doctor.callback()  # type: ignore[misc]
    click.echo("")
    flag = f"--llm-provider {info['provider']} " if info["provider"] else "--no-llm "
    click.echo(f"Next: atlas analyze {flag}.")
