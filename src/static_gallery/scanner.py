from __future__ import annotations

import os
from pathlib import Path

from static_gallery.model import IMAGE_EXTENSIONS, Node, NodeType


def _classify(path: Path) -> NodeType:
    ext = path.suffix.lower()
    if ext == ".md":
        return NodeType.MARKDOWN
    if ext in IMAGE_EXTENSIONS:
        return NodeType.IMAGE
    return NodeType.STATIC


def _ensure_dir(root: Node, rel: Path, dir_map: dict[Path, Node]) -> Node:
    for i in range(len(rel.parts)):
        partial = Path(*rel.parts[: i + 1])
        if partial not in dir_map:
            parent_path = partial.parent
            parent_node = (
                dir_map.get(parent_path, root) if parent_path != partial else root
            )
            child = Node(
                node_type=None, name=rel.parts[i], source=None, parent=parent_node
            )
            parent_node.children.append(child)
            dir_map[partial] = child
    return dir_map[rel]


def scan(source: Path, config_filename: str | None) -> Node:
    root = Node(node_type=None, name="", source=None, parent=None)
    dir_map: dict[Path, Node] = {}

    # Collect files grouped by their parent directory, pruning dotdirs
    dir_files: dict[Path, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_dir = Path(dirpath).relative_to(source)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if config_filename and rel_dir == Path(".") and name == config_filename:
                continue
            path = Path(dirpath) / name
            dir_files.setdefault(rel_dir, []).append(path)

    # Process each directory's files
    for parent_rel in sorted(dir_files):
        files = dir_files[parent_rel]

        if parent_rel == Path("."):
            dir_node = root
        else:
            dir_node = _ensure_dir(root, parent_rel, dir_map)

        # Separate index.md from other files
        index_file = None
        other_files = []
        for path in files:
            if path.name.lower() == "index.md":
                index_file = path
            else:
                other_files.append(path)

        # Collapse index.md into the directory node
        if index_file is not None:
            dir_node.node_type = NodeType.MARKDOWN
            dir_node.source = index_file

        # Collision resolution: collect markdown stems, demote colliding images
        md_stems: set[str] = set()
        if index_file is not None:
            md_stems.add("index")
        for path in other_files:
            if _classify(path) == NodeType.MARKDOWN:
                md_stems.add(path.stem.lower())

        # Create child nodes
        for path in other_files:
            file_type = _classify(path)
            if file_type == NodeType.IMAGE and path.stem.lower() in md_stems:
                file_type = NodeType.STATIC
            child = Node(
                node_type=file_type,
                name=path.stem,
                source=path,
                parent=dir_node,
            )
            dir_node.children.append(child)

    return root
