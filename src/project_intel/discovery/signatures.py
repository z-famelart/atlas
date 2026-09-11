"""Signature loader and matcher — reads from data/signatures.toml."""

from __future__ import annotations

import fnmatch
import json
import tomllib
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "signatures.toml"


def _load_signatures() -> list[dict]:
    with _DATA_FILE.open("rb") as fh:
        return tomllib.load(fh)["signatures"]


# Cache at import time — data file is read-only.
_SIGNATURES: list[dict] = _load_signatures()


def _key_present(root: Path, manifest_file: str, manifest_key: str) -> bool:
    """Return True if dot-separated manifest_key path exists in a JSON/TOML manifest."""
    mf = root / manifest_file
    if not mf.is_file():
        return False
    try:
        if manifest_file.endswith(".toml"):
            with mf.open("rb") as fh:
                data = tomllib.load(fh)
        else:
            data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    for part in manifest_key.split("."):
        if not isinstance(data, dict) or part not in data:
            return False
        data = data[part]
    return True


def match_signatures(root: Path, rel_paths: list[str]) -> list[dict]:
    """Return list of matched signature entries (no dedup — callers decide).

    Each returned dict has at minimum: category, name, matched_path.
    """
    matched: list[dict] = []
    path_set = set(rel_paths)

    for sig in _SIGNATURES:
        if "manifest_file" in sig and "manifest_key" in sig:
            if _key_present(root, sig["manifest_file"], sig["manifest_key"]):
                matched.append({**sig, "matched_path": sig["manifest_file"]})
            continue

        for pattern in sig.get("files", []):
            for rel in path_set:
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern):
                    matched.append({**sig, "matched_path": rel})
                    break  # one match per signature entry is enough

    return matched
