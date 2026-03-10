"""Tests for v1.0 features: shortcode escaping, EXIF date sorting, real titles,
breadcrumbs, prev/next navigation, verbose output, and dry-run."""

import os
from pathlib import Path

import jinja2
import pytest

from static_gallery.builder import build
from static_gallery.metadata import resolve_date
from static_gallery.model import Node, NodeType
from static_gallery.render import _breadcrumbs, _image_siblings
from static_gallery.shortcodes import expand_shortcodes, shortcode_dependencies
from static_gallery.sync import sync_target

from conftest import (
    LISTING_TEMPLATE,
    setup_theme as _setup_theme,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_META = {"exif": {}, "iptc": {}, "xmp": {}}

IMAGE_TPL = '<img src="{{ path }}" alt="{{ alt }}">'
GALLERY_TPL = (
    "{% for image in images %}"
    "{{ image.filename }}:{{ image.page_url }}"
    "{% if not loop.last %},{% endif %}"
    "{% endfor %}"
)


@pytest.fixture
def env(tmp_path):
    tpl_dir = tmp_path / "shortcodes"
    tpl_dir.mkdir()
    (tpl_dir / "image.html").write_text(IMAGE_TPL)
    (tpl_dir / "gallery.html").write_text(GALLERY_TPL)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmp_path)),
        autoescape=True,
    )


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    return d


def _img(src, name="photo.jpg", meta_cache=None):
    f = src / name
    f.write_bytes(b"fake")
    if meta_cache is not None:
        meta_cache[f] = _EMPTY_META
    return f


def _site_config():
    return {"title": "Test Site", "url": "https://example.com/", "language": "en-us"}


def _make_tree(*children):
    root = Node(node_type=None, name="", source=None, parent=None)
    for c in children:
        c.parent = root
        root.children.append(c)
    return root


def _make_child(node_type, name, source, parent=None):
    return Node(node_type=node_type, name=name, source=source, parent=parent)


# ===========================================================================
# Feature 1: Shortcode Escaping
# ===========================================================================


class TestShortcodeEscaping:
    def test_escaped_produces_literal(self, env, src):
        result = expand_shortcodes("\\<<not a shortcode>>", env, src, source_root=src)
        assert result == "<<not a shortcode>>"

    def test_mixed_escaped_and_real(self, env, src):
        _img(src)
        result = expand_shortcodes(
            "\\<<literal>> and <<photo.jpg>>", env, src, source_root=src
        )
        assert "<<literal>>" in result
        assert '<img src="photo.jpg"' in result

    def test_multiple_escaped(self, env, src):
        result = expand_shortcodes("\\<<a>> then \\<<b>>", env, src, source_root=src)
        assert result == "<<a>> then <<b>>"

    def test_dependencies_skip_escaped(self, src):
        (src / "example.py").write_text("print('hi')")
        body = "\\<<example.py>> and <<example.py>>"
        deps = shortcode_dependencies(body, src)
        assert deps == {src / "example.py"}

    def test_dependencies_only_escaped(self, src):
        (src / "example.py").write_text("print('hi')")
        body = "\\<<example.py>>"
        deps = shortcode_dependencies(body, src)
        assert deps == set()


# ===========================================================================
# Feature 2: EXIF Date Sorting
# ===========================================================================


