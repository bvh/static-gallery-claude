from pathlib import Path

import jinja2
import pytest

from static_gallery.errors import GalleryError
from static_gallery.shortcodes import expand_shortcodes

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
            expand_shortcodes("<<photo.jpg>>", env, src)
            == '<img src="photo.jpg" alt="photo">'
        )

    def test_subdirectory_path(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        _img(sub, "sunset.png")
        assert (
            expand_shortcodes("<<photos/sunset.png>>", env, src)
            == '<img src="photos/sunset.png" alt="sunset">'
        )

    def test_whitespace_tolerance(self, env, src):
        _img(src)
        assert (
            expand_shortcodes("<< photo.jpg >>", env, src)
            == '<img src="photo.jpg" alt="photo">'
        )

    def test_multiple_same_line(self, env, src):
        _img(src, "a.jpg")
        _img(src, "b.png")
        result = expand_shortcodes("<<a.jpg>> and <<b.png>>", env, src)
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_multiple_separate_lines(self, env, src):
        _img(src, "a.jpg")
        _img(src, "b.png")
        result = expand_shortcodes("<<a.jpg>>\n<<b.png>>", env, src)
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_no_shortcodes(self, env, src):
        text = "Just some normal text."
        assert expand_shortcodes(text, env, src) == text

    def test_auto_alt_dashes_underscores(self, env, src):
        _img(src, "my-cool_photo.jpg")
        assert (
            expand_shortcodes("<<my-cool_photo.jpg>>", env, src)
            == '<img src="my-cool_photo.jpg" alt="my cool photo">'
        )

    def test_explicit_alt(self, env, src):
        _img(src, "sunset.png")
        assert (
            expand_shortcodes("<<sunset.png A beautiful sunset>>", env, src)
            == '<img src="sunset.png" alt="A beautiful sunset">'
        )

    def test_explicit_alt_with_padding(self, env, src):
        _img(src, "sunset.png")
        assert (
            expand_shortcodes("<< sunset.png A beautiful sunset >>", env, src)
            == '<img src="sunset.png" alt="A beautiful sunset">'
        )


class TestCodeShortcodes:
    def test_inlines_content(self, env, src):
        (src / "hello.py").write_text("print('hello')")
        result = expand_shortcodes("<<hello.py>>", env, src)
        assert (
            '<pre><code class="language-python">print(&#39;hello&#39;)</code></pre>'
            in result
        )

    def test_language_mapping(self, env, src):
        (src / "app.js").write_text("const x = 1;")
        result = expand_shortcodes("<<app.js>>", env, src)
        assert "language-javascript" in result

    def test_content_escaping(self, env, src):
        (src / "bad.html").write_text("<script>alert('xss')</script>")
        result = expand_shortcodes("<<bad.html>>", env, src)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestTextShortcodes:
    def test_inlines_text(self, env, src):
        (src / "notes.txt").write_text("Some notes")
        result = expand_shortcodes("<<notes.txt>>", env, src)
        assert "<pre>Some notes</pre>" in result


class TestCsvShortcodes:
    def test_inlines_csv(self, env, src):
        (src / "data.csv").write_text("a,b\n1,2")
        result = expand_shortcodes("<<data.csv>>", env, src)
        assert "<pre>a,b\n1,2</pre>" in result


class TestShortcodeErrors:
    def test_unknown_extension(self, env, src):
        (src / "file.xyz").write_text("data")
        with pytest.raises(GalleryError, match="Unknown shortcode file type"):
            expand_shortcodes("<<file.xyz>>", env, src)

    def test_missing_file(self, env, src):
        with pytest.raises(GalleryError, match="file not found"):
            expand_shortcodes("<<missing.jpg>>", env, src)

    def test_missing_template(self, src):
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(src)),
            autoescape=True,
        )
        (src / "photo.jpg").write_bytes(b"fake")
        with pytest.raises(GalleryError, match="Missing template"):
            expand_shortcodes("<<photo.jpg>>", env, src)

    def test_unknown_directive(self, env, src):
        with pytest.raises(GalleryError, match="Unknown shortcode directive"):
            expand_shortcodes("<<unknown>>", env, src)


