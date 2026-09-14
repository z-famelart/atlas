"""CLI entry point — project-intel analyze / facts query."""

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
    db_dir = repo_path / ".project-intel"
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
    """Inspect stored facts."""


@facts.command("query")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--type", "fact_type", default=None, help="Filter by fact type.")
@click.option("--run-id", default=None, help="Filter by run ID.")
@click.option("--provenance", default=None, help="Filter by provenance.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def facts_query(
    path: Path,
    fact_type: str | None,
    run_id: str | None,
    provenance: str | None,
    as_json: bool,
) -> None:
    """Query stored facts for the repository at PATH."""
    import dataclasses

    db_path = path.resolve() / ".project-intel" / "facts.sqlite"
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
