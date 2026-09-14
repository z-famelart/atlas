"""CLI entry point — atlas analyze / facts query."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import click

from ..discovery.scope import ScopeConfig
from ..facts.store import FactStore
from .registry import STAGE_REGISTRY
from .types import PipelineContext

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


@click.group()
def main() -> None:
    """Project Intelligence — build an evidence-linked understanding map of a codebase."""


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
def analyze(path: Path) -> None:
    """Run all analysis stages against a repository at PATH."""
    repo_path = path.resolve()
    db_dir = repo_path / ".atlas-cache"
    db_dir.mkdir(parents=True, exist_ok=True)
    store = FactStore(db_dir / "facts.sqlite")

    run_id = str(uuid.uuid4())
    ctx = PipelineContext(
        store=store,
        repository_path=repo_path,
        run_id=run_id,
        scope=_DEFAULT_SCOPE,
    )

    click.echo(f"run_id:    {run_id}")
    click.echo(f"analyzing: {repo_path}\n")

    any_failed = False
    click.echo(f"{'stage':<20} {'status':<10} {'facts':>10}  detail")
    click.echo("-" * 70)

    for stage in STAGE_REGISTRY:
        result = stage.run(ctx)
        if result.status == "failed":
            any_failed = True
        click.echo(
            f"{result.name:<20} {result.status:<10} {result.facts_produced:>10}  {result.detail or ''}"
        )

    store.close()
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

if __name__ == "__main__":
    main()
