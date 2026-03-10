from pathlib import Path

import jinja2
import pytest

from static_gallery.errors import GalleryError
from static_gallery.shortcodes import expand_shortcodes, shortcode_dependencies

IMAGE_TPL = '<img src="{{ path }}" alt="{{ alt }}">'
CODE_TPL = '<pre><code class="language-{{ language }}">{{ content }}</code></pre>'
TEXT_TPL = "<pre>{{ content }}</pre>"
CSV_TPL = "<pre>{{ content }}</pre>"
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
    (tpl_dir / "code.html").write_text(CODE_TPL)
    (tpl_dir / "text.html").write_text(TEXT_TPL)
    (tpl_dir / "csv.html").write_text(CSV_TPL)
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


_EMPTY_META = {"exif": {}, "iptc": {}, "xmp": {}}


def _img(src, name="photo.jpg", meta_cache=None):
    f = src / name
    f.write_bytes(b"fake")
    if meta_cache is not None:
        meta_cache[f] = _EMPTY_META
    return f


class TestImageShortcodes:
    def test_basic(self, env, src):
        _img(src)
        assert (
            expand_shortcodes("<<photo.jpg>>", env, src, source_root=src)
            == '<img src="photo.jpg" alt="photo">'
        )

    def test_subdirectory_path(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        _img(sub, "sunset.png")
        assert (
            expand_shortcodes("<<photos/sunset.png>>", env, src, source_root=src)
            == '<img src="photos/sunset.png" alt="sunset">'
        )

    def test_whitespace_tolerance(self, env, src):
        _img(src)
        assert (
            expand_shortcodes("<< photo.jpg >>", env, src, source_root=src)
            == '<img src="photo.jpg" alt="photo">'
        )

    def test_multiple_same_line(self, env, src):
        _img(src, "a.jpg")
        _img(src, "b.png")
        result = expand_shortcodes("<<a.jpg>> and <<b.png>>", env, src, source_root=src)
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_multiple_separate_lines(self, env, src):
        _img(src, "a.jpg")
        _img(src, "b.png")
        result = expand_shortcodes("<<a.jpg>>\n<<b.png>>", env, src, source_root=src)
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_no_shortcodes(self, env, src):
        text = "Just some normal text."
        assert expand_shortcodes(text, env, src, source_root=src) == text

    def test_auto_alt_dashes_underscores(self, env, src):
        _img(src, "my-cool_photo.jpg")
        assert (
            expand_shortcodes("<<my-cool_photo.jpg>>", env, src, source_root=src)
            == '<img src="my-cool_photo.jpg" alt="my cool photo">'
        )

    def test_explicit_alt(self, env, src):
        _img(src, "sunset.png")
        assert (
            expand_shortcodes(
                "<<sunset.png A beautiful sunset>>", env, src, source_root=src
            )
            == '<img src="sunset.png" alt="A beautiful sunset">'
        )

    def test_explicit_alt_with_padding(self, env, src):
        _img(src, "sunset.png")
        assert (
            expand_shortcodes(
                "<< sunset.png A beautiful sunset >>", env, src, source_root=src
            )
            == '<img src="sunset.png" alt="A beautiful sunset">'
        )


class TestCodeShortcodes:
    def test_inlines_content(self, env, src):
        (src / "hello.py").write_text("print('hello')")
        result = expand_shortcodes("<<hello.py>>", env, src, source_root=src)
        assert (
            '<pre><code class="language-python">print(&#39;hello&#39;)</code></pre>'
            in result
        )

    def test_language_mapping(self, env, src):
        (src / "app.js").write_text("const x = 1;")
        result = expand_shortcodes("<<app.js>>", env, src, source_root=src)
        assert "language-javascript" in result

    def test_content_escaping(self, env, src):
        (src / "bad.html").write_text("<script>alert('xss')</script>")
        result = expand_shortcodes("<<bad.html>>", env, src, source_root=src)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestTextShortcodes:
    def test_inlines_text(self, env, src):
        (src / "notes.txt").write_text("Some notes")
        result = expand_shortcodes("<<notes.txt>>", env, src, source_root=src)
        assert "<pre>Some notes</pre>" in result


class TestCsvShortcodes:
    def test_inlines_csv(self, env, src):
        (src / "data.csv").write_text("a,b\n1,2")
        result = expand_shortcodes("<<data.csv>>", env, src, source_root=src)
        assert "<pre>a,b\n1,2</pre>" in result


class TestShortcodeErrors:
    def test_unknown_extension_falls_back_to_code(self, env, src):
        (src / "file.xyz").write_text("data")
        result = expand_shortcodes("<<file.xyz>>", env, src, source_root=src)
        assert "language-xyz" in result
        assert "data" in result

    def test_unknown_extension_warns(self, env, src, capsys):
        (src / "file.xyz").write_text("data")
        expand_shortcodes("<<file.xyz>>", env, src, source_root=src)
        assert "unknown shortcode file type '.xyz'" in capsys.readouterr().err

    def test_known_code_extension_does_not_warn(self, env, src, capsys):
        (src / "hello.py").write_text("print('hi')")
        expand_shortcodes("<<hello.py>>", env, src, source_root=src)
        assert capsys.readouterr().err == ""

    def test_missing_file(self, env, src):
        with pytest.raises(GalleryError, match="file not found"):
            expand_shortcodes("<<missing.jpg>>", env, src, source_root=src)

    def test_missing_template(self, src):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(src)),
            autoescape=True,
        )
        (src / "photo.jpg").write_bytes(b"fake")
        with pytest.raises(GalleryError, match="Missing template"):
            expand_shortcodes("<<photo.jpg>>", env, src, source_root=src)

    def test_unknown_directive(self, env, src):
        with pytest.raises(GalleryError, match="Unknown shortcode directive"):
            expand_shortcodes("<<unknown>>", env, src, source_root=src)