class TestGalleryShortcode:
    def test_basic_listing(self, env, src):
        mc = {}
        _img(src, "alpha.jpg", mc)
        _img(src, "beta.png", mc)
        result = expand_shortcodes("<<gallery>>", env, src, meta_cache=mc)
        assert "alpha.jpg:alpha.html" in result
        assert "beta.png:beta.html" in result

    def test_sort_name(self, env, src):
        mc = {}
        _img(src, "cherry.jpg", mc)
        _img(src, "apple.jpg", mc)
        _img(src, "banana.jpg", mc)
        result = expand_shortcodes("<<gallery sort=name>>", env, src, meta_cache=mc)
        assert (
            result
            == "apple.jpg:apple.html,banana.jpg:banana.html,cherry.jpg:cherry.html"
        )

    def test_sort_name_reverse(self, env, src):
        mc = {}
        _img(src, "cherry.jpg", mc)
        _img(src, "apple.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=name reverse>>", env, src, meta_cache=mc
        )
        assert result == "cherry.jpg:cherry.html,apple.jpg:apple.html"

    def test_sort_date(self, env, src):
        import os
        import time

        mc = {}
        _img(src, "old.jpg", mc)
        old_time = time.time() - 100
        os.utime(src / "old.jpg", (old_time, old_time))
        _img(src, "new.jpg", mc)
        result = expand_shortcodes("<<gallery sort=date>>", env, src, meta_cache=mc)
        assert result == "old.jpg:old.html,new.jpg:new.html"

    def test_sort_date_reverse(self, env, src):
        import os
        import time

        mc = {}
        _img(src, "old.jpg", mc)
        old_time = time.time() - 100
        os.utime(src / "old.jpg", (old_time, old_time))
        _img(src, "new.jpg", mc)
        result = expand_shortcodes(
            "<<gallery sort=date reverse>>", env, src, meta_cache=mc
        )
        assert result == "new.jpg:new.html,old.jpg:old.html"

    def test_filter(self, env, src):
        mc = {}
        _img(src, "photo.jpg", mc)
        _img(src, "photo.png", mc)
        result = expand_shortcodes("<<gallery filter=*.jpg>>", env, src, meta_cache=mc)
        assert "photo.jpg:photo.html" in result
        assert "photo.png" not in result

    def test_path_subdirectory(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        mc = {}
        _img(sub, "sunset.jpg", mc)
        result = expand_shortcodes("<<gallery path=photos>>", env, src, meta_cache=mc)
        assert "sunset.jpg:sunset.html" in result

    def test_path_relative_in_output(self, env, src):
        sub = src / "photos"
        sub.mkdir()
        mc = {}
        _img(sub, "sunset.jpg", mc)
        gallery_tpl = "{% for image in images %}{{ image.path }}{% endfor %}"
        tpl_dir = env.loader.searchpath[0]  # type: ignore[union-attr]
        (Path(tpl_dir) / "shortcodes" / "gallery.html").write_text(gallery_tpl)
        result = expand_shortcodes("<<gallery path=photos>>", env, src, meta_cache=mc)
        assert result == "photos/sunset.jpg"

    def test_empty_directory(self, env, src):
        result = expand_shortcodes("<<gallery>>", env, src, meta_cache={})
        assert result == ""

    def test_missing_directory(self, env, src):
        with pytest.raises(GalleryError, match="Gallery directory not found"):
            expand_shortcodes("<<gallery path=nonexistent>>", env, src, meta_cache={})

    def test_unknown_sort_key(self, env, src):
        with pytest.raises(GalleryError, match="Unknown gallery sort key"):
            expand_shortcodes("<<gallery sort=size>>", env, src, meta_cache={})

    def test_ignores_non_image_files(self, env, src):
        mc = {}
        _img(src, "photo.jpg", mc)
        (src / "readme.txt").write_text("hello")
        result = expand_shortcodes("<<gallery>>", env, src, meta_cache=mc)
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
        result = expand_shortcodes("<<gallery>>", env, src, meta_cache=mc)
        assert "title=Sunset" in result
        assert "alt=sunset" in result
        assert "exif=True" in result
        assert "iptc=True" in result
        assert "xmp=True" in result
