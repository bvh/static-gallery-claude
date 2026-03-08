from __future__ import annotations

import argparse
import sys
from pathlib import Path

from static_gallery.config import parse_config
from static_gallery.errors import GalleryError
from static_gallery.scanner import scan
from static_gallery.builder import build
from static_gallery.sync import sync_target


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gallery",
        description="Static Gallery — a static site generator with image support.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
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
        "--theme",
        type=Path,
        default=None,
        help="theme directory (default: .theme inside source)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="force full rebuild, ignoring file timestamps",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="print build actions to stderr",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="show what would be built without writing any files",
    )
    parser.add_argument(
        "--stage",
        action="store_true",
        default=False,
        help="build and serve the site locally via HTTP",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port for the staging server (default: 8000)",
    )

    args = parser.parse_args()

    try:
        source, target, theme_dir, config_path, site_config = _resolve_dirs(args)
        verbose = args.verbose or args.dry_run

        if not args.dry_run:
            target.mkdir(parents=True, exist_ok=True)
        # Safe to skip mkdir in dry-run: is_up_to_date returns False for
        # nonexistent targets, so everything reports "Would build" correctly.

        config_filename = config_path.name if config_path.parent == source else None
        tree = scan(source, config_filename)

        expected = build(
            tree,
            site_config,
            source,
            target,
            config_path=config_path,
            force=args.force,
            theme_dir=theme_dir,
            verbose=verbose,
            dry_run=args.dry_run,
        )
        sync_target(target, expected, verbose=verbose, dry_run=args.dry_run)
    except GalleryError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    if args.stage:
        from functools import partial
        from http.server import HTTPServer, SimpleHTTPRequestHandler

        handler = partial(SimpleHTTPRequestHandler, directory=str(target))
        try:
            server = HTTPServer(("127.0.0.1", args.port), handler)
        except OSError as exc:
            print(f"Could not start server: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Serving at http://localhost:{args.port} — press Ctrl+C to stop")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def _resolve_dirs(
    args: argparse.Namespace,
) -> tuple[Path, Path, Path, Path, dict[str, str]]:
    # Step 1: Find and parse config
    if args.config is not None:
        config_path = args.config.resolve()
    elif args.source is not None:
        config_path = (args.source / "site.conf").resolve()
    else:
        config_path = (Path.cwd() / "site.conf").resolve()

    conf_dir = config_path.parent
    site_config = parse_config(config_path)

    # Step 2: Resolve source
    if args.source is not None:
        source = args.source.resolve()
    elif "source" in site_config:
        source = (conf_dir / site_config["source"]).resolve()
    else:
        source = conf_dir.resolve()

    if not source.is_dir():
        raise GalleryError(f"Source directory does not exist: {source}")

    # Step 3: Resolve target
    if args.target is not None:
        target = args.target.resolve()
    elif "target" in site_config:
        target = (conf_dir / site_config["target"]).resolve()
    else:
        target = (source / ".public").resolve()

    # Step 4: Validate target is not inside source (unless all parts are dotdirs)
    rel = target.relative_to(source).parts if target.is_relative_to(source) else None
    if rel is not None and (not rel or not all(part.startswith(".") for part in rel)):
        raise GalleryError(
            f"Target directory {target} is inside source directory {source}. "
            "Use a dotdir (e.g. .public) or a path outside the source tree."
        )

    # Step 5: Resolve theme
    if args.theme is not None:
        theme_dir = args.theme.resolve()
    elif "theme" in site_config:
        theme_dir = (conf_dir / site_config["theme"]).resolve()
    else:
        theme_dir = (source / ".theme").resolve()

    for key in ("source", "target", "theme"):
        site_config.pop(key, None)

    return source, target, theme_dir, config_path, site_config
