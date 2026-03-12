from pathlib import Path

from static_gallery.model import Node, NodeType
from static_gallery.render import _breadcrumbs, _image_siblings, _normalize_date_iso

from conftest import EMPTY_META as _EMPTY_META


class TestBreadcrumbs:
    def test_root_page(self):
        root = Node(node_type=None, name="", source=None, parent=None)
        child = Node(
            node_type=NodeType.MARKDOWN,
            name="about",
            source=Path("about.md"),
            parent=root,
        )
        root.children.append(child)

        crumbs = _breadcrumbs(child, {"title": "My Site"})
        assert crumbs == [{"name": "My Site", "url": "/"}]

    def test_nested_page(self):
        root = Node(node_type=None, name="", source=None, parent=None)
        photos = Node(node_type=None, name="photos", source=None, parent=root)
        root.children.append(photos)
        child = Node(
            node_type=NodeType.IMAGE,
            name="sunset",
            source=Path("sunset.jpg"),
            parent=photos,
        )
        photos.children.append(child)

        crumbs = _breadcrumbs(child, {"title": "My Site"})
        assert crumbs == [
            {"name": "My Site", "url": "/"},
            {"name": "photos", "url": "/photos/"},
        ]

    def test_deeply_nested(self):
        root = Node(node_type=None, name="", source=None, parent=None)
        a = Node(node_type=None, name="a", source=None, parent=root)
        root.children.append(a)
        b = Node(node_type=None, name="b", source=None, parent=a)
        a.children.append(b)
        child = Node(
            node_type=NodeType.MARKDOWN, name="page", source=Path("page.md"), parent=b
        )
        b.children.append(child)

        crumbs = _breadcrumbs(child, {"title": "Site"})
        assert crumbs == [
            {"name": "Site", "url": "/"},
            {"name": "a", "url": "/a/"},
            {"name": "b", "url": "/a/b/"},
        ]


class TestImageSiblings:
    def _make_image_gallery(self, source, *names):
        """Create parent node with image children."""
        parent = Node(node_type=None, name="photos", source=None, parent=None)
        children = []
        for name in names:
            stem = Path(name).stem
            img_path = source / name
            img_path.write_bytes(b"fake")
            child = Node(
                node_type=NodeType.IMAGE, name=stem, source=img_path, parent=parent
            )
            parent.children.append(child)
            children.append(child)
        return parent, children

    def test_middle_gets_both(self, tmp_path):
        parent, children = self._make_image_gallery(tmp_path, "a.jpg", "b.jpg", "c.jpg")
        mc = {c.source: _EMPTY_META for c in children}
        prev, nxt = _image_siblings(children[1], mc)
        assert prev is not None
        assert nxt is not None
        assert prev["url"] == "a/"
        assert nxt["url"] == "c/"

    def test_first_gets_only_next(self, tmp_path):
        parent, children = self._make_image_gallery(tmp_path, "a.jpg", "b.jpg", "c.jpg")
        mc = {c.source: _EMPTY_META for c in children}
        prev, nxt = _image_siblings(children[0], mc)
        assert prev is None
        assert nxt is not None
        assert nxt["url"] == "b/"

    def test_last_gets_only_prev(self, tmp_path):
        parent, children = self._make_image_gallery(tmp_path, "a.jpg", "b.jpg", "c.jpg")
        mc = {c.source: _EMPTY_META for c in children}
        prev, nxt = _image_siblings(children[2], mc)
        assert prev is not None
        assert prev["url"] == "b/"
        assert nxt is None

    def test_single_image_gets_none(self, tmp_path):
        parent, children = self._make_image_gallery(tmp_path, "a.jpg")
        mc = {c.source: _EMPTY_META for c in children}
        prev, nxt = _image_siblings(children[0], mc)
        assert prev is None
        assert nxt is None

    def test_no_parent_returns_none(self, tmp_path):
        img = tmp_path / "solo.jpg"
        img.write_bytes(b"fake")
        node = Node(node_type=NodeType.IMAGE, name="solo", source=img, parent=None)
        prev, nxt = _image_siblings(node, {})
        assert prev is None
        assert nxt is None


class TestNormalizeDateIso:
    def test_full_iso_with_z(self):
        assert _normalize_date_iso("2024-03-15T10:30:00Z") == "2024-03-15T10:30:00Z"

    def test_iso_without_z(self):
        assert _normalize_date_iso("2024-03-15T10:30:00") == "2024-03-15T10:30:00Z"

    def test_datetime_with_space(self):
        assert _normalize_date_iso("2024-03-15 10:30:00") == "2024-03-15T10:30:00Z"

    def test_date_only(self):
        assert _normalize_date_iso("2024-03-15") == "2024-03-15T00:00:00Z"

    def test_invalid_returns_none(self):
        assert _normalize_date_iso("not a date") is None

    def test_partial_date_returns_none(self):
        assert _normalize_date_iso("2024-03") is None
