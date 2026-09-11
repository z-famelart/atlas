"""Document/config file tagger — classifies files by documentary role."""

from __future__ import annotations

import fnmatch

# Patterns → role tag.  First match wins.
_DOC_PATTERNS: list[tuple[str, str]] = [
    ("README*", "readme"),
    ("CHANGELOG*", "changelog"),
    ("CONTRIBUTING*", "contributing"),
    ("LICENSE*", "license"),
    ("NOTICE*", "notice"),
    ("*.md", "markdown"),
    ("*.rst", "rst"),
    ("*.adoc", "asciidoc"),
    ("*.txt", "text"),
    # Config files worth tagging as documents
    (".env*", "env"),
    ("*.yaml", "config"),
    ("*.yml", "config"),
    ("*.json", "config"),
    ("*.toml", "config"),
    ("*.ini", "config"),
    ("*.cfg", "config"),
    ("*.conf", "config"),
]


def tag_documents(rel_paths: list[str]) -> list[dict[str, str]]:
    """Return a list of {path, role} dicts for files that match a documentary pattern.

    Files with no match are skipped (they are handled as unrecognized artifacts).
    """
    tagged: list[dict[str, str]] = []
    for rel in rel_paths:
        name = rel.split("/")[-1]
        for pattern, role in _DOC_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                tagged.append({"path": rel, "role": role})
                break
    return tagged
