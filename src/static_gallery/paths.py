from __future__ import annotations

from pathlib import Path

from static_gallery.model import Node, NodeType


def node_segments(node: Node) -> list[str]:
    parts = []
    current = node
    while current is not None:
        if current.name:
            parts.append(current.name)
        current = current.parent
    parts.reverse()
    return parts


def has_sibling_dir(node: Node) -> bool:
    """Check if a sibling directory with the same name exists and has children.

    Returns False for parentless nodes (e.g. the root), which always get
    pretty URLs since there is no sibling to collide with.
    """
    if node.parent is None:
        return False
    for sibling in node.parent.children:
        if sibling is node:
            continue
        if sibling.node_type is None and sibling.name == node.name and sibling.children:
            return True
    return False


def content_rel_url(node: Node) -> str:
    """Relative URL for a content node: 'name/' or 'name.html'."""
    if has_sibling_dir(node):
        return node.name + ".html"
    return node.name + "/"


def content_asset_src(node: Node) -> str:
    """Relative src path for an image asset in listings.

    Only valid for IMAGE nodes (which always have a source file).
    """
    assert node.source is not None
    if has_sibling_dir(node):
        return node.source.name
    return node.name + "/" + node.source.name


def target_paths(
    node: Node, target: Path, *, has_listing: bool = False
) -> tuple[Path | None, Path | None]:
    segs = node_segments(node)
    prefix = Path(*segs) if segs else Path(".")

    if node.source is None:
        if has_listing and node.children:
            return target / prefix / "index.html", None
        return None, None

    if node.node_type == NodeType.MARKDOWN:
        if node.is_index:
            html = target / prefix / "index.html"
        elif has_sibling_dir(node):
            html = target / prefix.parent / (node.name + ".html")
        else:
            html = target / prefix / "index.html"
        return html, None

    elif node.node_type == NodeType.IMAGE:
        if has_sibling_dir(node):
            html = target / prefix.parent / (node.name + ".html")
            asset = target / prefix.parent / node.source.name
        else:
            html = target / prefix / "index.html"
            asset = target / prefix / node.source.name
        return html, asset

    else:  # STATIC
        asset = target / prefix.parent / node.source.name
        return None, asset
