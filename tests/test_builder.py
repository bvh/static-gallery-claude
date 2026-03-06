import os
import pytest
from static_gallery.builder import build
from static_gallery.errors import GalleryError
from static_gallery.model import Node, NodeType


PAGE_TEMPLATE = "<html><head><title>{{ page.title }}</title></head><body>{{ content }}</body></html>"
IMAGE_TEMPLATE = '<html><head><title>{{ page.title }}</title></head><body><img src="{{ content }}"></body></html>'


SHORTCODE_IMAGE_TEMPLATE = '<img src="{{ path }}" alt="{{ alt }}">'
SHORTCODE_CODE_TEMPLATE = (
    '<pre><code class="language-{{ language }}">{{ content }}</code></pre>'
)


def _setup_theme(source, page=PAGE_TEMPLATE, image=IMAGE_TEMPLATE):
    theme = source / ".theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme / "page.html").write_text(page)
    (theme / "image.html").write_text(image)
    sc = theme / "shortcodes"
    sc.mkdir(exist_ok=True)
    (sc / "image.html").write_text(SHORTCODE_IMAGE_TEMPLATE)
    (sc / "code.html").write_text(SHORTCODE_CODE_TEMPLATE)


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


class TestBuildMarkdown:
    def test_renders_through_template(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        md_file = source / "index.md"
        md_file.write_text("Title: Home\n\nHello **world**.")

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
        build(root, _site_config(), source, target)

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
        build(root, _site_config(), source, target)

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
        build(root, _site_config(), source, target)

        assert not (target / "old").exists()

    def test_target_root_not_removed(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        _setup_theme(source)

        build(_make_tree(), _site_config(), source, target)

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md_file
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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md

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

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md

        build(root, _site_config(), source, target, config_path=conf)
        html = target / "index.html"
        _set_mtime(html, PAST + 500)

        # Force rebuild — should rewrite even though nothing changed
        build(root, _site_config(), source, target, config_path=conf, force=True)
        assert html.stat().st_mtime > PAST + 500

    def test_expected_set_populated_when_skipping(self, tmp_path):
        """Stale files are still cleaned even when builds are skipped."""
        source, target, conf = self._setup(tmp_path)
        md = source / "index.md"
        md.write_text("Title: Home\n\nHello.")
        _set_mtime(md, PAST)
        _set_theme_mtime(source, PAST)
        _set_mtime(conf, PAST)

        root = _make_tree()
        root.node_type = NodeType.MARKDOWN
        root.source = md

        build(root, _site_config(), source, target, config_path=conf)

        # Plant a stale file
        stale = target / "stale.html"
        stale.write_text("stale")

        # Rebuild (skips markdown because up-to-date) — stale should be removed
        build(root, _site_config(), source, target, config_path=conf)
        assert not stale.exists()
        assert (target / "index.html").exists()
