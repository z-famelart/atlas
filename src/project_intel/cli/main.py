"""CLI entry point — atlas analyze / facts query."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from ..discovery.scope import ScopeConfig
from ..facts.enums import EntityType, RelationType
from ..facts.model import Entity, EntityRef, Evidence, Fact
from ..facts.refs import ConfigRef
from ..facts.store import SCHEMA_VERSION, FactStore
from ..hotspots.weights import HotspotWeights
from ..html_report import generate_report as _generate_report
from ..llm.providers import ClaudeCodeProvider, DisabledProvider, OllamaProvider
from .registry import STAGE_REGISTRY
from .types import PipelineContext, StageRunResult

_DEFAULT_SCOPE = ScopeConfig(
    exclude_globs=(
        ".git/*",
        ".git",
        "node_modules/*",
        "__pycache__/*",
        "*.pyc",
        ".venv/*",
        "venv/*",
        "dist/*",
        "build/*",
        ".mypy_cache/*",
        ".ruff_cache/*",
        ".pytest_cache/*",
    )
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------


def _load_config(config_path: Path) -> dict[str, Any]:
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def _scope_from_config(cfg: dict[str, Any]) -> ScopeConfig:
    scope = cfg.get("scope", {})
    exclude = tuple(scope.get("exclude_globs", _DEFAULT_SCOPE.exclude_globs))
    include = tuple(scope.get("include_globs", ()))
    max_depth = scope.get("max_depth", None)
    return ScopeConfig(include_globs=include, exclude_globs=exclude, max_depth=max_depth)


def _weights_from_config(cfg: dict[str, Any]) -> HotspotWeights:
    w = cfg.get("hotspot_weights", {})
    return HotspotWeights(
        complexity=w.get("complexity", 1.0),
        size=w.get("size", 0.5),
        centrality=w.get("centrality", 1.0),
        churn=w.get("churn", 1.0),
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _configure_logging(verbosity: int) -> None:
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
        force=True,
    )


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

_STATUS_GLYPH = {"ok": "✓", "failed": "✗", "skipped": "⊘"}


def _run_stages_plain(
    stages: list[Any], ctx: PipelineContext
) -> list[StageRunResult]:
    results: list[StageRunResult] = []
    for stage in stages:
        click.echo(f"Running {stage.name}…")
        result = _run_stage_safe(stage, ctx)
        glyph = _STATUS_GLYPH.get(result.status, "?")
        detail = f"  {result.detail}" if result.detail else ""
        click.echo(f"{glyph} {result.name}: {result.facts_produced} facts{detail}")
        results.append(result)
    return results


def _run_stages_rich(
    stages: list[Any], ctx: PipelineContext
) -> list[StageRunResult]:
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    results: list[StageRunResult] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=False,
    ) as progress:
        for stage in stages:
            task = progress.add_task(stage.name, total=None)
            result = _run_stage_safe(stage, ctx)
            glyph = _STATUS_GLYPH.get(result.status, "?")
            detail = f"  {result.detail}" if result.detail else ""
            label = f"{glyph} {result.name}: {result.facts_produced} facts{detail}"
            progress.update(task, description=label, completed=1, total=1)
            results.append(result)
    return results


def _run_stage_safe(stage: Any, ctx: PipelineContext) -> StageRunResult:
    try:
        result = stage.run(ctx)
    except Exception as exc:
        logger.debug("Stage %s raised an exception", stage.name, exc_info=True)
        result = StageRunResult(name=stage.name, status="failed", facts_produced=0, detail=str(exc))
    _persist_stage_run_result(ctx, result)
    return result


def _persist_stage_run_result(ctx: PipelineContext, result: StageRunResult) -> None:
    """Record every stage's outcome as a `stage_run_result` fact (Feature 06c)."""
    repository_id = str(ctx.repository_path.resolve())
    fact = Fact(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:stage_run_result:{result.name}")),
        type="stage_run_result",
        subject=EntityRef(EntityType.REPOSITORY, repository_id),
        value={
            "stage": result.name,
            "status": result.status,
            "facts_produced": result.facts_produced,
            "detail": result.detail,
        },
        provenance="computed",
        confidence=1.0,
        source_analyzer="cli.runner@1.0",
        evidence=(),
        created_at=datetime.now(UTC),
        schema_version=SCHEMA_VERSION,
        run_id=ctx.run_id,
    )
    ctx.store.insert_facts([fact])


