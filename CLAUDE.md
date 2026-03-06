# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static Gallery is a static site generator in Python with first-class image/gallery support. It uses Markdown (CommonMark) for content and Jinja templates for output. Early stage (0.1.0) — the README contains the full design spec.

## Commands

- **Run**: `uv run gallery` (CLI flags: `--source`, `--target`, `--config`)
- **Run tests**: `uv run pytest`
- **Run a single test**: `uv run pytest tests/test_scanner.py::test_name` or `uv run pytest -k "keyword"`
- **Python 3.14**, managed with **uv**

## Architecture

**Two-pass build:** scan source tree into a `Node` tree, then walk the tree to produce output files.

### Modules

- `__init__.py` — CLI entry point (`main`). Parses args, wires together config → scan → build.
- `config.py` — Parses `site.conf` (key:value, split on first colon, case-insensitive keys, `#` comments) and markdown front matter (same format, no comments, terminated by blank line). Shared `_parse_line` helper.
- `scanner.py` — `scan()` walks the source tree with `rglob`, classifies files by extension, and returns a `Node` tree. Skips dotfiles/dotdirs and the config file.
- `builder.py` — `build()` walks the `Node` tree, renders markdown/image pages through Jinja templates, copies static assets, then syncs the target directory (removes orphans).
- `model.py` — `Node` dataclass (tree structure) and `NodeType` enum (`MARKDOWN`, `IMAGE`, `STATIC`).
- `errors.py` — `GalleryError` exception. All user-facing errors raise this; `main` catches it and prints to stderr.

### Key design details

- **index.md collapsing**: An `index.md` file is not a child node — it collapses into its parent directory node, setting that node's `node_type` to `MARKDOWN` and `source` to the index.md path. Directory nodes without an index.md have `node_type=None` and `source=None`.
- **Collision resolution**: In a directory, markdown stems are collected first. Images whose stem matches a markdown file are demoted to `STATIC` (copied but no HTML page generated).
- **Target sync**: After building, `_sync_target` removes files in target not in the expected set, then removes empty directories. This prevents stale files across builds.
- **Templates**: Loaded from `.theme/` at source root. Selected by type name (`page` for markdown, `image` for images). Markdown can override via `Type:` front matter key.
- **Strict fail-fast**: Any error stops the build immediately via `GalleryError`.

### Dependencies

- Runtime: `jinja2`, `mistletoe` (CommonMark), `markupsafe` (via jinja2, used for `Markup()` to mark rendered HTML as safe)
- Dev: `pytest`, `pre-commit`
- Linting/formatting: `ruff` (enforced via pre-commit hook)
