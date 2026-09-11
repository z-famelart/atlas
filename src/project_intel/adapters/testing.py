"""Contract-test helper for adapter normalize() functions.

Usage in test files:
    facts = assert_normalizes(my_manifest, FIXTURE / "tool_output.json", context)
"""

from __future__ import annotations

from pathlib import Path

from ..facts import Fact
from .manifest import AdapterContext, AdapterManifest


def assert_normalizes(
    manifest: AdapterManifest,
    fixture_path: Path,
    context: AdapterContext,
    expected_facts: list[Fact] | None = None,
) -> list[Fact]:
    """Run normalize() against captured fixture output and assert contract invariants.

    Invariants checked on every call (regardless of expected_facts):
    - Returns a list of Fact instances.
    - Every fact has source_analyzer == manifest.source_analyzer_id.
    - Every fact has at least one evidence entry.
    - Every fact has run_id == context.run_id.

    If expected_facts is provided, also asserts the result is equal to it.
    """
    raw = fixture_path.read_text(encoding="utf-8")
    facts = manifest.normalize(raw, context)

    assert isinstance(facts, list), "normalize() must return a list"
    for fact in facts:
        assert isinstance(fact, Fact), f"normalize() returned a non-Fact item: {fact!r}"
        assert fact.source_analyzer == manifest.source_analyzer_id, (
            f"Fact.source_analyzer {fact.source_analyzer!r} != "
            f"manifest.source_analyzer_id {manifest.source_analyzer_id!r}"
        )
        assert len(fact.evidence) > 0, f"Fact {fact.id!r} has no evidence"
        assert fact.run_id == context.run_id, (
            f"Fact.run_id {fact.run_id!r} != context.run_id {context.run_id!r}"
        )

    if expected_facts is not None:
        assert facts == expected_facts

    return facts
