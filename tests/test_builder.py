import os
from unittest.mock import patch

import pytest
from static_gallery.builder import build
from static_gallery.sync import sync_target
from static_gallery.errors import GalleryError
from static_gallery.model import Node, NodeType

from conftest import (
    LISTING_TEMPLATE,
    setup_theme as _setup_theme,
)


def _site_config():
    return {"title": "Test Site", "url": "https://example.com/", "language": "en-us"}


def _make_tree(*children):
    root = Node(node_type=None, name="", source=None, parent=None)
    for c in children:
        c.parent = root
        root.children.append(c)
    return root


def _make_index_tree(source, *children):
    root = _make_tree(*children)
    root.node_type = NodeType.MARKDOWN
    root.source = source
    return root


def _make_child(node_type, name, source, parent=None):
    return Node(node_type=node_type, name=name, source=source, parent=parent)


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

        output = (target / "test.html").read_text()
        assert "site=Test Site" in output
        assert "page=Jane" in output
        assert "content=" in output

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

        output = (target / "gallery.html").read_text()
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

        output = (target / "plain.html").read_text()
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

        html = (target / "photo.html").read_text()
        assert "<title>Photo</title>" in html
        assert 'src="photo.jpg"' in html

        assert (target / "photo.jpg").read_bytes() == b"fake image data"

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

        html = (target / "my-cool_photo.html").read_text()
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


class TestTargetSync:
    def test_stale_file_removed(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        stale = target / "old.html"
        stale.write_text("stale")

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello.")

        root = _make_index_tree(md_file)
        expected = build(root, _site_config(), source, target)
        sync_target(target, expected)

        assert not stale.exists()
        assert (target / "index.html").exists()

    def test_empty_dirs_cleaned(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        stale_dir = target / "old"
        stale_dir.mkdir()
        (stale_dir / "stale.html").write_text("stale")

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello.")

        root = _make_index_tree(md_file)
        expected = build(root, _site_config(), source, target)
        sync_target(target, expected)

        assert not stale_dir.exists()

    def test_nested_stale_dirs_cleaned(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        stale_dir = target / "old" / "nested" / "deep"
        stale_dir.mkdir(parents=True)
        (stale_dir / "stale.html").write_text("stale")

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello.")

        root = _make_index_tree(md_file)
        expected = build(root, _site_config(), source, target)
        sync_target(target, expected)

        assert not (target / "old").exists()

    def test_target_root_not_removed(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        expected = build(_make_tree(), _site_config(), source, target)
        sync_target(target, expected)

        assert target.exists()


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

        output = (target / "post.html").read_text()
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

        output = (target / "post.html").read_text()
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

        html = target / "photo.html"
        asset = target / "photo.jpg"
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
        html = target / "post.html"
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
        html = target / "post.html"
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

        html = (target / "sunset.html").read_text()
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

        output = (target / "sunset.html").read_text()
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

        html = (target / "my-cool_photo.html").read_text()
        assert "<title>My Cool Photo</title>" in html


class TestSyncTargetSymlinks:
    def test_symlink_in_target_is_cleaned_up(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        real_file = tmp_path / "real.txt"
        real_file.write_text("hello")
        link = target / "stale.txt"
        link.symlink_to(real_file)

        sync_target(target, set())

        assert not link.exists() and not link.is_symlink()

    def test_broken_symlink_in_target_is_cleaned_up(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = target / "broken.txt"
        link.symlink_to(tmp_path / "nonexistent")

        sync_target(target, set())

        assert not link.is_symlink()
