from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import jinja2

from static_gallery.errors import GalleryError
from static_gallery.freshness import compute_global_mtime, is_up_to_date
from static_gallery.model import Node, NodeType
from static_gallery.paths import node_segments, target_paths
from static_gallery.render import (
    build_feed,
    build_image,
    build_listing,
    build_markdown,
    build_static,
    build_static_file,
    try_load_template,
)
from static_gallery.shortcodes import shortcode_dependencies


@dataclass
class BuildContext:
    env: jinja2.Environment
    site_config: dict[str, str]
    source: Path
    target: Path
    global_mtime: float
    meta_cache: dict[Path, dict[str, dict]] = field(default_factory=dict)
    expected: set[Path] = field(default_factory=set)
    listing_template: jinja2.Template | None = None
    verbose: bool = False
    dry_run: bool = False


def build(
    tree: Node,
    site_config: dict[str, str],
    source: Path,
    target: Path,
    *,
    config_path: Path | None = None,
    force: bool = False,
    theme_dir: Path | None = None,
    verbose: bool = False,
    dry_run: bool = False,
) -> set[Path]:
    if theme_dir is None:
        theme_dir = source / ".theme"
    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(theme_dir)),
            autoescape=jinja2.select_autoescape(
                enabled_extensions=("html",),
                default_for_string=True,
            ),
        )
    except Exception as exc:
        raise GalleryError(f"Cannot load templates from {theme_dir}: {exc}")

    if force:
        global_mtime = float("inf")
    else:
        global_mtime = compute_global_mtime(theme_dir, config_path)

    ctx = BuildContext(
        env=env,
        site_config=site_config,
        source=source,
        target=target,
        global_mtime=global_mtime,
        listing_template=try_load_template(env, "listing"),
        verbose=verbose,
        dry_run=dry_run,
    )

    _copy_theme_assets(ctx, theme_dir)
    _build_node(tree, ctx)

    feed_template = try_load_template(env, "feed", ext="xml")
    if feed_template is not None:
        feed_path = target / "feed.xml"
        ctx.expected.add(feed_path)
        if ctx.verbose:
            prefix = "Would build" if ctx.dry_run else "Build"
            print(f"{prefix}: {feed_path}", file=sys.stderr)
        if not ctx.dry_run:
            build_feed(tree, site_config, feed_template, ctx.meta_cache, target)

    return ctx.expected


def _copy_theme_assets(ctx: BuildContext, theme_dir: Path) -> None:
    static_dir = theme_dir / "static"
    if not static_dir.is_dir():
        return
    for source_file in static_dir.rglob("*"):
        if not source_file.is_file():
            continue
        rel = source_file.relative_to(static_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        target_file = ctx.target / rel
        ctx.expected.add(target_file)
        if not is_up_to_date(target_file, source_file, ctx.global_mtime, is_html=False):
            if ctx.verbose:
                prefix = "Would build" if ctx.dry_run else "Build"
                print(f"{prefix}: {target_file}", file=sys.stderr)
            if not ctx.dry_run:
                build_static_file(source_file, target_file)
        elif ctx.verbose:
            print(f"Skip: {target_file}", file=sys.stderr)


def _build_node(node: Node, ctx: BuildContext) -> None:
    has_listing = ctx.listing_template is not None
    html_target, asset_target = target_paths(node, ctx.target, has_listing=has_listing)

    if html_target is not None:
        ctx.expected.add(html_target)
    if asset_target is not None:
        ctx.expected.add(asset_target)

    if node.node_type == NodeType.MARKDOWN and node.source is not None:
        try:
            text = node.source.read_text(encoding="utf-8")
        except OSError as exc:
            raise GalleryError(f"Cannot read {node.source}: {exc}")
        deps = shortcode_dependencies(text, node.source.parent, ctx.source)
        try:
            dep_mtime = max((p.stat().st_mtime for p in deps), default=0.0)
        except OSError as exc:
            raise GalleryError(f"Cannot stat shortcode dependency: {exc}")
        if not is_up_to_date(
            html_target,
            node.source,
            ctx.global_mtime,
            is_html=True,
            extra_mtime=dep_mtime,
        ):
            if ctx.verbose:
                prefix = "Would build" if ctx.dry_run else "Build"
                print(f"{prefix}: {html_target}", file=sys.stderr)
            if not ctx.dry_run:
                build_markdown(
                    node,
                    html_target,
                    ctx.site_config,
                    ctx.env,
                    ctx.meta_cache,
                    ctx.source,
                    text,
                )
        elif ctx.verbose:
            print(f"Skip: {html_target}", file=sys.stderr)
    elif node.node_type == NodeType.IMAGE:
        skip_html = is_up_to_date(
            html_target, node.source, ctx.global_mtime, is_html=True
        )
        skip_asset = is_up_to_date(
            asset_target, node.source, ctx.global_mtime, is_html=False
        )
        if not skip_html or not skip_asset:
            if ctx.verbose:
                prefix = "Would build" if ctx.dry_run else "Build"
                if not skip_html:
                    print(f"{prefix}: {html_target}", file=sys.stderr)
                if not skip_asset:
                    print(f"{prefix}: {asset_target}", file=sys.stderr)
            if not ctx.dry_run:
                build_image(
                    node,
                    html_target,
                    asset_target,
                    ctx.site_config,
                    ctx.env,
                    ctx.meta_cache,
                    skip_html=skip_html,
                    skip_asset=skip_asset,
                )
        elif ctx.verbose:
            print(f"Skip: {html_target}", file=sys.stderr)
            print(f"Skip: {asset_target}", file=sys.stderr)
    elif node.node_type == NodeType.STATIC:
        if not is_up_to_date(
            asset_target, node.source, ctx.global_mtime, is_html=False
        ):
            if ctx.verbose:
                prefix = "Would build" if ctx.dry_run else "Build"
                print(f"{prefix}: {asset_target}", file=sys.stderr)
            if not ctx.dry_run:
                build_static(node, asset_target)
        elif ctx.verbose:
            print(f"Skip: {asset_target}", file=sys.stderr)
    elif node.node_type is None and node.children and has_listing:
        source_dir = (
            ctx.source / Path(*node_segments(node)) if node.name else ctx.source
        )
        if not is_up_to_date(html_target, source_dir, ctx.global_mtime, is_html=True):
            if ctx.verbose:
                prefix = "Would build" if ctx.dry_run else "Build"
                print(f"{prefix}: {html_target}", file=sys.stderr)
            if not ctx.dry_run:
                build_listing(
                    node,
                    html_target,
                    ctx.site_config,
                    ctx.listing_template,
                    ctx.meta_cache,
                )
        elif ctx.verbose:
            print(f"Skip: {html_target}", file=sys.stderr)

    for child in node.children:
        _build_node(child, ctx)
