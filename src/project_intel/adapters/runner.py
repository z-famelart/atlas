"""Adapter executor — presence/version checks, parallel execution, failure isolation."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from packaging.version import InvalidVersion, Version

from .manifest import AdapterContext, AdapterManifest
from .result import AdapterResult, AdapterStatus


def _is_cli(command: list[str] | Callable) -> bool:
    return isinstance(command, list)


def _check_presence(manifest: AdapterManifest) -> bool:
    """Return True if the adapter's binary is available (pure-Python adapters always pass)."""
    if not _is_cli(manifest.command):
        return True
    binary = manifest.command[0]
    return shutil.which(binary) is not None


def _detect_version(binary: str) -> str | None:
    """Run `binary --version` and extract the first X.Y[.Z] version string found."""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = proc.stdout + proc.stderr
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
        return match.group(1) if match else None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def _version_in_range(version: str, min_v: str | None, max_v: str | None) -> bool:
    """Return True if version is within [min_v, max_v] (both bounds inclusive, both optional)."""
    try:
        v = Version(version)
        if min_v and v < Version(min_v):
            return False
        if max_v and v > Version(max_v):
            return False
    except InvalidVersion:
        return False
    return True


def _invoke(manifest: AdapterManifest, context: AdapterContext) -> str:
    """Run the adapter's command and return its raw output string."""
    if _is_cli(manifest.command):
        proc = subprocess.run(
            manifest.command,
            cwd=context.target_path,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command {manifest.command!r} exited {proc.returncode}:\n{proc.stderr.strip()}"
            )
        return proc.stdout
    else:
        return manifest.command(context)


def _run_one(manifest: AdapterManifest, context: AdapterContext) -> AdapterResult:
    """Execute one adapter, returning an AdapterResult regardless of outcome."""
    # 1. Presence check
    if not _check_presence(manifest):
        hint = f" — {manifest.install_hint}" if manifest.install_hint else ""
        return AdapterResult(
            adapter_name=manifest.name,
            status=AdapterStatus.SKIPPED_TOOL_NOT_FOUND,
            facts=(),
            error=f"Binary '{manifest.command[0]}' not found{hint}",
        )

    # 2. Version check (CLI only)
    tool_version: str | None = None
    if _is_cli(manifest.command) and (manifest.min_version or manifest.max_version):
        tool_version = _detect_version(manifest.command[0])
        if tool_version is None or not _version_in_range(
            tool_version, manifest.min_version, manifest.max_version
        ):
            return AdapterResult(
                adapter_name=manifest.name,
                status=AdapterStatus.SKIPPED_VERSION_MISMATCH,
                facts=(),
                error=(
                    f"Version {tool_version!r} is outside required range "
                    f"[{manifest.min_version}, {manifest.max_version}]"
                ),
                tool_version=tool_version,
            )

    # 3. Invocation + normalization
    try:
        raw = _invoke(manifest, context)
        facts = manifest.normalize(raw, context)
        return AdapterResult(
            adapter_name=manifest.name,
            status=AdapterStatus.OK,
            facts=tuple(facts),
            tool_version=tool_version,
        )
    except Exception as exc:  # noqa: BLE001
        return AdapterResult(
            adapter_name=manifest.name,
            status=AdapterStatus.FAILED,
            facts=(),
            error=str(exc),
            tool_version=tool_version,
        )


def run_adapters(
    manifests: Sequence[AdapterManifest],
    context: AdapterContext,
) -> list[AdapterResult]:
    """Run all adapters concurrently and collect results.

    Failures of individual adapters are isolated — a single adapter crashing
    never prevents sibling adapters from running.  Results are returned in
    completion order (not submission order); callers that need a stable order
    should sort by adapter_name themselves.
    """
    with ThreadPoolExecutor(max_workers=min(len(manifests), 8) or 1) as pool:
        futures = {pool.submit(_run_one, m, context): m for m in manifests}
        return [f.result() for f in as_completed(futures)]