# ---------------------------------------------------------------------------
# Multi-repository System orchestration (Feature 13b)
# ---------------------------------------------------------------------------


def _write_system_facts(project_root: Path, repos_cfg: list[dict[str, Any]], config_path: Path) -> None:
    """Group [[repositories]] entries by declared `system`; for each with 2+
    members, write System/Repository entities and `belongs_to` facts (declared
    membership only — Décidé Q4 rules out inferring *how* repos relate) to a
    dedicated store, separate from each repository's own facts.sqlite."""
    by_system: dict[str, list[dict[str, Any]]] = {}
    for entry in repos_cfg:
        system_name = entry.get("system")
        if system_name:
            by_system.setdefault(system_name, []).append(entry)

    for system_name, members in by_system.items():
        if len(members) < 2:
            continue

        db_dir = project_root / ".atlas-cache"
        db_dir.mkdir(parents=True, exist_ok=True)
        store = FactStore(db_dir / f"system-{system_name}.sqlite")
        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        entities = [Entity(type=EntityType.SYSTEM, id=system_name, attributes={})]
        facts = []
        for entry in members:
            repo_id = str(Path(entry["path"]).resolve())
            repo_name = entry.get("name", Path(repo_id).name)
            entities.append(
                Entity(
                    type=EntityType.REPOSITORY,
                    id=repo_id,
                    attributes={"name": repo_name},
                    repository_id=repo_id,
                )
            )
            facts.append(
                Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:belongs_to:{repo_id}:{system_name}")),
                    type=RelationType.BELONGS_TO.value,
                    subject=EntityRef(EntityType.REPOSITORY, repo_id),
                    predicate=RelationType.BELONGS_TO,
                    object=EntityRef(EntityType.SYSTEM, system_name),
                    provenance="observed",
                    confidence=1.0,
                    source_analyzer="system_orchestration@1.0",
                    evidence=(
                        Evidence(
                            kind="config",
                            ref=ConfigRef(repository_id=repo_id, path=str(config_path)),
                            source_analyzer="system_orchestration@1.0",
                            retrieved_at=now,
                        ),
                    ),
                    created_at=now,
                    schema_version=SCHEMA_VERSION,
                    run_id=run_id,
                )
            )

        store.insert_entities(entities)
        store.insert_facts(facts)
        store.close()
        click.echo(f"System '{system_name}': {len(members)} repositories -> {db_dir / f'system-{system_name}.sqlite'}")


# ---------------------------------------------------------------------------
# Interactive ollama model selection
# ---------------------------------------------------------------------------


def _pick_ollama_model() -> str:
    """Prompt the user to pick an Ollama model from the installed list."""
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
    models = [
        line.split()[0]
        for line in result.stdout.strip().splitlines()[1:]  # skip header
        if line.strip()
    ]
    if models:
        click.echo("Available Ollama models:")
        for i, m in enumerate(models, 1):
            click.echo(f"  {i}. {m}")
        return click.prompt("Select model (name or number)", default=models[0])
    return click.prompt("Ollama model (e.g. qwen2.5:14b)")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.group()
def main() -> None:
    """Project Intelligence — build an evidence-linked understanding map of a codebase."""


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path), required=False)
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None,
              help="TOML project config file. Auto-discovers .atlas.toml in PATH if omitted.")
@click.option("--no-llm", is_flag=True, default=False, help="Disable LLM stages.")
@click.option("--llm-provider", default=None, show_default=True,
              type=click.Choice(["ollama", "claude-code"]),
              help="LLM backend (overrides config).")
