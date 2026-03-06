import os
import subprocess
import sys


def _make_site(root):
    """Create a minimal valid site for integration testing."""
    (root / "site.conf").write_text(
        "title: Test Site\nurl: https://example.com/\nlanguage: en-us\n"
    )
    theme = root / ".theme"
    theme.mkdir()
    (theme / "page.html").write_text(
        "<html><head><title>{{ page.title }}</title></head>"
        "<body>{{ content }}</body></html>"
    )
    (theme / "image.html").write_text(
        "<html><head><title>{{ page.title }}</title></head>"
        '<body><img src="{{ content }}"></body></html>'
    )


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
        for f in (source / ".theme").iterdir():
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
