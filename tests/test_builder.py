import os
from pathlib import Path
from unittest.mock import patch

import pytest
from static_gallery.builder import build
from static_gallery.sync import sync_target
from static_gallery.errors import GalleryError
from static_gallery.model import Node, NodeType

from conftest import (
    LISTING_TEMPLATE,
    make_child as _make_child,
    make_index_tree as _make_index_tree,
    make_tree as _make_tree,
    setup_theme as _setup_theme,
    site_config as _site_config,
)

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


class TestBuildMarkdown:
    def test_renders_through_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello **world**.")

        root = _make_index_tree(md_file)
        build(root, _site_config(), source, target)

        output = (target / "index.html").read_text()
        assert "<title>Home</title>" in output
        assert "<strong>world</strong>" in output

    def test_template_variables(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "site={{ site.title }}|page={{ page.author }}|content={{ content }}"
        _setup_theme(source, page=tpl)

        md_file = source / "test.md"
        md_file.write_text("Author: Jane\n\nHi.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "test", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "test" / "index.html").read_text()
        assert "site=Test Site" in output
        assert "page=Jane" in output
        assert "content=" in output

    def test_generator_variable(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "{{ generator.name }} {{ generator.version }}"
        _setup_theme(source, page=tpl)

        md_file = source / "test.md"
        md_file.write_text("\nHello.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "test", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "test" / "index.html").read_text()
        assert output.startswith("Static Gallery ")
        # Version should be a dotted number like 0.1.0
        version = output.split(" ", 2)[2].strip()
        assert version.count(".") >= 1

    def test_type_override(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md_file = source / "gallery.md"
        md_file.write_text("Type: image\nTitle: Gallery\n\nSome content.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "gallery", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "gallery" / "index.html").read_text()
        assert "<img src=" in output

    def test_no_front_matter(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md_file = source / "plain.md"
        md_file.write_text("Just some text.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "plain", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "plain" / "index.html").read_text()
        assert "Just some text." in output


class TestBuildImage:
    def test_renders_through_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img_file = source / "photo.jpg"
        img_file.write_bytes(b"fake image data")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "photo", img_file),
        )
        build(tree, _site_config(), source, target)

        html = (target / "photo" / "index.html").read_text()
        assert "<title>Photo</title>" in html
        assert 'src="photo.jpg"' in html

        assert (target / "photo" / "photo.jpg").read_bytes() == b"fake image data"

    def test_title_from_stem(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img_file = source / "my-cool_photo.png"
        img_file.write_bytes(b"fake")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "my-cool_photo", img_file),
        )
        build(tree, _site_config(), source, target)

        html = (target / "my-cool_photo" / "index.html").read_text()
        assert "<title>My Cool Photo</title>" in html


class TestBuildStatic:
    def test_copies_file(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        css_file = source / "styles.css"
        css_file.write_text("body { color: red; }")

        tree = _make_tree(
            _make_child(NodeType.STATIC, "styles", css_file),
        )
        build(tree, _site_config(), source, target)

        assert (target / "styles.css").read_text() == "body { color: red; }"

    def test_creates_parent_dirs(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        js_file = source / "assets" / "app.js"
        js_file.parent.mkdir(parents=True)
        js_file.write_text("console.log('hi')")

        # Need intermediate container node for "assets"
        assets_dir = Node(node_type=None, name="assets", source=None, parent=None)
        child = _make_child(NodeType.STATIC, "app", js_file, parent=assets_dir)
        assets_dir.children.append(child)
        tree = _make_tree(assets_dir)
        build(tree, _site_config(), source, target)

        assert (target / "assets" / "app.js").read_text() == "console.log('hi')"


class TestShortcodeIntegration:
    def test_image_shortcode_in_markdown(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        (source / "photo.jpg").write_bytes(b"fake image")
        md_file = source / "post.md"
        md_file.write_text("Title: Post\n\nHere is <<photo.jpg>>.")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "post", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "post" / "index.html").read_text()
        assert '<img src="photo.jpg"' in output

    def test_code_shortcode_in_markdown(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        (source / "example.py").write_text("print('hello')")
        md_file = source / "post.md"
        md_file.write_text("Title: Post\n\n<<example.py>>")

        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "post", md_file),
        )
        build(tree, _site_config(), source, target)

        output = (target / "post" / "index.html").read_text()
        assert "language-python" in output
        assert "print(" in output


class TestBuildErrors:
    def test_missing_template_exits(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello.")

        root = _make_index_tree(md_file)
        with pytest.raises(GalleryError):
            build(root, _site_config(), source, target)

    def test_template_syntax_error_exits(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        theme = source / ".theme"
        theme.mkdir()
        (theme / "page.html").write_text("{{ unclosed")

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello.")

        root = _make_index_tree(md_file)
        with pytest.raises(GalleryError):
            build(root, _site_config(), source, target)

    def test_unreadable_source_exits(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        missing = source / "gone.md"
        tree = _make_tree(
            _make_child(NodeType.MARKDOWN, "gone", missing),
        )
        with pytest.raises(GalleryError):
            build(tree, _site_config(), source, target)


# Mtime helpers: set all source files to a "past" time, then selectively
# advance specific files to test incremental logic.

PAST = 1_000_000_000.0  # 2001-09-09
FUTURE = 2_000_000_000.0  # 2033-05-18


def _set_mtime(path, t):
    os.utime(path, (t, t))


def _set_theme_mtime(source, t):
    theme = source / ".theme"
    for f in theme.rglob("*"):
        if f.is_file():
            _set_mtime(f, t)


class TestIncrementalBuild:
    def _setup(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)
        conf = source / "site.conf"
        conf.write_text("title: Test\n")
        return source, target, conf

    def test_skip_unchanged_markdown(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_index_tree(md)

        # First build
        build(root, _site_config(), source, target, config_path=conf)
        html = target / "index.html"
        assert html.exists()
        # Set output to a known time so we can detect writes
        _set_mtime(html, PAST + 500)

        # Second build — source unchanged
        build(root, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime == PAST + 500  # not rewritten

    def test_rebuild_on_source_change(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_index_tree(md)

        build(root, _site_config(), source, target, config_path=conf)
        html = target / "index.html"
        _set_mtime(html, PAST + 500)

        # Touch source file to be newer than target
        _set_mtime(md, FUTURE)
        build(root, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime > PAST + 500  # was rewritten

    def test_rebuild_html_on_template_change(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        img = source / "photo.jpg"
        img.write_bytes(b"fake")
        _set_mtime(img, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        tree = _make_tree(_make_child(NodeType.IMAGE, "photo", img))
        build(tree, _site_config(), source, target, config_path=conf)

        html = target / "photo" / "index.html"
        asset = target / "photo" / "photo.jpg"
        _set_mtime(html, PAST + 500)
        _set_mtime(asset, PAST + 500)

        # Touch template — HTML should rebuild, asset should not
        _set_mtime(source / ".theme" / "image.html", FUTURE)
        build(tree, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime > PAST + 500  # HTML rebuilt
        assert asset.stat().st_mtime == PAST + 500  # asset untouched

    def test_rebuild_html_on_config_change(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_index_tree(md)

        build(root, _site_config(), source, target, config_path=conf)
        html = target / "index.html"
        _set_mtime(html, PAST + 500)

        # Touch config
        _set_mtime(conf, FUTURE)
        build(root, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime > PAST + 500

    def test_skip_unchanged_static(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        css = source / "style.css"
        css.write_text("body{}")
        _set_mtime(css, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        tree = _make_tree(_make_child(NodeType.STATIC, "style", css))
        build(tree, _site_config(), source, target, config_path=conf)

        out = target / "style.css"
        _set_mtime(out, PAST + 500)

        build(tree, _site_config(), source, target, config_path=conf)
        assert out.stat().st_mtime == PAST + 500

    def test_force_rebuilds_everything(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_index_tree(md)

        build(root, _site_config(), source, target, config_path=conf)
        html = target / "index.html"
        _set_mtime(html, PAST + 500)

        # Force rebuild — should rewrite even though nothing changed
        build(root, _site_config(), source, target, config_path=conf, force=True)
        assert html.stat().st_mtime > PAST + 500

    def test_rebuild_markdown_when_shortcode_dep_changes(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        (source / "example.py").write_text("print('v1')")
        md = source / "post.md"
        md.write_text("Title: Post\n\n<<example.py>>")
        _set_mtime(md, PAST)
        _set_mtime(source / "example.py", PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target, config_path=conf)
        html = target / "post" / "index.html"
        assert html.exists()
        _set_mtime(html, PAST + 500)

        # Touch the dependency file — markdown should rebuild
        _set_mtime(source / "example.py", FUTURE)
        build(tree, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime > PAST + 500

    def test_skip_markdown_when_shortcode_dep_unchanged(self, tmp_path):
        source, target, conf = self._setup(tmp_path)
        (source / "example.py").write_text("print('v1')")
        md = source / "post.md"
        md.write_text("Title: Post\n\n<<example.py>>")
        _set_mtime(md, PAST)
        _set_mtime(source / "example.py", PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "post", md))
        build(tree, _site_config(), source, target, config_path=conf)
        html = target / "post" / "index.html"
        _set_mtime(html, PAST + 500)

        # Rebuild with nothing changed — should skip
        build(tree, _site_config(), source, target, config_path=conf)
        assert html.stat().st_mtime == PAST + 500

    def test_expected_set_populated_when_skipping(self, tmp_path):
        """Stale files are still cleaned even when builds are skipped."""
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_index_tree(md)

        expected = build(root, _site_config(), source, target, config_path=conf)
        sync_target(target, expected)

        # Plant a stale file
        stale = target / "stale.html"
        stale.write_text("stale")

        # Rebuild (skips markdown because up-to-date) — stale should be removed
        expected = build(root, _site_config(), source, target, config_path=conf)
        sync_target(target, expected)
        assert not stale.exists()
        assert (target / "index.html").exists()


class TestPrettyURLCollision:
    def test_markdown_falls_back_when_sibling_dir_exists(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "about.md"
        md.write_text("Title: About\n\nAbout page.")
        sub_md = source / "details.md"
        sub_md.write_text("Title: Details\n\nDetails.")

        about_dir = Node(node_type=None, name="about", source=None, parent=None)
        details = _make_child(NodeType.MARKDOWN, "details", sub_md, parent=about_dir)
        about_dir.children.append(details)
        about_md = _make_child(NodeType.MARKDOWN, "about", md)
        tree = _make_tree(about_dir, about_md)

        build(tree, _site_config(), source, target)

        # Collision: about.md falls back to about.html (not about/index.html)
        assert (target / "about.html").exists()
        about_html = (target / "about.html").read_text()
        assert "About page." in about_html

    def test_image_falls_back_when_sibling_dir_exists(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img = source / "photo.jpg"
        img.write_bytes(b"fake image data")
        sub_md = source / "info.md"
        sub_md.write_text("Title: Info\n\nInfo.")

        photo_dir = Node(node_type=None, name="photo", source=None, parent=None)
        info = _make_child(NodeType.MARKDOWN, "info", sub_md, parent=photo_dir)
        photo_dir.children.append(info)
        photo_img = _make_child(NodeType.IMAGE, "photo", img)
        tree = _make_tree(photo_dir, photo_img)

        build(tree, _site_config(), source, target)

        # Collision: image falls back to photo.html, asset at root level
        assert (target / "photo.html").exists()
        assert (target / "photo.jpg").exists()

    def test_no_collision_without_sibling_dir(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md = source / "about.md"
        md.write_text("Title: About\n\nAbout page.")

        tree = _make_tree(_make_child(NodeType.MARKDOWN, "about", md))
        build(tree, _site_config(), source, target)

        # No collision: pretty URL
        assert (target / "about" / "index.html").exists()
        assert not (target / "about.html").exists()

    def test_listing_urls_use_html_on_collision(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        listing = (
            "{% for p in children.pages %}page:{{ p.url }} {% endfor %}"
            "{% for i in children.images %}img:{{ i.url }} {% endfor %}"
        )
        _setup_theme(source, listing=listing)

        md = source / "about.md"
        md.write_text("Title: About\n\nAbout page.")
        img = source / "photo.jpg"
        img.write_bytes(b"fake image data")

        # Sibling dirs with children cause collisions
        about_dir = Node(node_type=None, name="about", source=None, parent=None)
        about_dir.children.append(
            _make_child(NodeType.STATIC, "x", source / "about.md", parent=about_dir)
        )
        photo_dir = Node(node_type=None, name="photo", source=None, parent=None)
        photo_dir.children.append(
            _make_child(NodeType.STATIC, "x", source / "photo.jpg", parent=photo_dir)
        )
        about_md = _make_child(NodeType.MARKDOWN, "about", md)
        photo_img = _make_child(NodeType.IMAGE, "photo", img)

        parent = Node(node_type=None, name="gallery", source=None, parent=None)
        for child in [about_dir, photo_dir, about_md, photo_img]:
            child.parent = parent
            parent.children.append(child)
        tree = _make_tree(parent)

        build(tree, _site_config(), source, target)

        content = (target / "gallery" / "index.html").read_text()
        assert "page:about.html" in content
        assert "img:photo.html" in content

    def test_listing_urls_use_slash_without_collision(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        listing = (
            "{% for p in children.pages %}page:{{ p.url }} {% endfor %}"
            "{% for i in children.images %}img:{{ i.url }} {% endfor %}"
        )
        _setup_theme(source, listing=listing)

        md = source / "about.md"
        md.write_text("Title: About\n\nAbout page.")
        img = source / "photo.jpg"
        img.write_bytes(b"fake image data")

        parent = Node(node_type=None, name="gallery", source=None, parent=None)
        about_md = _make_child(NodeType.MARKDOWN, "about", md, parent=parent)
        photo_img = _make_child(NodeType.IMAGE, "photo", img, parent=parent)
        parent.children.extend([about_md, photo_img])
        tree = _make_tree(parent)

        build(tree, _site_config(), source, target)

        content = (target / "gallery" / "index.html").read_text()
        assert "page:about/" in content
        assert "img:photo/" in content

    def test_nav_urls_use_html_on_collision(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "prev={{ prev.url if prev else 'none' }}|next={{ next.url if next else 'none' }}"
        _setup_theme(source, image=tpl)

        a_img = source / "a.jpg"
        a_img.write_bytes(b"fake")
        b_img = source / "b.jpg"
        b_img.write_bytes(b"fake")

        parent = Node(node_type=None, name="", source=None, parent=None)
        # "a" has a sibling directory collision
        a_dir = Node(node_type=None, name="a", source=None, parent=parent)
        a_dir.children.append(_make_child(NodeType.STATIC, "x", a_img, parent=a_dir))
        a_node = _make_child(NodeType.IMAGE, "a", a_img, parent=parent)
        b_node = _make_child(NodeType.IMAGE, "b", b_img, parent=parent)
        parent.children.extend([a_dir, a_node, b_node])

        build(parent, _site_config(), source, target)

        # b's prev link to a should use .html (collision)
        b_html = (target / "b" / "index.html").read_text()
        assert "prev=a.html" in b_html

        # a's next link to b should use / (no collision)
        a_html = (target / "a.html").read_text()
        assert "next=b/" in a_html


class TestAutoIndex:
    def test_generates_index_for_dir_with_images(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        img = source / "photos" / "sunset.jpg"
        img.parent.mkdir()
        img.write_bytes(b"fake")

        photos = Node(node_type=None, name="photos", source=None, parent=None)
        child = _make_child(NodeType.IMAGE, "sunset", img, parent=photos)
        photos.children.append(child)
        tree = _make_tree(photos)

        build(tree, _site_config(), source, target)

        listing = target / "photos" / "index.html"
        assert listing.exists()
        content = listing.read_text()
        assert "img:sunset" in content
        assert "<title>Photos</title>" in content

    def test_skipped_when_no_listing_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)  # no listing template

        img = source / "photos" / "sunset.jpg"
        img.parent.mkdir()
        img.write_bytes(b"fake")

        photos = Node(node_type=None, name="photos", source=None, parent=None)
        child = _make_child(NodeType.IMAGE, "sunset", img, parent=photos)
        photos.children.append(child)
        tree = _make_tree(photos)

        build(tree, _site_config(), source, target)

        assert not (target / "photos" / "index.html").exists()

    def test_skipped_for_empty_directories(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        empty_dir = Node(node_type=None, name="empty", source=None, parent=None)
        tree = _make_tree(empty_dir)

        build(tree, _site_config(), source, target)

        assert not (target / "empty" / "index.html").exists()

    def test_not_used_when_index_md_exists(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        md = source / "photos" / "index.md"
        md.parent.mkdir()
        md.write_text("Title: My Photos\n\nCustom page.")

        photos = Node(
            node_type=NodeType.MARKDOWN, name="photos", source=md, parent=None
        )
        tree = _make_tree(photos)

        build(tree, _site_config(), source, target)

        content = (target / "photos" / "index.html").read_text()
        assert "Custom page." in content
        assert "img:" not in content  # listing template not used

    def test_template_receives_categorized_children(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        # Create source dirs for the nodes
        (source / "gallery").mkdir()
        (source / "gallery" / "sub").mkdir()

        img = source / "gallery" / "photo.jpg"
        img.write_bytes(b"fake")
        md = source / "gallery" / "about.md"
        md.write_text("Title: About\n\nInfo.")
        css = source / "gallery" / "sub" / "x.css"
        css.write_text("body{}")

        gallery = Node(node_type=None, name="gallery", source=None, parent=None)
        sub = Node(node_type=None, name="sub", source=None, parent=gallery)
        sub.children.append(_make_child(NodeType.STATIC, "dummy", css, parent=sub))
        img_child = _make_child(NodeType.IMAGE, "photo", img, parent=gallery)
        md_child = _make_child(NodeType.MARKDOWN, "about", md, parent=gallery)
        gallery.children.extend([sub, img_child, md_child])
        tree = _make_tree(gallery)

        build(tree, _site_config(), source, target)

        content = (target / "gallery" / "index.html").read_text()
        assert "dir:sub" in content
        assert "page:About" in content
        assert "img:photo" in content

    def test_root_auto_indexed(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        img = source / "photo.jpg"
        img.write_bytes(b"fake")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "photo", img),
        )

        build(tree, _site_config(), source, target)

        listing = target / "index.html"
        assert listing.exists()
        content = listing.read_text()
        assert "img:photo" in content
        assert "<title>Test Site</title>" in content

    def test_auto_indexed_files_in_expected_set(self, tmp_path):
        """Auto-indexed pages should not be deleted by sync."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source, listing=LISTING_TEMPLATE)

        img = source / "photos" / "a.jpg"
        img.parent.mkdir()
        img.write_bytes(b"fake")

        photos = Node(node_type=None, name="photos", source=None, parent=None)
        photos.children.append(_make_child(NodeType.IMAGE, "a", img, parent=photos))
        tree = _make_tree(photos)

        # First build
        expected = build(tree, _site_config(), source, target)
        sync_target(target, expected)
        assert (target / "photos" / "index.html").exists()

        # Second build — listing should survive sync
        expected = build(tree, _site_config(), source, target)
        sync_target(target, expected)
        assert (target / "photos" / "index.html").exists()


class TestThemeAssets:
    def test_copies_theme_static_files(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        static_dir = source / ".theme" / "static"
        static_dir.mkdir()
        (static_dir / "styles.css").write_text("body { color: red; }")

        tree = _make_tree()
        build(tree, _site_config(), source, target)

        assert (target / "styles.css").read_text() == "body { color: red; }"

    def test_preserves_nested_directory_structure(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        css_dir = source / ".theme" / "static" / "css"
        css_dir.mkdir(parents=True)
        (css_dir / "main.css").write_text("h1 {}")
        js_dir = source / ".theme" / "static" / "js"
        js_dir.mkdir(parents=True)
        (js_dir / "app.js").write_text("alert(1)")

        tree = _make_tree()
        build(tree, _site_config(), source, target)

        assert (target / "css" / "main.css").read_text() == "h1 {}"
        assert (target / "js" / "app.js").read_text() == "alert(1)"

    def test_theme_assets_survive_sync(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        static_dir = source / ".theme" / "static"
        static_dir.mkdir()
        (static_dir / "styles.css").write_text("body {}")

        tree = _make_tree()
        expected = build(tree, _site_config(), source, target)
        sync_target(target, expected)

        assert (target / "styles.css").exists()

    def test_no_error_without_static_dir(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        tree = _make_tree()
        build(tree, _site_config(), source, target)  # should not raise

    def test_skips_dotfiles(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        static_dir = source / ".theme" / "static"
        static_dir.mkdir()
        (static_dir / ".DS_Store").write_bytes(b"\x00")
        dotdir = static_dir / ".hidden"
        dotdir.mkdir()
        (dotdir / "secret.txt").write_text("nope")
        (static_dir / "visible.css").write_text("body {}")

        tree = _make_tree()
        build(tree, _site_config(), source, target)

        assert (target / "visible.css").exists()
        assert not (target / ".DS_Store").exists()
        assert not (target / ".hidden").exists()

    def test_incremental_skips_unchanged_theme_assets(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)
        conf = source / "site.conf"
        conf.write_text("title: Test\n")

        static_dir = source / ".theme" / "static"
        static_dir.mkdir()
        (static_dir / "styles.css").write_text("body {}")
        _set_mtime(static_dir / "styles.css", PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        tree = _make_tree()
        build(tree, _site_config(), source, target, config_path=conf)

        out = target / "styles.css"
        _set_mtime(out, PAST + 500)

        build(tree, _site_config(), source, target, config_path=conf)
        assert out.stat().st_mtime == PAST + 500  # not rewritten


MOCK_METADATA = {
    "exif": {"ISO": "400", "FocalLength": "200mm"},
    "iptc": {"ObjectName": "Sunset Over Water", "City": "Portland"},
    "xmp": {
        "AltTextAccessibility": {'lang="x-default"': "A golden sunset over the river"}
    },
}


class TestImageMetadata:
    def test_image_page_uses_iptc_title(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img_file = source / "sunset.jpg"
        img_file.write_bytes(b"fake image data")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "sunset", img_file),
        )

        with patch(
            "static_gallery.metadata.read_image_metadata", return_value=MOCK_METADATA
        ):
            build(tree, _site_config(), source, target)

        html = (target / "sunset" / "index.html").read_text()
        assert "<title>Sunset Over Water</title>" in html

    def test_image_page_metadata_in_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        tpl = "{{ page.title }}|{{ page.iptc.City }}|{{ page.exif.ISO }}"
        _setup_theme(source, image=tpl)

        img_file = source / "sunset.jpg"
        img_file.write_bytes(b"fake image data")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "sunset", img_file),
        )

        with patch(
            "static_gallery.metadata.read_image_metadata", return_value=MOCK_METADATA
        ):
            build(tree, _site_config(), source, target)

        output = (target / "sunset" / "index.html").read_text()
        assert "Sunset Over Water" in output
        assert "Portland" in output
        assert "400" in output

    def test_listing_uses_metadata_title_and_alt(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        listing = "{% for i in children.images %}{{ i.title }}|{{ i.alt }}{% endfor %}"
        _setup_theme(source, listing=listing)

        (source / "photos").mkdir()
        img_file = source / "photos" / "sunset.jpg"
        img_file.write_bytes(b"fake image data")

        photos = Node(node_type=None, name="photos", source=None, parent=None)
        photos.children.append(
            _make_child(NodeType.IMAGE, "sunset", img_file, parent=photos)
        )
        tree = _make_tree(photos)

        with patch(
            "static_gallery.metadata.read_image_metadata", return_value=MOCK_METADATA
        ):
            build(tree, _site_config(), source, target)

        content = (target / "photos" / "index.html").read_text()
        assert "Sunset Over Water" in content
        assert "A golden sunset over the river" in content

    def test_falls_back_to_stem_without_metadata(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        img_file = source / "my-cool_photo.png"
        img_file.write_bytes(b"fake")

        tree = _make_tree(
            _make_child(NodeType.IMAGE, "my-cool_photo", img_file),
        )

        empty_meta = {"exif": {}, "iptc": {}, "xmp": {}}
        with patch(
            "static_gallery.metadata.read_image_metadata", return_value=empty_meta
        ):
            build(tree, _site_config(), source, target)

        html = (target / "my-cool_photo" / "index.html").read_text()
        assert "<title>My Cool Photo</title>" in html


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


class TestBreadcrumbsIntegration:
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


class TestPrevNextIntegration:
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


class TestVerboseBuild:
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


class TestDryRun:
    def test_produces_no_files(self, tmp_path, capsys):
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

    def test_image_no_files(self, tmp_path, capsys):
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

    def test_expected_set_correct(self, tmp_path):
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


def _setup_theme_with_feed(source, **kwargs):
    _setup_theme(source, **kwargs)
    (source / ".theme" / "feed.xml").write_text(FEED_TEMPLATE)


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
        assert "https://example.com/post/" in content
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
        assert "https://example.com/sunset/" in content

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
        assert "https://example.com/blog/post/" in content

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
