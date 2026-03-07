from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import jinja2
from markupsafe import Markup
import mistletoe

from static_gallery.config import parse_front_matter
from static_gallery.metadata import (
    copy_image_stripped,
    get_image_metadata,
    resolve_alt,
    resolve_title,
    stem_to_title,
)
from static_gallery.shortcodes import expand_shortcodes, shortcode_dependencies
from static_gallery.errors import GalleryError
from static_gallery.model import IMAGE_EXTENSIONS, Node, NodeType


def _compute_global_mtime(theme_dir: Path, config_path: Path | None) -> float:
    mtime = 0.0
    if theme_dir.is_dir():
        for entry in theme_dir.rglob("*"):
            if entry.is_file():
                mtime = max(mtime, entry.stat().st_mtime)
    if config_path is not None and config_path.is_file():
        mtime = max(mtime, config_path.stat().st_mtime)
    return mtime


def _is_up_to_date(
    target_path: Path,
    source_path: Path,
    global_mtime: float,
    is_html: bool,
    *,
    extra_mtime: float = 0.0,
) -> bool:
    if not target_path.exists():
        return False
    target_mtime = target_path.stat().st_mtime
    if is_html:
        return target_mtime >= max(
            source_path.stat().st_mtime, global_mtime, extra_mtime
        )
    return target_mtime >= source_path.stat().st_mtime


def _node_segments(node: Node) -> list[str]:
    parts = []
    current = node
    while current is not None:
        if current.name:
            parts.append(current.name)
        current = current.parent
    parts.reverse()
    return parts


def _target_paths(
    node: Node, target: Path, *, has_listing: bool = False
) -> tuple[Path | None, Path | None]:
    segs = _node_segments(node)
    prefix = Path(*segs) if segs else Path(".")

    if node.source is None:
        if has_listing and node.children:
            return target / prefix / "index.html", None
        return None, None

    is_index = node.source.name.lower() == "index.md"

    if node.node_type == NodeType.MARKDOWN:
        if is_index:
            html = target / prefix / "index.html"
        else:
            html = target / prefix.parent / (node.name + ".html")
        return html, None

    elif node.node_type == NodeType.IMAGE:
        html = target / prefix.parent / (node.name + ".html")
        asset = target / prefix.parent / node.source.name
        return html, asset

    else:  # STATIC
        asset = target / prefix.parent / node.source.name
        return None, asset


def build(
    tree: Node,
    site_config: dict[str, str],
    source: Path,
    target: Path,
    *,
    config_path: Path | None = None,
    force: bool = False,
    theme_dir: Path | None = None,
) -> None:
    if theme_dir is None:
        theme_dir = source / ".theme"
    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(theme_dir)),
            autoescape=True,
        )
    except Exception as exc:
        raise GalleryError(f"Cannot load templates from {theme_dir}: {exc}")

    listing_template = _try_load_template(env, "listing")

    if force:
        global_mtime = float("inf")
    else:
        global_mtime = _compute_global_mtime(theme_dir, config_path)

    expected: set[Path] = set()
    meta_cache: dict[Path, dict[str, dict]] = {}
    _build_node(
        tree,
        site_config,
        env,
        target,
        expected,
        global_mtime,
        source=source,
        listing_template=listing_template,
        meta_cache=meta_cache,
    )
    _sync_target(target, expected)


def _build_node(
    node: Node,
    site_config: dict[str, str],
    env: jinja2.Environment,
    target: Path,
    expected: set[Path],
    global_mtime: float,
    *,
    source: Path,
    listing_template: jinja2.Template | None = None,
    meta_cache: dict[Path, dict[str, dict]],
) -> None:
    has_listing = listing_template is not None
    html_target, asset_target = _target_paths(node, target, has_listing=has_listing)

    if html_target is not None:
        expected.add(html_target)
    if asset_target is not None:
        expected.add(asset_target)

    if node.node_type == NodeType.MARKDOWN and node.source is not None:
        # Read source early to check shortcode dependency mtimes
        try:
            text = node.source.read_text(encoding="utf-8")
        except OSError as exc:
            raise GalleryError(f"Cannot read {node.source}: {exc}")
        deps = shortcode_dependencies(text, node.source.parent, source)
        try:
            dep_mtime = max((p.stat().st_mtime for p in deps), default=0.0)
        except OSError as exc:
            raise GalleryError(f"Cannot stat shortcode dependency: {exc}")
        if not _is_up_to_date(
            html_target, node.source, global_mtime, is_html=True, extra_mtime=dep_mtime
        ):
            _build_markdown(
                node, html_target, site_config, env, meta_cache, source, text
            )
    elif node.node_type == NodeType.IMAGE:
        skip_html = _is_up_to_date(html_target, node.source, global_mtime, is_html=True)
        skip_asset = _is_up_to_date(
            asset_target, node.source, global_mtime, is_html=False
        )
        if not skip_html or not skip_asset:
            _build_image(
                node,
                html_target,
                asset_target,
                site_config,
                env,
                meta_cache,
                skip_html=skip_html,
                skip_asset=skip_asset,
            )
    elif node.node_type == NodeType.STATIC:
        if not _is_up_to_date(asset_target, node.source, global_mtime, is_html=False):
            _build_static(node, asset_target)
    elif node.node_type is None and node.children and has_listing:
        source_dir = source / Path(*_node_segments(node)) if node.name else source
        if not _is_up_to_date(html_target, source_dir, global_mtime, is_html=True):
            _build_listing(node, html_target, site_config, listing_template, meta_cache)

    for child in node.children:
        _build_node(
            child,
            site_config,
            env,
            target,
            expected,
            global_mtime,
            source=source,
            listing_template=listing_template,
            meta_cache=meta_cache,
        )


