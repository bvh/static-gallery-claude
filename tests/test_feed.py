import pytest
from unittest.mock import patch

from static_gallery.builder import build
from static_gallery.errors import GalleryError
from static_gallery.metadata import resolve_date_iso
from static_gallery.model import Node, NodeType
from static_gallery.render import _normalize_date_iso
from static_gallery.sync import sync_target

from conftest import setup_theme as _setup_theme

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{{ site.title }}</title>
  <link href="{{ site.url }}" rel="alternate"/>
  <link href="{{ site.url }}feed.xml" rel="self"/>
  <id>{{ site.url }}</id>
  {% if items %}<updated>{{ items[0].date }}</updated>{% endif %}
  {% for item in items %}
  <entry>
    <title>{{ item.title }}</title>
    <link href="{{ item.url }}" rel="alternate"/>
    <id>{{ item.url }}</id>
    <updated>{{ item.date }}</updated>
  </entry>
  {% endfor %}
</feed>"""


def _site_config():
    return {"title": "Test Site", "url": "https://example.com/", "language": "en-us"}


def _setup_theme_with_feed(source, **kwargs):
    _setup_theme(source, **kwargs)
    (source / ".theme" / "feed.xml").write_text(FEED_TEMPLATE)


def _make_tree(*children):
    root = Node(node_type=None, name="", source=None, parent=None)
    for c in children:
        c.parent = root
        root.children.append(c)
    return root


def _make_child(node_type, name, source, parent=None):
    return Node(node_type=node_type, name=name, source=source, parent=parent)


class TestResolveDateIso:
    def test_returns_iso_from_exif(self):
        meta = {
            "exif": {"DateTimeOriginal": "2024:03:15 10:30:00"},
            "iptc": {},
            "xmp": {},
        }
        assert resolve_date_iso(meta) == "2024-03-15T10:30:00Z"

    def test_returns_none_without_exif(self):
        meta = {"exif": {}, "iptc": {}, "xmp": {}}
        assert resolve_date_iso(meta) is None

    def test_returns_none_for_invalid_date(self):
        meta = {"exif": {"DateTimeOriginal": "not-a-date"}, "iptc": {}, "xmp": {}}
        assert resolve_date_iso(meta) is None


class TestBuildFeed:
    def test_generates_feed_with_dated_markdown(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: My Post\nDate: 2024-03-15T10:00:00Z\n\nContent here.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target)

        feed = target / "feed.xml"
        assert feed.exists()
        content = feed.read_text()
        assert "<title>My Post</title>" in content
        assert "https://example.com/post.html" in content
        assert "2024-03-15T10:00:00Z" in content

    def test_excludes_undated_markdown(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "about.md"
        md.write_text("Title: About\n\nNo date here.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "about", md))
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "<entry>" not in content

    def test_no_feed_without_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)  # no feed template

        md = source / "post.md"
        md.write_text("Title: Post\nDate: 2024-01-01T00:00:00Z\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target)

        assert not (target / "feed.xml").exists()

    def test_feed_survives_sync(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: Post\nDate: 2024-01-01T00:00:00Z\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        expected = build(tree, _site_config(), source, target)
        sync_target(target, expected)

        assert (target / "feed.xml").exists()

    def test_feed_sorted_by_date_descending(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        old = source / "old.md"
        old.write_text("Title: Old Post\nDate: 2024-01-01T00:00:00Z\n\nOld.")
        new = source / "new.md"
        new.write_text("Title: New Post\nDate: 2024-06-15T00:00:00Z\n\nNew.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "old", old),
            _make_child(NodeType.MARKDOWN, "new", new),
        )
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        new_pos = content.index("New Post")
        old_pos = content.index("Old Post")
        assert new_pos < old_pos

    def test_feed_with_image_exif_date(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        img = source / "sunset.jpg"
        img.write_bytes(b"fake image data")

        tree = _make_tree(_make_child(NodeType.IMAGE, "sunset", img))

        meta = {
            "exif": {"DateTimeOriginal": "2024:07:20 18:30:00"},
            "iptc": {"ObjectName": "Golden Sunset"},
            "xmp": {},
        }
        with patch("static_gallery.metadata.read_image_metadata", return_value=meta):
            build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "<title>Golden Sunset</title>" in content
        assert "2024-07-20T18:30:00Z" in content
        assert "https://example.com/sunset.html" in content

    def test_feed_excludes_image_without_exif_date(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        img = source / "photo.jpg"
        img.write_bytes(b"fake")

        tree = _make_tree(_make_child(NodeType.IMAGE, "photo", img))

        meta = {"exif": {}, "iptc": {}, "xmp": {}}
        with patch("static_gallery.metadata.read_image_metadata", return_value=meta):
            build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "<entry>" not in content

    def test_feed_limit(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        children = []
        for i in range(5):
            md = source / f"post{i}.md"
            md.write_text(
                f"Title: Post {i}\nDate: 2024-01-{i + 1:02d}T00:00:00Z\n\nHi."
            )
            children.append(_make_child(NodeType.MARKDOWN, f"post{i}", md))

        tree = _make_tree(*children)
        config = {**_site_config(), "feed_limit": "3"}
        build(tree, config, source, target)

        content = (target / "feed.xml").read_text()
        assert content.count("<entry>") == 3

    def test_feed_index_md_url(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        sub = source / "blog"
        sub.mkdir()
        md = sub / "index.md"
        md.write_text("Title: Blog\nDate: 2024-05-01T00:00:00Z\n\nBlog content.")

        blog_node = Node(
            node_type=NodeType.MARKDOWN, name="blog", source=md, parent=None
        )
        tree = _make_tree(blog_node)
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "https://example.com/blog/" in content

    def test_feed_nested_content(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        (source / "blog").mkdir()
        md = source / "blog" / "post.md"
        md.write_text("Title: Nested\nDate: 2024-02-01T00:00:00Z\n\nNested post.")

        blog = Node(node_type=None, name="blog", source=None, parent=None)
        post = _make_child(NodeType.MARKDOWN, "post", md, parent=blog)
        blog.children.append(post)
        tree = _make_tree(blog)
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "https://example.com/blog/post.html" in content

    def test_date_only_format_normalized(self, tmp_path):
        """Date: 2024-03-15 should be normalized to full ISO 8601."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: Post\nDate: 2024-03-15\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "2024-03-15T00:00:00Z" in content

    def test_unparseable_date_excluded(self, tmp_path):
        """A date that can't be parsed should be silently excluded."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: Post\nDate: March 15, 2024\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        assert "<entry>" not in content

    def test_invalid_feed_limit_raises(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: Post\nDate: 2024-01-01\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        config = {**_site_config(), "feed_limit": "all"}
        with pytest.raises(GalleryError, match="Invalid feed_limit"):
            build(tree, config, source, target)

    def test_feed_xml_not_autoescaped(self, tmp_path):
        """XML templates should not have HTML autoescape applied."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme_with_feed(source)

        md = source / "post.md"
        md.write_text("Title: Tom & Jerry\nDate: 2024-01-01T00:00:00Z\n\nHi.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target)

        content = (target / "feed.xml").read_text()
        # Should be raw & not &amp; since autoescape is off for .xml
        assert "Tom & Jerry" in content
        assert "Tom &amp; Jerry" not in content


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
