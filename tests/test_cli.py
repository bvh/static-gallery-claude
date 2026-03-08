import argparse
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from static_gallery import _resolve_dirs, main
from static_gallery.errors import GalleryError

from conftest import setup_theme


def _make_site(root):
    """Create a minimal valid site for integration testing."""
    (root / "site.conf").write_text(
        "title: Test Site\nurl: https://example.com/\nlanguage: en-us\n"
    )
    setup_theme(root)


class TestCLIIntegration:
    def test_full_pipeline(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)

        (source / "index.md").write_text("Title: Home\n\nWelcome.")

        target = source / ".public"
        result = subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (target / "index.html").exists()
        html = (target / "index.html").read_text()
        assert "<title>Home</title>" in html
        assert "Welcome." in html

    def test_custom_target(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)
        (source / "index.md").write_text("Title: Home\n\nHi.")

        target = tmp_path / "output"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "static_gallery",
                "--source",
                str(source),
                "--target",
                str(target),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (target / "index.html").exists()

    def test_missing_source_exits(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "static_gallery",
                "--source",
                str(tmp_path / "nonexistent"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_end_to_end_readme_example(self, tmp_path):
        """Verify the example from the README spec."""
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)

        (source / "index.md").write_text("Title: Home\n\nWelcome.")
        (source / "about.md").write_text("Title: About\n\nAbout us.")
        (source / "portrait.jpg").write_bytes(b"fake jpg data")
        (source / "styles.css").write_text("body { margin: 0; }")

        news = source / "news"
        news.mkdir()
        (news / "index.md").write_text("Title: News\n\nLatest news.")
        (news / "today.md").write_text("Title: Today\n\nToday's news.")
        (news / "today.jpg").write_bytes(b"fake jpg")

        target = source / ".public"
        result = subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        # Markdown → HTML
        assert (target / "index.html").exists()
        assert (target / "about.html").exists()
        assert (target / "news" / "index.html").exists()
        assert (target / "news" / "today.html").exists()

        # Image → HTML + copy (portrait has no collision)
        assert (target / "portrait.html").exists()
        assert (target / "portrait.jpg").exists()

        # Collision: today.md wins, today.jpg is static only
        today_html = (target / "news" / "today.html").read_text()
        assert "<title>Today</title>" in today_html  # from markdown, not image
        assert (target / "news" / "today.jpg").exists()  # copied as static

        # Static asset
        assert (target / "styles.css").read_text() == "body { margin: 0; }"

    def test_stale_file_cleanup(self, tmp_path):
        """Build twice: remove a source file, verify target cleaned up."""
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)

        (source / "index.md").write_text("Title: Home\n\nHi.")
        (source / "old.md").write_text("Title: Old\n\nOld page.")

        target = source / ".public"

        # First build
        subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        assert (target / "old.html").exists()

        # Remove source file and rebuild
        (source / "old.md").unlink()
        subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        assert not (target / "old.html").exists()
        assert (target / "index.html").exists()

    def test_custom_config_path(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)

        # Move config to a custom location
        custom_conf = tmp_path / "custom.conf"
        (source / "site.conf").rename(custom_conf)

        (source / "index.md").write_text("Title: Home\n\nHi.")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "static_gallery",
                "--source",
                str(source),
                "--config",
                str(custom_conf),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (source / ".public" / "index.html").exists()

    def test_force_flag(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)
        (source / "index.md").write_text("Title: Home\n\nHi.")

        target = source / ".public"

        # First build
        subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        html = target / "index.html"
        assert html.exists()

        # Set output to a known past time
        past = 1_000_000_000.0
        os.utime(html, (past, past))
        os.utime(source / "index.md", (past, past))
        os.utime(source / "site.conf", (past, past))
        for f in (source / ".theme").rglob("*"):
            os.utime(f, (past, past))

        # Rebuild without --force: should skip (mtime unchanged)
        subprocess.run(
            [sys.executable, "-m", "static_gallery", "--source", str(source)],
            capture_output=True,
            text=True,
        )
        assert html.stat().st_mtime == past

        # Rebuild with --force: should rewrite
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "static_gallery",
                "--source",
                str(source),
                "--force",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert html.stat().st_mtime > past


