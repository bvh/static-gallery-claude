# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static Gallery is a static site generator in Python with first-class image/gallery support. It uses Markdown (CommonMark) for content and Jinja templates for output. Early stage (0.1.0) — the README contains the full design spec.

## Commands

- **Run**: `uv run gallery` (CLI flags: `--source`, `--target`, `--config`, `--theme`, `--force`)
- **Run tests**: `uv run pytest`
- **Run a single test**: `uv run pytest tests/test_scanner.py::test_name` or `uv run pytest -k "keyword"`
- **Python 3.14**, managed with **uv**

## Architecture

**Two-pass build:** scan source tree into a `Node` tree, then walk the tree to produce output files.

### Modules

- `__init__.py` — CLI entry point (`main`). Parses args, wires together config → scan → build.
- `config.py` — Parses `site.conf` (key:value, split on first colon, case-insensitive keys, `#` comments) and markdown front matter (same format, no comments, terminated by blank line). Shared `_parse_line` helper.
- `scanner.py` — `scan()` walks the source tree with `os.walk`, classifies files by extension, and returns a `Node` tree. Skips dotfiles/dotdirs and the config file.
- `builder.py` — `build()` orchestrates the build: walks the `Node` tree, delegates rendering/copying to submodules, and returns the set of expected target paths. Contains `BuildContext` dataclass shared across the pipeline.
- `render.py` — Rendering functions (`build_markdown`, `build_image`, `build_listing`, `build_static`, `build_static_file`) that produce output files through Jinja templates. Also provides `load_template` and `try_load_template` helpers.
- `paths.py` — Path computation helpers (`node_segments`, `target_paths`) mapping nodes to target file locations.
- `freshness.py` — Incremental build logic (`compute_global_mtime`, `is_up_to_date`) for timestamp-based skip decisions.
- `sync.py` — `sync_target()` removes orphaned files and empty directories from the target after a build.
- `model.py` — `Node` dataclass (tree structure), `NodeType` enum (`MARKDOWN`, `IMAGE`, `STATIC`), and `IMAGE_EXTENSIONS` constant.
- `metadata.py` — Image metadata extraction via `pyexiv2`. Reads EXIF/IPTC/XMP, resolves titles and alt text from metadata with filename-stem fallbacks, and strips metadata on copy (keeping only artist/copyright/description/date).
- `shortcodes.py` — Expands `<< >>` shortcodes in markdown before parsing. Handles file embeds (image, code, text, csv) and the `<<gallery>>` directive. Each type renders through a Jinja template in `.theme/shortcodes/`.
- `errors.py` — `GalleryError` exception. All user-facing errors raise this; `main` catches it and prints to stderr.

### Key design details

- **index.md collapsing**: An `index.md` file is not a child node — it collapses into its parent directory node, setting that node's `node_type` to `MARKDOWN` and `source` to the index.md path. Directory nodes without an index.md have `node_type=None` and `source=None`.
- **Collision resolution**: In a directory, markdown stems are collected first. Images whose stem matches a markdown file are demoted to `STATIC` (copied but no HTML page generated).
- **Target sync**: After building, `sync_target` (called from `__init__.py`) removes files in target not in the expected set, then removes empty directories. This prevents stale files across builds.
- **Templates**: Loaded from `.theme/` at source root. Selected by type name (`page` for markdown, `image` for images). Markdown can override via `Type:` front matter key.
- **Shortcode expansion**: Shortcodes are expanded in markdown body text before CommonMark parsing. File shortcodes resolve relative to the markdown file's source directory; the `<<gallery>>` directive scans for images in the source tree.
- **Incremental builds**: Files are only rebuilt when source is newer than target. Template/config changes trigger full rebuilds. `--force` bypasses timestamp checks.
- **Metadata caching**: Image metadata reads are cached per-path via a `meta_cache` dict passed through the build pipeline, avoiding redundant pyexiv2 calls.
- **Theme static assets**: Files in `.theme/static/` are copied to the target root, preserving relative paths (e.g., `.theme/static/css/styles.css` → `target/css/styles.css`). They participate in incremental builds and are registered in `expected` so `sync_target` preserves them.
- **Strict fail-fast**: Any error stops the build immediately via `GalleryError`.

### Dependencies

- Runtime: `jinja2`, `mistletoe` (CommonMark), `pyexiv2` (image metadata), `markupsafe` (via jinja2, used for `Markup()` to mark rendered HTML as safe)
- Dev: `pytest`, `pre-commit`
- Linting/formatting: `ruff` (enforced via pre-commit hook)
