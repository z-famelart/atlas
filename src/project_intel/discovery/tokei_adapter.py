"""Tokei language/LOC adapter — Feature 03 Part B."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..adapters.manifest import AdapterContext, AdapterManifest
from ..facts import SCHEMA_VERSION, EntityRef, EntityType, Evidence, Fact, FileRef

_MVP_LANGUAGES: frozenset[str] = frozenset(
    {"Python", "TypeScript", "JavaScript", "Go", "Java", "Kotlin", "Ruby", "Rust"}
)


def _normalize_tokei(raw: str, ctx: AdapterContext) -> list[Fact]:
    data: dict = json.loads(raw)
    source_analyzer = TOKEI_MANIFEST.source_analyzer_id
    facts: list[Fact] = []

    for language, lang_data in data.items():
        if language not in _MVP_LANGUAGES:
            continue
        for report in lang_data.get("reports", []):
            abs_path = report["name"]
            try:
                rel_path = str(Path(abs_path).relative_to(ctx.target_path))
            except ValueError:
                # path not under target_path — skip
                continue
            stats = report["stats"]
            ref = FileRef(repository_id=ctx.repository_id, path=rel_path)
            facts.append(
                Fact(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ctx.run_id}:{abs_path}")),
                    type="language_detected",
                    subject=EntityRef(type=EntityType.FILE, id=rel_path),
                    value={
                        "language": language,
                        "loc": stats["code"],
                        "total_lines": stats["lines"],
                    },
                    provenance="observed",
                    confidence=1.0,
                    evidence=(
                        Evidence(
                            kind="file",
                            ref=ref,
                            source_analyzer=source_analyzer,
                            retrieved_at=ctx.timestamp,
                        ),
                    ),
                    source_analyzer=source_analyzer,
                    run_id=ctx.run_id,
                    schema_version=SCHEMA_VERSION,
                    created_at=ctx.timestamp,
                )
            )

    return facts


TOKEI_MANIFEST = AdapterManifest(
    name="tokei",
    version="1.0",
    category="language_detection",
    command=["tokei", "--output", "json", "{target_path}"],
    min_version="12.0.0",
    normalize=_normalize_tokei,
    install_hint="cargo install tokei  # or: brew install tokei",
    supported_ecosystems=["python", "typescript", "javascript", "go", "java", "kotlin", "ruby", "rust"],
)