class TestGalleryShortcode:
    def test_basic_listing(self, env, src):
        mc = {}
        _img(src, "alpha.jpg", mc)
        _img(src, "beta.png", mc)
        result = expand_shortcodes(
            "<<gallery>>", env, src, meta_cache=mc, source_root=src
        )
        assert "alpha.jpg:alpha/" in result
        assert "beta.png:beta/" in result

    def test_sort_name(self, env, src):
        mc = {}
        _img(src, "cherry.jpg", mc)
        _img(src, "apple.jpg", mc)
        _img(src, "banana.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=name>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "apple.jpg:apple/,banana.jpg:banana/,cherry.jpg:cherry/"

    def test_sort_name_reverse(self, env, src):
        mc = {}
        _img(src, "cherry.jpg", mc)
        _img(src, "apple.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=name reverse>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "cherry.jpg:cherry/,apple.jpg:apple/"

    def test_sort_date(self, env, src):
        import os
        import time

        mc = {}
        _img(src, "old.jpg", mc)
        old_time = time.time() - 100
        os.utime(src / "old.jpg", (old_time, old_time))
        _img(src, "new.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=date>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "old.jpg:old/,new.jpg:new/"

    def test_sort_date_reverse(self, env, src):
        import os
        import time

        mc = {}
        _img(src, "old.jpg", mc)
        old_time = time.time() - 100
        os.utime(src / "old.jpg", (old_time, old_time))
        _img(src, "new.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=date reverse>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "new.jpg:new/,old.jpg:old/"

    def test_filter(self, env, src):
        mc = {}
        _img(src, "photo.jpg", mc)
        _img(src, "photo.png", mc)
        result = expand_shortcodes(
            "<<gallery filter=*.jpg>>", env, src, meta_cache=mc, source_root=src
        )
        assert "photo.jpg:photo/" in result
        assert "photo.png" not in result

    def test_path_subdirectory(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        mc = {}
        _img(sub, "sunset.jpg", mc)
        result = expand_shortcodes(
            "<<gallery path=photos>>", env, src, meta_cache=mc, source_root=src
        )
        assert "sunset.jpg:sunset/" in result

    def test_path_relative_in_output(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        mc = {}
        _img(sub, "sunset.jpg", mc)
        gallery_tpl = "{% for image in images %}{{ image.path }}{% endfor %}"
        tpl_dir = env.loader.searchpath[0]  # type: ignore[union-attr]
        (Path(tpl_dir) / "shortcodes" / "gallery.html").write_text(gallery_tpl)
        result = expand_shortcodes(
            "<<gallery path=photos>>", env, src, meta_cache=mc, source_root=src
        )
        assert result == "photos/sunset.jpg"

    def test_collision_falls_back_to_html(self, env, src):
        mc = {}
        _img(src, "sunset.jpg", mc)
        # Create a sibling directory "sunset/" with contents
        sibling = src / "sunset"
        sibling.mkdir()
        (sibling / "detail.txt").write_text("info")
        result = expand_shortcodes(
            "<<gallery>>", env, src, meta_cache=mc, source_root=src
        )
        assert "sunset.jpg:sunset.html" in result

    def test_empty_directory(self, env, src):
        result = expand_shortcodes(
            "<<gallery>>", env, src, meta_cache={}, source_root=src
        )
        assert result == ""

    def test_missing_directory(self, env, src):
        with pytest.raises(GalleryError, match="Gallery directory not found"):
            expand_shortcodes(
                "<<gallery path=nonexistent>>", env, src, meta_cache={}, source_root=src
            )

    def test_unknown_sort_key(self, env, src):
        with pytest.raises(GalleryError, match="Unknown gallery sort key"):
            expand_shortcodes(
                "<<gallery sort=size>>", env, src, meta_cache={}, source_root=src
            )

    def test_ignores_non_image_files(self, env, src):
        mc = {}
        _img(src, "photo.jpg", mc)
        (src / "readme.txt").write_text("hello")
        result = expand_shortcodes(
            "<<gallery>>", env, src, meta_cache=mc, source_root=src
        )
        assert "photo.jpg" in result
        assert "readme.txt" not in result

    def test_gallery_image_metadata_fields(self, env, src):
        """Gallery image dicts include title, alt, exif, iptc, xmp keys."""
        mc = {}
        _img(src, "sunset.jpg", mc)
        field_tpl = (
            "{% for image in images %}"
            "title={{ image.title }}|alt={{ image.alt }}"
            "|exif={{ image.exif is mapping }}"
            "|iptc={{ image.iptc is mapping }}"
            "|xmp={{ image.xmp is mapping }}"
            "{% endfor %}"
        )
        tpl_dir = env.loader.searchpath[0]  # type: ignore[union-attr]
        (Path(tpl_dir) / "shortcodes" / "gallery.html").write_text(field_tpl)
        result = expand_shortcodes(
            "<<gallery>>", env, src, meta_cache=mc, source_root=src
        )
        assert "title=Sunset" in result
        assert "alt=sunset" in result
        assert "exif=True" in result
        assert "iptc=True" in result
        assert "xmp=True" in result


class TestPathTraversal:
    def test_file_shortcode_rejects_traversal(self, env, src):
        with pytest.raises(GalleryError, match="escapes source tree"):
            expand_shortcodes("<<../../etc/passwd.txt>>", env, src, source_root=src)

    def test_gallery_path_rejects_traversal(self, env, src):
        with pytest.raises(GalleryError, match="escapes source tree"):
            expand_shortcodes(
                "<<gallery path=../../>>", env, src, meta_cache={}, source_root=src
            )

    def test_file_shortcode_from_subdirectory(self, env, src):
        sub = src / "pages"
        sub.mkdir()
        with pytest.raises(GalleryError, match="escapes source tree"):
            expand_shortcodes("<<../../../etc/passwd.txt>>", env, sub, source_root=src)

    def test_symlink_escape_rejected(self, env, src):
        outside = src.parent / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        link = src / "escape"
        link.symlink_to(outside)
        with pytest.raises(GalleryError, match="escapes source tree"):
            expand_shortcodes("<<escape/secret.txt>>", env, src, source_root=src)

    def test_gallery_symlink_escape_rejected(self, env, src):
        outside = src.parent / "outside_gallery"
        outside.mkdir()
        link = src / "linked"
        link.symlink_to(outside)
        with pytest.raises(GalleryError, match="escapes source tree"):
            expand_shortcodes(
                "<<gallery path=linked>>", env, src, meta_cache={}, source_root=src
            )

    def test_subdirectory_is_allowed(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        mc = {}
        _img(sub, "ok.jpg", mc)
        result = expand_shortcodes(
            "<<gallery path=photos>>", env, src, meta_cache=mc, source_root=src
        )
        assert "ok.jpg" in result


class TestShortcodeDependencies:
    def test_returns_resolved_paths_for_file_shortcodes(self, src):
        (src / "example.py").write_text("print('hi')")
        deps = shortcode_dependencies("Look: <<example.py>>", src)
        assert deps == {src / "example.py"}

    def test_empty_for_no_shortcodes(self, src):
        deps = shortcode_dependencies("no shortcodes here", src)
        assert deps == set()

    def test_multiple_deps(self, src):
        (src / "a.py").write_text("")
        (src / "b.csv").write_text("")
        deps = shortcode_dependencies("<<a.py>>\n<<b.csv>>", src)
        assert deps == {src / "a.py", src / "b.csv"}

    def test_ignores_missing_files(self, src):
        deps = shortcode_dependencies("<<missing.py>>", src)
        assert deps == set()

    def test_includes_unknown_extensions(self, src):
        (src / "file.xyz").write_text("")
        deps = shortcode_dependencies("<<file.xyz>>", src)
        assert deps == {src / "file.xyz"}

    def test_gallery_deps_include_images(self, src):
        _img(src, "a.jpg")
        _img(src, "b.png")
        deps = shortcode_dependencies("<<gallery>>", src)
        assert src / "a.jpg" in deps
        assert src / "b.png" in deps

    def test_gallery_with_path_option(self, src):
        photos = src / "photos"
        photos.mkdir()
        _img(photos, "a.jpg")
        deps = shortcode_dependencies("<<gallery path=photos>>", src)
        assert photos / "a.jpg" in deps

    def test_gallery_with_filter_option(self, src):
        _img(src, "photo.jpg")
        _img(src, "photo.png")
        deps = shortcode_dependencies("<<gallery filter=*.jpg>>", src)
        assert deps == {src / "photo.jpg"}

    def test_path_traversal_excluded(self, src):
        deps = shortcode_dependencies("<<../../etc/passwd.txt>>", src, source_root=src)
        assert deps == set()

    def test_gallery_path_traversal_excluded(self, src):
        deps = shortcode_dependencies("<<gallery path=../../>>", src, source_root=src)
        assert deps == set()

    def test_gallery_missing_dir_returns_empty(self, src):
        deps = shortcode_dependencies("<<gallery path=nonexistent>>", src)
        assert deps == set()

    def test_unknown_directive_returns_empty(self, src):
        deps = shortcode_dependencies("<<unknown>>", src)
        assert deps == set()
