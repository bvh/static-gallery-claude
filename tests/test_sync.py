from static_gallery.builder import build
from static_gallery.sync import sync_target

from conftest import (
    make_index_tree as _make_index_tree,
    make_tree as _make_tree,
    setup_theme as _setup_theme,
    site_config as _site_config,
)


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


class TestSyncSymlinks:
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


class TestSyncVerbose:
    def test_prints_delete(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        stale = target / "old.html"
        stale.write_text("stale")

        sync_target(target, set(), verbose=True)

        err = capsys.readouterr().err
        assert "Delete:" in err
        assert not stale.exists()

    def test_prints_remove_dir(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        empty = target / "empty"
        empty.mkdir()

        sync_target(target, set(), verbose=True)

        err = capsys.readouterr().err
        assert "Remove:" in err


class TestSyncDryRun:
    def test_no_delete(self, tmp_path, capsys):
        target = tmp_path / "target"
        target.mkdir()
        stale = target / "old.html"
        stale.write_text("stale")

        sync_target(target, set(), dry_run=True, verbose=True)

        assert stale.exists()  # not deleted
        err = capsys.readouterr().err
        assert "Would delete:" in err