@click.option("--ollama-model", default=None, envvar="OLLAMA_MODEL",
              help="Ollama model tag. Also read from $OLLAMA_MODEL.")
@click.option("--ollama-url", default="http://localhost:11434", show_default=True, envvar="OLLAMA_URL",
              help="Base URL of the Ollama server.")
@click.option("--claude-model", default="claude-haiku-4-5-20251001", show_default=True, envvar="CLAUDE_MODEL",
              help="Claude model ID when --llm-provider=claude-code.")
@click.option("--only", "only_stages", multiple=True, metavar="STAGE",
              help="Run only this stage (repeatable). E.g. --only git --only hotspots.")
@click.option("-v", "--verbose", "verbosity", count=True,
              help="-v = INFO, -vv = DEBUG.")
@click.option("--debug", "debug_flag", is_flag=True, default=False,
              help="Alias for -vv (DEBUG logging).")
def analyze(
    path: Path | None,
    config_path: Path | None,
    no_llm: bool,
    llm_provider: str | None,
    ollama_model: str | None,
    ollama_url: str,
    claude_model: str,
    only_stages: tuple[str, ...],
    verbosity: int,
    debug_flag: bool,
) -> None:
    """Run all analysis stages against a repository at PATH.

    LLM stages are enabled by default and use a local Ollama server (no API key
    required). Set OLLAMA_MODEL (e.g. qwen2.5:14b) or pass --ollama-model.
    Pass --no-llm to skip LLM stages entirely, or --llm-provider=claude-code to
    use the local Claude Code CLI instead.
    """
    if debug_flag:
        verbosity = max(verbosity, 2)

    _configure_logging(verbosity)

    # --- load config ---
    cfg: dict[str, Any] = {}
    if config_path is None and path is not None:
        candidate = path / ".atlas.toml"
        if candidate.exists():
            config_path = candidate
    if config_path is not None:
        cfg = _load_config(config_path)

    # --- repositories list ---
    repos_cfg = cfg.get("repositories", [])
    if path is not None:
        # CLI path takes precedence; ignore [[repositories]] from config
        repos = [{"path": str(path), "name": path.name}]
    elif repos_cfg:
        repos = repos_cfg
    else:
        raise click.UsageError("Provide a PATH argument or a config file with [[repositories]].")

    # --- scope & weights from config ---
    scope = _scope_from_config(cfg) if cfg else _DEFAULT_SCOPE
    # ponytail: weights loaded but stages don't read from ctx yet; wire when hotspots stage exposes it
    _weights = _weights_from_config(cfg)

    # --- LLM config merging (config < env < CLI flags) ---
    llm_cfg = cfg.get("llm", {})
    if llm_provider is None:
        llm_provider = llm_cfg.get("provider", "ollama")
    if ollama_model is None:
        ollama_model = llm_cfg.get("model")
    # ponytail: budget_tokens loaded; stages use BudgetConfig.unlimited() until threaded through ctx
    _budget_tokens: int | None = llm_cfg.get("budget_tokens")

    # --- resolve LLM provider ---
    if no_llm:
        llm_provider_obj = DisabledProvider()
    elif llm_provider == "claude-code":
        llm_provider_obj = ClaudeCodeProvider(model=claude_model)
    else:
        # ollama
        if not ollama_model:
            if sys.stdin.isatty():
                ollama_model = _pick_ollama_model()
            else:
                raise click.ClickException(
                    "No Ollama model configured — set OLLAMA_MODEL (e.g. qwen2.5:14b) "
                    "or pass --ollama-model, or run with --no-llm."
                )
        llm_provider_obj = OllamaProvider(model=ollama_model, base_url=ollama_url)

    # --- stage filter ---
    stages = list(STAGE_REGISTRY)
    if only_stages:
        stages = [s for s in stages if s.name in set(only_stages)]
        if not stages:
            raise click.ClickException(
                f"No stages matched --only filter: {list(only_stages)}. "
                f"Available: {[s.name for s in STAGE_REGISTRY]}"
            )

    use_rich = sys.stdout.isatty() and verbosity == 0

    any_failed = False

    for repo_entry in repos:
        repo_path = Path(repo_entry["path"]).resolve()
        repo_name = repo_entry.get("name", repo_path.name)

        if len(repos) > 1:
            click.echo(f"\n── {repo_name} ({repo_path}) ──")

        db_dir = repo_path / ".atlas-cache"
        db_dir.mkdir(parents=True, exist_ok=True)
        store = FactStore(db_dir / "facts.sqlite")

        run_id = str(uuid.uuid4())
        ctx = PipelineContext(
            store=store,
            repository_path=repo_path,
            run_id=run_id,
            scope=scope,
            llm_provider=llm_provider_obj,
        )

        click.echo(f"run_id:    {run_id}")
        click.echo(f"analyzing: {repo_path}\n")

        if use_rich:
            results = _run_stages_rich(stages, ctx)
        else:
            results = _run_stages_plain(stages, ctx)

        any_failed = any_failed or any(r.status == "failed" for r in results)

        # --- HTML report ---
        report_path = _generate_report(ctx.store, run_id=ctx.run_id, output_dir=Path("."))
        click.echo(f"Report: {report_path}")

        store.close()

    if path is None and repos_cfg and config_path is not None:
        _write_system_facts(config_path.resolve().parent, repos_cfg, config_path)

    raise SystemExit(1 if any_failed else 0)


