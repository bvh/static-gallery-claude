from __future__ import annotations

import shutil
from importlib.metadata import version as _pkg_version
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
from static_gallery.shortcodes import expand_shortcodes
from static_gallery.errors import GalleryError
from static_gallery.model import IMAGE_EXTENSIONS, Node, NodeType

GENERATOR = {"name": "Static Gallery", "version": _pkg_version("static-gallery")}


def _breadcrumbs(node: Node, site_config: dict[str, str]) -> list[dict[str, str]]:
    ancestors = []
    current = node.parent
    while current is not None and current.name:
        ancestors.append(current.name)
        current = current.parent
    ancestors.reverse()

    crumbs: list[dict[str, str]] = [{"name": site_config.get("title", ""), "url": "/"}]
    path = ""
    for name in ancestors:
        path += name + "/"
        crumbs.append({"name": name, "url": "/" + path})
    return crumbs


def load_template(env: jinja2.Environment, name: str) -> jinja2.Template:
    try:
        return env.get_template(f"{name}.html")
    except jinja2.TemplateNotFound:
        raise GalleryError(f"Missing template: .theme/{name}.html")
    except jinja2.TemplateSyntaxError as exc:
        raise GalleryError(f"Template syntax error in .theme/{name}.html: {exc}")


def try_load_template(env: jinja2.Environment, name: str) -> jinja2.Template | None:
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
            title = stem_to_title(child.name)
            if child.source is not None:
                try:
                    text = child.source.read_text(encoding="utf-8")
                    fm, _ = parse_front_matter(text)
                    if "title" in fm:
                        title = fm["title"]
                except OSError:
                    pass
            url = child.name + ("/" if child.is_index else ".html")
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


def _image_siblings(
    node: Node, meta_cache: dict[Path, dict[str, dict]]
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    if node.parent is None:
        return None, None
    images = [c for c in node.parent.children if c.node_type == NodeType.IMAGE]
    try:
        idx = images.index(node)
    except ValueError:
        return None, None

    def _nav(n: Node) -> dict[str, str]:
        stem = n.source.stem
        meta = get_image_metadata(n.source, meta_cache)
        return {
            "url": n.name + ".html",
            "title": resolve_title(stem, meta),
            "src": n.source.name,
        }

    prev = _nav(images[idx - 1]) if idx > 0 else None
    nxt = _nav(images[idx + 1]) if idx < len(images) - 1 else None
    return prev, nxt


def build_listing(
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
        site=site_config,
        page={"title": title},
        children=children_data,
        breadcrumbs=_breadcrumbs(node, site_config),
        generator=GENERATOR,
    )

    html_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html_target.write_text(output, encoding="utf-8")
    except OSError as exc:
        raise GalleryError(f"Cannot write {html_target}: {exc}")


def build_markdown(
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
    page_context = {k: v for k, v in metadata.items() if k != "type"}
    template = load_template(env, template_type)

    output = template.render(
        site=site_config,
        page=page_context,
        content=Markup(html_content),
        breadcrumbs=_breadcrumbs(node, site_config),
        generator=GENERATOR,
    )

    html_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html_target.write_text(output, encoding="utf-8")
    except OSError as exc:
        raise GalleryError(f"Cannot write {html_target}: {exc}")


def build_image(
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
        template = load_template(env, "image")
        prev, nxt = _image_siblings(node, meta_cache)

        output = template.render(
            site=site_config,
            page=metadata,
            content=filename,
            breadcrumbs=_breadcrumbs(node, site_config),
            prev=prev,
            next=nxt,
            generator=GENERATOR,
        )

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


def build_static_file(source: Path, target: Path) -> None:
    """Copy a file to target. Like build_static but without Node or image stripping."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise GalleryError(f"Cannot copy {source} to {target}: {exc}")


def build_static(node: Node, asset_target: Path) -> None:
    asset_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if node.source.suffix.lower() in IMAGE_EXTENSIONS:
            copy_image_stripped(node.source, asset_target)
        else:
            shutil.copy2(node.source, asset_target)
    except OSError as exc:
        raise GalleryError(f"Cannot copy {node.source} to {asset_target}: {exc}")
