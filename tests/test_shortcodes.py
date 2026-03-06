import jinja2
import pytest

from static_gallery.errors import GalleryError
from static_gallery.shortcodes import expand_shortcodes

IMAGE_TPL = '<img src="{{ path }}" alt="{{ alt }}">'
CODE_TPL = '<pre><code class="language-{{ language }}">{{ content }}</code></pre>'
TEXT_TPL = "<pre>{{ content }}</pre>"
CSV_TPL = "<pre>{{ content }}</pre>"


@pytest.fixture
def env(tmp_path):
    tpl_dir = tmp_path / "shortcodes"
    tpl_dir.mkdir()
    (tpl_dir / "image.html").write_text(IMAGE_TPL)
    (tpl_dir / "code.html").write_text(CODE_TPL)
    (tpl_dir / "text.html").write_text(TEXT_TPL)
    (tpl_dir / "csv.html").write_text(CSV_TPL)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tmp_path)),
        autoescape=True,
    )


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    return d


def _img(src, name="photo.jpg"):
    f = src / name
    f.write_bytes(b"fake")
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
