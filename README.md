# Project Intelligence (Atlas)

Builds an evidence-linked understanding map of an unfamiliar software system: what it is, how it's built, and where to look first.

See [`specs/Product Brief & Vision.md`](specs/Product%20Brief%20%26%20Vision.md) for the pitch and principles, [`specs/Capability Matrix.md`](specs/Capability%20Matrix.md) for scope, and [`specs/Design Decisions.md`](specs/Design%20Decisions.md) for the architectural decisions this implementation follows. Feature-level specs live under [`specs/features/`](specs/features/).

## Development

This project is managed with [mise](https://mise.jdx.dev/) (Python + uv toolchain pinning) and [uv](https://docs.astral.sh/uv/) (dependency management).

```bash
mise install
uv sync
uv run project-intel
```

Run tests and lint:

```bash
uv run pytest
uv run ruff check .
```
