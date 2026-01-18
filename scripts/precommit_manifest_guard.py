#!/usr/bin/env python3
"""Fail when frontend/backend changes lack their manifest updates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def touched_directory(files: list[Path], directory: str) -> bool:
    return any(parts and parts[0] == directory for parts in (path.parts for path in files))


def manifest_present(files: list[Path], manifest: Path) -> bool:
    return manifest in files


def main() -> None:
    staged = get_staged_files()
    checks: list[str] = []

    frontend_manifest = Path("frontend") / "package.json"
    backend_manifest = Path("backend") / "pyproject.toml"

    if touched_directory(staged, "frontend") and not manifest_present(staged, frontend_manifest):
        checks.append(
            "frontend changes are staged without a matching update to frontend/package.json"
        )

    if touched_directory(staged, "backend") and not manifest_present(staged, backend_manifest):
        checks.append(
            "backend changes are staged without a matching update to backend/pyproject.toml"
        )

    if checks:
        print("ERROR: Manifest updates required")
        for item in checks:
            print(f"  - {item}")
        print("Please bump the relevant manifest before committing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