@main.group()
def facts() -> None:
    """Read facts produced by a previous `analyze` run.

    Facts are the normalized, evidence-linked observations stored in
    <repo>/.atlas-cache/facts.sqlite after each `analyze` run.
    Use `facts query` to filter and inspect them.
    """


@facts.command("query")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--type", "fact_type", default=None,
    help=(
        "Keep only facts of this type. "
        "Common values: technology_detected, language_detected, git_churn, "
        "centrality, hotspot_score, symbol_defined, calls, imports."
    ),
)
@click.option(
    "--run-id", default=None,
    help=(
        "Keep only facts from this specific analysis run. "
        "The run ID is printed at the start of every `analyze` call."
    ),
)
@click.option(
    "--provenance", default=None,
    help=(
        "Keep only facts with this provenance. "
        "Values: observed (raw tool output), computed (derived metric), "
        "inferred (heuristic), hypothesis (LLM suggestion)."
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Emit full fact records as JSON instead of a summary table.")
def facts_query(
    path: Path,
    fact_type: str | None,
    run_id: str | None,
    provenance: str | None,
    as_json: bool,
) -> None:
    """Print facts stored for the repository at PATH.

    Without filters, lists every fact across all runs — usually thousands of
    lines. Narrow down with --type and/or --run-id first.

    \b
    Examples:
      atlas facts query . --type technology_detected
      atlas facts query . --type hotspot_score --run-id <id>
      atlas facts query . --type git_churn --json
    """
    import dataclasses

    db_path = path.resolve() / ".atlas-cache" / "facts.sqlite"
    if not db_path.exists():
        raise click.ClickException(f"No facts database at {db_path}")

    store = FactStore(db_path)
    stored_facts = list(store.query_facts(type=fact_type, run_id=run_id, provenance=provenance))
    store.close()

    if as_json:
        output = []
        for f in stored_facts:
            d = dataclasses.asdict(f)
            d["subject"] = {"type": f.subject.type.value, "id": f.subject.id}
            output.append(d)
        click.echo(json.dumps(output, default=str, indent=2))
    else:
        for f in stored_facts:
            click.echo(f"{f.type:<30} {f.subject.type.value:<12} {f.subject.id}")

@main.command("mcp-serve")
@click.option("--port", default=8765, type=int, help="Port (reserved for future SSE transport).")
def mcp_serve(port: int) -> None:
    """Start the MCP server for AI agent access.

    Global server — no database path needed at startup. Every tool call
    carries a repo_path argument; the server derives
    <repo_path>/.atlas-cache/facts.sqlite on each call.
    """
    from ..mcp_server import run_server
    run_server(port=port)



if __name__ == "__main__":
    main()
