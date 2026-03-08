from __future__ import annotations

import sys
from pathlib import Path


def sync_target(
    target: Path,
    expected_paths: set[Path],
    *,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    if not target.exists():
        return

    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            if verbose:
                prefix = "Would remove" if dry_run else "Remove"
                print(f"{prefix}: {path}", file=sys.stderr)
            if not dry_run:
                path.rmdir()
        elif not path.is_dir() and path not in expected_paths:
            if verbose:
                prefix = "Would delete" if dry_run else "Delete"
                print(f"{prefix}: {path}", file=sys.stderr)
            if not dry_run:
                path.unlink()
