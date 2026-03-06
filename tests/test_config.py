import pytest
from static_gallery.config import parse_config, parse_front_matter
from static_gallery.errors import GalleryError


class TestParseConfig:
    def test_valid_config(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text("title: My Site\nurl: https://example.com/\nlanguage: en-us\n")
        result = parse_config(conf)
        assert result["title"] == "My Site"
        assert result["url"] == "https://example.com/"
        assert result["language"] == "en-us"

    def test_split_on_first_colon(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "title: My Site\nurl: https://example.com/path\nlanguage: en-us\n"
        )
        result = parse_config(conf)
        assert result["url"] == "https://example.com/path"

    def test_whitespace_trimmed(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "  title  :  My Site  \nurl: https://example.com/\nlanguage: en-us\n"
        )
        result = parse_config(conf)
        assert result["title"] == "My Site"

    def test_case_insensitive_keys(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text("TITLE: My Site\nURL: https://example.com/\nLanguage: en-us\n")
        result = parse_config(conf)
        assert result["title"] == "My Site"
        assert result["url"] == "https://example.com/"
        assert result["language"] == "en-us"

    def test_comments_skipped(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "# comment\ntitle: My Site\nurl: https://example.com/\nlanguage: en-us\n"
        )
        result = parse_config(conf)
        assert "#" not in "".join(result.keys())
        assert result["title"] == "My Site"

    def test_blank_lines_skipped(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "title: My Site\n\nurl: https://example.com/\n\nlanguage: en-us\n"
        )
        result = parse_config(conf)
        assert len(result) == 3

    def test_missing_required_key_exits(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text("title: My Site\n")
        with pytest.raises(GalleryError):
            parse_config(conf)

    def test_missing_file_exits(self, tmp_path):
        conf = tmp_path / "nonexistent.conf"
        with pytest.raises(GalleryError):
            parse_config(conf)

    def test_malformed_line_exits(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "title: My Site\nno colon here\nurl: https://example.com/\nlanguage: en-us\n"
        )
        with pytest.raises(GalleryError):
            parse_config(conf)

    def test_extra_keys_passed_through(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "title: My Site\nurl: https://example.com/\nlanguage: en-us\nauthor: Jane\n"
        )
        result = parse_config(conf)
        assert result["author"] == "Jane"

    def test_duplicate_keys_last_wins(self, tmp_path):
        conf = tmp_path / "site.conf"
        conf.write_text(
            "title: First\ntitle: Second\nurl: https://example.com/\nlanguage: en-us\n"
        )
        result = parse_config(conf)
        assert result["title"] == "Second"


class TestParseFrontMatter:
    def test_with_front_matter(self):
        text = "Title: My Post\nDate: 2026-03-01\n\nHello world."
        meta, body = parse_front_matter(text)
        assert meta["title"] == "My Post"
        assert meta["date"] == "2026-03-01"
        assert body == "Hello world."

    def test_no_front_matter(self):
        text = "Hello world.\n\nMore text."
        meta, body = parse_front_matter(text)
        assert meta == {}
        assert body == "Hello world.\n\nMore text."

    def test_empty_input(self):
        meta, body = parse_front_matter("")
        assert meta == {}
        assert body == ""

    def test_colon_in_value(self):
        text = "Title: My Post: Part 2\n\nBody."
        meta, body = parse_front_matter(text)
        assert meta["title"] == "My Post: Part 2"

    def test_type_key(self):
        text = "Type: image\nTitle: Photo\n\nBody."
        meta, body = parse_front_matter(text)
        assert meta["type"] == "image"

    def test_no_blank_terminator(self):
        text = "Title: My Post\nDate: 2026-03-01"
        meta, body = parse_front_matter(text)
        assert meta["title"] == "My Post"
        assert meta["date"] == "2026-03-01"
        assert body == ""

    def test_malformed_line_exits(self):
        text = "Title: My Post\nno colon here\n\nBody."
        with pytest.raises(GalleryError):
            parse_front_matter(text)

    def test_whitespace_trimmed(self):
        text = "  Title  :  My Post  \n\nBody."
        meta, body = parse_front_matter(text)
        assert meta["title"] == "My Post"

    def test_case_insensitive_keys(self):
        text = "TITLE: My Post\n\nBody."
        meta, body = parse_front_matter(text)
        assert "title" in meta
