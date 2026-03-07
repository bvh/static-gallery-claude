from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path, PurePosixPath

import jinja2

from static_gallery.errors import GalleryError
from static_gallery.model import IMAGE_EXTENSIONS

_SHORTCODE_RE = re.compile(r"<<\s*([^\s>]+)(?:\s+(.+?))?\s*>>")

_SHORTCODE_TYPE_MAP = {
    ".jpeg": "image",
    ".jpg": "image",
    ".webp": "image",
    ".png": "image",
    ".gif": "image",
    ".svg": "image",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".css": "code",
    ".html": "code",
    ".sh": "code",
    ".json": "code",
    ".yaml": "code",
    ".yml": "code",
    ".toml": "code",
    ".xml": "code",
    ".sql": "code",
    ".rs": "code",
    ".go": "code",
    ".c": "code",
    ".h": "code",
    ".txt": "text",
    ".csv": "csv",
}

_INLINE_TYPES = {"code", "text", "csv"}

_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".css": "css",
    ".html": "html",
    ".sh": "bash",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".sql": "sql",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
}


def _parse_options(raw: str | None) -> dict[str, str | bool]:
    opts: dict[str, str | bool] = {}
    if not raw:
        return opts
    for token in raw.split():
        if "=" in token:
            key, value = token.split("=", 1)
            opts[key] = value
        else:
            opts[token] = True
    return opts


def _expand_gallery(
    raw_opts: str | None, env: jinja2.Environment, source_dir: Path
) -> str:
    opts = _parse_options(raw_opts)
    sort_key = opts.get("sort", "name")
    if sort_key not in ("name", "date"):
        raise GalleryError(f"Unknown gallery sort key: {sort_key}")
    reverse = bool(opts.get("reverse", False))
    filter_pattern = opts.get("filter")
    rel_path = opts.get("path")

    target_dir = source_dir / rel_path if rel_path else source_dir
    if not target_dir.is_dir():
        raise GalleryError(f"Gallery directory not found: {target_dir}")

    images = []
    for entry in target_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if filter_pattern and not fnmatch.fnmatch(entry.name, filter_pattern):
            continue
        images.append(entry)

    if sort_key == "name":
        images.sort(key=lambda p: p.name.lower(), reverse=reverse)
    elif sort_key == "date":
        images.sort(key=lambda p: os.path.getmtime(p), reverse=reverse)

    items = []
    for img in images:
        stem = img.stem
        items.append(
            {
                "path": str(img.relative_to(source_dir)),
                "filename": img.name,
                "stem": stem,
                "extension": img.suffix.lower(),
                "alt": stem.replace("-", " ").replace("_", " "),
                "page_url": f"{stem}.html",
            }
        )

    template_name = "shortcodes/gallery.html"
    try:
        template = env.get_template(template_name)
    except jinja2.TemplateNotFound:
        raise GalleryError(f"Missing template: .theme/{template_name}")
    except jinja2.TemplateSyntaxError as exc:
        raise GalleryError(f"Template syntax error in .theme/{template_name}: {exc}")

    return template.render(images=items, options=opts)


_DIRECTIVE_HANDLERS = {
    "gallery": _expand_gallery,
}


def expand_shortcodes(body: str, env: jinja2.Environment, source_dir: Path) -> str:
    def _replace(match: re.Match) -> str:
        path_str = match.group(1)
        raw_opts = match.group(2)

        if "." not in path_str:
            handler = _DIRECTIVE_HANDLERS.get(path_str)
            if handler is None:
                raise GalleryError(f"Unknown shortcode directive: {path_str}")
            return handler(raw_opts, env, source_dir)

        alt = raw_opts
        pp = PurePosixPath(path_str)
        ext = pp.suffix.lower()

        type_name = _SHORTCODE_TYPE_MAP.get(ext)
        if type_name is None:
            raise GalleryError(f"Unknown shortcode file type: {path_str}")

        resolved = source_dir / path_str
        if not resolved.is_file():
            raise GalleryError(f"Shortcode file not found: {resolved}")

        context: dict[str, str] = {
            "path": path_str,
            "filename": pp.name,
            "stem": pp.stem,
            "extension": ext,
            "alt": alt
            if alt is not None
            else pp.stem.replace("-", " ").replace("_", " "),
        }

        if type_name in _INLINE_TYPES:
            try:
                context["content"] = resolved.read_text(encoding="utf-8")
            except OSError as exc:
                raise GalleryError(f"Cannot read shortcode file {resolved}: {exc}")
            context["language"] = _LANGUAGE_MAP.get(ext, "")

        template_name = f"shortcodes/{type_name}.html"
        try:
            template = env.get_template(template_name)
        except jinja2.TemplateNotFound:
            raise GalleryError(f"Missing template: .theme/{template_name}")
        except jinja2.TemplateSyntaxError as exc:
            raise GalleryError(
                f"Template syntax error in .theme/{template_name}: {exc}"
            )

        return template.render(**context)

    return _SHORTCODE_RE.sub(_replace, body)