class TestExifDateSorting:
    def test_resolve_date_uses_exif(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"fake")
        meta = {
            "exif": {"DateTimeOriginal": "2020:06:15 10:30:00"},
            "iptc": {},
            "xmp": {},
        }
        ts = resolve_date(f, meta)
        import datetime

        expected = datetime.datetime(2020, 6, 15, 10, 30, 0).timestamp()
        assert ts == expected

    def test_resolve_date_falls_back_to_mtime(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"fake")
        meta = {"exif": {}, "iptc": {}, "xmp": {}}
        ts = resolve_date(f, meta)
        assert ts == pytest.approx(os.path.getmtime(f), abs=1)

    def test_resolve_date_bad_format_falls_back(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"fake")
        meta = {"exif": {"DateTimeOriginal": "not-a-date"}, "iptc": {}, "xmp": {}}
        ts = resolve_date(f, meta)
        assert ts == pytest.approx(os.path.getmtime(f), abs=1)

    def test_gallery_sort_date_uses_exif(self, env, src):
        mc = {}
        # "old" by filename but newer by EXIF date
        _img(src, "alpha.jpg", mc)
        _img(src, "beta.jpg", mc)
        # alpha has a newer EXIF date than beta
        mc[src / "alpha.jpg"] = {
            "exif": {"DateTimeOriginal": "2025:01:01 12:00:00"},
            "iptc": {},
            "xmp": {},
        }
        mc[src / "beta.jpg"] = {
            "exif": {"DateTimeOriginal": "2020:01:01 12:00:00"},
            "iptc": {},
            "xmp": {},
        }
        result = expand_shortcodes(
            "<<gallery sort=date>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "beta.jpg:beta/,alpha.jpg:alpha/"

    def test_gallery_sort_date_reverse_with_exif(self, env, src):
        mc = {}
        _img(src, "alpha.jpg", mc)
        _img(src, "beta.jpg", mc)
        mc[src / "alpha.jpg"] = {
            "exif": {"DateTimeOriginal": "2025:01:01 12:00:00"},
            "iptc": {},
            "xmp": {},
        }
        mc[src / "beta.jpg"] = {
            "exif": {"DateTimeOriginal": "2020:01:01 12:00:00"},
            "iptc": {},
            "xmp": {},
        }
        result = expand_shortcodes(
            "<<gallery sort=date reverse>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "alpha.jpg:alpha/,beta.jpg:beta/"


# ===========================================================================
# Feature 3: Real Titles in Listings
# ===========================================================================


class TestRealTitlesInListings:
    def test_listing_uses_front_matter_title(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        md = source / "gallery" / "about.md"
        md.parent.mkdir()
        md.write_text("Title: About This Gallery\n\nInfo.")

        gallery = Node(node_type=None, name="gallery", source=None, parent=None)
        md_child = _make_child(NodeType.MARKDOWN, "about", md, parent=gallery)
        gallery.children.append(md_child)
        tree = _make_tree(gallery)

        build(tree, _site_config(), source, target)

        content = (target / "gallery" / "index.html").read_text()
        assert "page:About This Gallery" in content

    def test_listing_falls_back_to_stem(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        md = source / "gallery" / "my-page.md"
        md.parent.mkdir()
        md.write_text("\nNo front matter title.")

        gallery = Node(node_type=None, name="gallery", source=None, parent=None)
        md_child = _make_child(NodeType.MARKDOWN, "my-page", md, parent=gallery)
        gallery.children.append(md_child)
        tree = _make_tree(gallery)

        build(tree, _site_config(), source, target)

        content = (target / "gallery" / "index.html").read_text()
        assert "page:My Page" in content


# ===========================================================================
# Feature 4: Breadcrumb Data
# ===========================================================================


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

    def test_breadcrumbs_in_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "{% for c in breadcrumbs %}{{ c.name }}:{{ c.url }}{% if not loop.last %},{% endif %}{% endfor %}"
        _setup_theme(source, page=tpl)

        (source / "blog").mkdir()
        md = source / "blog" / "post.md"
        md.write_text("Title: Post\n\nHello.")

        blog = Node(node_type=None, name="blog", source=None, parent=None)
        child = _make_child(NodeType.MARKDOWN, "post", md, parent=blog)
        blog.children.append(child)
        tree = _make_tree(blog)

        build(tree, _site_config(), source, target)

        content = (target / "blog" / "post" / "index.html").read_text()
        assert "Test Site:/" in content
        assert "blog:/blog/" in content


# ===========================================================================
# Feature 5: Prev/Next Navigation
# ===========================================================================


class TestPrevNextNavigation:
    def _make_image_gallery(self, source, *names):
        """Create parent node with image children."""
        parent = Node(node_type=None, name="photos", source=None, parent=None)
        children = []
        for name in names:
            stem = Path(name).stem
            img_path = source / name
            img_path.write_bytes(b"fake")
            child = _make_child(NodeType.IMAGE, stem, img_path, parent=parent)
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

    def test_prev_next_in_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "prev={{ prev.url if prev else 'none' }}|next={{ next.url if next else 'none' }}"
        _setup_theme(source, image=tpl)

        parent = Node(node_type=None, name="", source=None, parent=None)
        imgs = []
        for name in ["a.jpg", "b.jpg", "c.jpg"]:
            f = source / name
            f.write_bytes(b"fake")
            stem = Path(name).stem
            child = _make_child(NodeType.IMAGE, stem, f, parent=parent)
            parent.children.append(child)
            imgs.append(child)

        build(parent, _site_config(), source, target)

        assert (target / "a" / "index.html").read_text() == "prev=none|next=b/"
        assert (target / "b" / "index.html").read_text() == "prev=a/|next=c/"
        assert (target / "c" / "index.html").read_text() == "prev=b/|next=none"


# ===========================================================================
# Feature 6: Verbose Output
# ===========================================================================


class TestVerboseOutput:
    def test_verbose_prints_build_messages(self, tmp_path, capsys):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")

        root = Node(node_type=NodeType.MARKDOWN, name="", source=md, parent=None)
        build(root, _site_config(), source, target, verbose=True)

        err = capsys.readouterr().err
        assert "Build:" in err

    def test_no_output_without_verbose(self, tmp_path, capsys):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")

        root = Node(node_type=NodeType.MARKDOWN, name="", source=md, parent=None)
        build(root, _site_config(), source, target, verbose=False)

        err = capsys.readouterr().err
        assert "Build:" not in err

    def test_verbose_sync_prints_delete(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        stale = target / "old.html"
        stale.write_text("stale")

        sync_target(target, set(), verbose=True)

        err = capsys.readouterr().err
        assert "Delete:" in err
        assert not stale.exists()

    def test_verbose_sync_prints_remove_dir(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        empty = target / "empty"
        empty.mkdir()

        sync_target(target, set(), verbose=True)

        err = capsys.readouterr().err
        assert "Remove:" in err


# ===========================================================================
# Feature 7: Dry-Run
# ===========================================================================


class TestDryRun:
    def test_dry_run_produces_no_files(self, tmp_path, capsys):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")

        root = Node(node_type=NodeType.MARKDOWN, name="", source=md, parent=None)
        expected = build(
            root, _site_config(), source, target, dry_run=True, verbose=True
        )

        assert not (target / "index.html").exists()
        assert target / "index.html" in expected

        err = capsys.readouterr().err
        assert "Would build:" in err

    def test_dry_run_image_no_files(self, tmp_path, capsys):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img = source / "photo.jpg"
        img.write_bytes(b"fake")

        tree = _make_tree(_make_child(NodeType.IMAGE, "photo", img))
        expected = build(
            tree, _site_config(), source, target, dry_run=True, verbose=True
        )

        assert not (target / "photo" / "index.html").exists()
        assert not (target / "photo" / "photo.jpg").exists()
        assert target / "photo" / "index.html" in expected
        assert target / "photo" / "photo.jpg" in expected

        err = capsys.readouterr().err
        assert "Would build:" in err

    def test_dry_run_sync_no_delete(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        stale = target / "old.html"
        stale.write_text("stale")

        sync_target(target, set(), dry_run=True, verbose=True)

        assert stale.exists()  # not deleted
        err = capsys.readouterr().err
        assert "Would delete:" in err

    def test_dry_run_expected_set_correct(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        css = source / "styles.css"
        css.write_text("body {}")

        root = Node(node_type=NodeType.MARKDOWN, name="", source=md, parent=None)
        root.children.append(_make_child(NodeType.STATIC, "styles", css))
        root.children[-1].parent = root

        expected_dry = build(root, _site_config(), source, target, dry_run=True)
        expected_real = build(root, _site_config(), source, target, dry_run=False)

        assert expected_dry == expected_real
