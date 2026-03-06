from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import jinja2

from static_gallery.errors import GalleryError

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


def expand_shortcodes(body: str, env: jinja2.Environment, source_dir: Path) -> str:
    def _replace(match: re.Match) -> str:
        path_str = match.group(1)
        alt = match.group(2)
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