class TestStage:
    def test_stage_starts_server(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        _make_site(source)
        (source / "index.md").write_text("Title: Home\n\nHi.")

        with (
            patch(
                "sys.argv",
                [
                    "gallery",
                    "--source",
                    str(source),
                    "--stage",
                    "--port",
                    "9123",
                ],
            ),
            patch("http.server.HTTPServer") as mock_server_cls,
        ):
            mock_server = MagicMock()
            mock_server.serve_forever.side_effect = KeyboardInterrupt
            mock_server_cls.return_value = mock_server

            main()

            mock_server_cls.assert_called_once()
            addr, handler_cls = mock_server_cls.call_args[0]
            assert addr == ("127.0.0.1", 9123)

            # Verify handler is configured with the target directory
            target = (source / ".public").resolve()
            assert handler_cls.keywords["directory"] == str(target)

            mock_server.serve_forever.assert_called_once()
            mock_server.server_close.assert_called_once()


def _make_args(**kwargs):
    """Create an argparse.Namespace with default None values."""
    defaults = {
        "source": None,
        "target": None,
        "config": None,
        "theme": None,
        "force": False,
        "stage": False,
        "port": 8000,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestResolveDirs:
    def test_target_inside_source_rejected(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
        )

        args = _make_args(source=source, target=source / "output")
        with pytest.raises(GalleryError, match="inside source"):
            _resolve_dirs(args)

    def test_target_equals_source_rejected(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
        )

        args = _make_args(source=source, target=source)
        with pytest.raises(GalleryError, match="inside source"):
            _resolve_dirs(args)

    def test_dotdir_target_inside_source_allowed(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
        )

        args = _make_args(source=source, target=source / ".hidden")
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert tgt == (source / ".hidden").resolve()

    def test_target_outside_source_allowed(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
        )

        args = _make_args(source=source, target=tmp_path / "output")
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert tgt == (tmp_path / "output").resolve()

    def test_default_theme(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
        )

        args = _make_args(source=source)
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert theme == (source / ".theme").resolve()

    def test_theme_from_config(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        my_theme = tmp_path / "my-theme"
        my_theme.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\ntheme: ../my-theme\n"
        )

        args = _make_args(source=source)
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert theme == my_theme.resolve()

    def test_theme_from_cli_overrides_config(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        cli_theme = tmp_path / "cli-theme"
        cli_theme.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\ntheme: ../config-theme\n"
        )

        args = _make_args(source=source, theme=cli_theme)
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert theme == cli_theme.resolve()

    def test_source_from_config(self, tmp_path):
        site_dir = tmp_path / "site"
        site_dir.mkdir()
        (tmp_path / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\nsource: ./site\n"
        )

        args = _make_args(config=tmp_path / "site.conf")
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert src == site_dir.resolve()

    def test_target_from_config(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        output = tmp_path / "public"
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\ntarget: ../public\n"
        )

        args = _make_args(source=source)
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert tgt == output.resolve()

    def test_target_from_config_inside_source_rejected(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\ntarget: ./site/output\n"
        )

        args = _make_args(config=source / "site.conf")
        with pytest.raises(GalleryError, match="inside source"):
            _resolve_dirs(args)

    def test_internal_keys_stripped_from_config(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\n"
            "source: .\ntarget: ../out\ntheme: .theme\n"
        )

        args = _make_args(source=source)
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert "source" not in conf
        assert "target" not in conf
        assert "theme" not in conf
        assert conf["title"] == "Test"

    def test_cli_flags_override_config(self, tmp_path):
        source = tmp_path / "site"
        source.mkdir()
        other_source = tmp_path / "other"
        other_source.mkdir()
        (source / "site.conf").write_text(
            "title: Test\nurl: https://example.com/\nlanguage: en-us\nsource: ./wrong\ntarget: ./wrong-target\n"
        )

        args = _make_args(
            source=other_source,
            target=tmp_path / "out",
            config=source / "site.conf",
        )
        src, tgt, theme, cfg, conf = _resolve_dirs(args)
        assert src == other_source.resolve()
        assert tgt == (tmp_path / "out").resolve()