def _load_template(env: jinja2.Environment, name: str) -> jinja2.Template:
    try:
        return env.get_template(f"{name}.html")
    except jinja2.TemplateNotFound:
        raise GalleryError(f"Missing template: .theme/{name}.html")
    except jinja2.TemplateSyntaxError as exc:
        raise GalleryError(f"Template syntax error in .theme/{name}.html: {exc}")


def _try_load_template(env: jinja2.Environment, name: str) -> jinja2.Template | None:
    try:
        return env.get_template(f"{name}.html")
    except jinja2.TemplateNotFound:
        return None
    except jinja2.TemplateSyntaxError as exc:
        raise GalleryError(f"Template syntax error in .theme/{name}.html: {exc}")


def _collect_children_data(
    node: Node, meta_cache: dict[Path, dict[str, dict]]
) -> dict[str, list[dict[str, Any]]]:
    directories: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []

    for child in node.children:
        if child.node_type is None and child.children:
            directories.append({"name": child.name, "url": child.name + "/"})
        elif child.node_type == NodeType.MARKDOWN:
            is_index = (
                child.source is not None and child.source.name.lower() == "index.md"
            )
            title = stem_to_title(child.name)
            url = child.name + ("/" if is_index else ".html")
            pages.append({"name": child.name, "title": title, "url": url})
        elif child.node_type == NodeType.IMAGE:
            stem = child.source.stem
            image_meta = get_image_metadata(child.source, meta_cache)
            title = resolve_title(stem, image_meta)
            alt = resolve_alt(stem, image_meta)
            images.append(
                {
                    "filename": child.source.name,
                    "stem": stem,
                    "title": title,
                    "alt": alt,
                    "url": child.name + ".html",
                    "src": child.source.name,
                    **image_meta,
                }
            )

    return {"directories": directories, "pages": pages, "images": images}


def _build_listing(
    node: Node,
    html_target: Path,
    site_config: dict[str, str],
    listing_template: jinja2.Template,
    meta_cache: dict[Path, dict[str, dict]],
) -> None:
    children_data = _collect_children_data(node, meta_cache)
    if node.name:
        title = stem_to_title(node.name)
    else:
        title = site_config.get("title", "")

    output = listing_template.render(
        site=site_config, page={"title": title}, children=children_data
    )

    html_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html_target.write_text(output, encoding="utf-8")
    except OSError as exc:
        raise GalleryError(f"Cannot write {html_target}: {exc}")


def _build_markdown(
    node: Node,
    html_target: Path,
    site_config: dict[str, str],
    env: jinja2.Environment,
    meta_cache: dict[Path, dict[str, dict]],
    source_root: Path,
    text: str,
) -> None:
    metadata, body = parse_front_matter(text)
    body = expand_shortcodes(body, env, node.source.parent, meta_cache, source_root)
    html_content = mistletoe.markdown(body)

    template_type = metadata.get("type", "page")
    if "type" in metadata:
        del metadata["type"]
    template = _load_template(env, template_type)

    output = template.render(
        site=site_config, page=metadata, content=Markup(html_content)
    )

    html_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html_target.write_text(output, encoding="utf-8")
    except OSError as exc:
        raise GalleryError(f"Cannot write {html_target}: {exc}")


def _build_image(
    node: Node,
    html_target: Path,
    asset_target: Path,
    site_config: dict[str, str],
    env: jinja2.Environment,
    meta_cache: dict[Path, dict[str, dict]],
    *,
    skip_html: bool = False,
    skip_asset: bool = False,
) -> None:
    if not skip_html:
        stem = node.source.stem
        filename = node.source.name
        image_meta = get_image_metadata(node.source, meta_cache)
        title = resolve_title(stem, image_meta)

        metadata = {"title": title, "src": filename, **image_meta}
        template = _load_template(env, "image")

        output = template.render(site=site_config, page=metadata, content=filename)

        html_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            html_target.write_text(output, encoding="utf-8")
        except OSError as exc:
            raise GalleryError(f"Cannot write {html_target}: {exc}")

    if not skip_asset:
        asset_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            copy_image_stripped(node.source, asset_target)
        except OSError as exc:
            raise GalleryError(f"Cannot copy {node.source} to {asset_target}: {exc}")


def _build_static(node: Node, asset_target: Path) -> None:
    asset_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if node.source.suffix.lower() in IMAGE_EXTENSIONS:
            copy_image_stripped(node.source, asset_target)
        else:
            shutil.copy2(node.source, asset_target)
    except OSError as exc:
        raise GalleryError(f"Cannot copy {node.source} to {asset_target}: {exc}")


def _sync_target(target: Path, expected_paths: set[Path]) -> None:
    if not target.exists():
        return

    for path in sorted(target.rglob("*"), reverse=True):
        if path.is_file() and path not in expected_paths:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
