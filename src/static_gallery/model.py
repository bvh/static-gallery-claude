from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".webp", ".png"}


class NodeType(Enum):
    MARKDOWN = auto()
    IMAGE = auto()
    STATIC = auto()


@dataclass
class Node:
    node_type: NodeType | None
    name: str
    source: Path | None
    parent: Node | None = field(default=None, repr=False)
    children: list[Node] = field(default_factory=list)
