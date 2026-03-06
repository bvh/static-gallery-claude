from __future__ import annotations

import argparse
import sys
from pathlib import Path

from static_gallery.config import parse_config
from static_gallery.errors import GalleryError
from static_gallery.scanner import scan
from static_gallery.builder import build


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gallery",
        description="Static Gallery — a static site generator with image support.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.cwd(),
        help="source directory (default: current working directory)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="target directory (default: .public inside source)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="config file path (default: site.conf in source root)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="force full rebuild, ignoring file timestamps",
    )

    args = parser.parse_args()

    try:
        source = args.source.resolve()
        if not source.is_dir():
            raise GalleryError(f"Source directory does not exist: {source}")

        target = (args.target or source / ".public").resolve()
        config_path = (args.config or source / "site.conf").resolve()

        site_config = parse_config(config_path)

        target.mkdir(parents=True, exist_ok=True)

        config_filename = config_path.name if config_path.parent == source else None
        tree = scan(source, config_filename)

        build(tree, site_config, source, target,
              config_path=config_path, force=args.force)
    except GalleryError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
