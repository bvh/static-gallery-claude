from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path, PurePosixPath

import jinja2

from static_gallery.errors import GalleryError
from static_gallery.metadata import (
    get_image_metadata,
    resolve_alt,
    resolve_date,
    resolve_title,
    stem_to_alt,
)
from static_gallery.model import IMAGE_EXTENSIONS

_SHORTCODE_RE = re.compile(r"<<\s*([^\s>]+)(?:\s+(.+?))?\s*>>")

_ESCAPE_PLACEHOLDER = "\x00ESCAPED_SHORTCODE\x00"

_SHORTCODE_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS | {".gif", ".svg"}

_INLINE_TYPES = {"code", "text", "csv"}

_LANGUAGE_OVERRIDES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".sh": "bash",
    ".yml": "yaml",
    ".rs": "rust",
    ".h": "c",
}


_KNOWN_CODE_EXTENSIONS = set(_LANGUAGE_OVERRIDES) | {
    ".css",
    ".html",
    ".json",
    ".yaml",
    ".toml",
    ".xml",
    ".sql",
    ".go",
    ".c",
}


def _shortcode_type(ext: str) -> str:
    """Derive the shortcode type from a file extension."""
    if ext in _SHORTCODE_IMAGE_EXTENSIONS:
        return "image"
    if ext == ".txt":
        return "text"
    if ext == ".csv":
        return "csv"
    return "code"


def _language_for(ext: str) -> str:
    """Derive the language name from a file extension."""
    return _LANGUAGE_OVERRIDES.get(ext, ext.lstrip("."))


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


def _resolve_file_path(
    path_str: str,
    source_dir: Path,
    resolved_root: Path | None,
) -> Path | None:
    """Resolve a shortcode file path, returning None if invalid or missing."""
    ext = PurePosixPath(path_str).suffix.lower()
    if not ext:
        return None
    resolved = source_dir / path_str
    if resolved_root is not None and not resolved.resolve().is_relative_to(
        resolved_root
    ):
        return None
    if not resolved.is_file():
        return None
    return resolved


def _resolve_gallery_dir(
    raw_opts: str | None,
    source_dir: Path,
    resolved_root: Path | None,
) -> tuple[Path, str | None] | None:
    """Resolve gallery target directory and filter pattern from options.

    Returns (target_dir, filter_pattern) or None on traversal/missing dir.
    """
    opts = _parse_options(raw_opts)
    rel_path = opts.get("path")
    if isinstance(rel_path, bool):
        rel_path = None
    filter_pattern = opts.get("filter")
    if isinstance(filter_pattern, bool):
        filter_pattern = None

    target_dir = source_dir / rel_path if rel_path else source_dir
    if (
        rel_path
        and resolved_root is not None
        and not target_dir.resolve().is_relative_to(resolved_root)
    ):
        return None
    if not target_dir.is_dir():
        return None

    return target_dir, filter_pattern


def _collect_gallery_images(target_dir: Path, filter_pattern: str | None) -> list[Path]:
    """Collect image files from a directory, optionally filtered by glob."""
    images = []
    for entry in target_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if filter_pattern and not fnmatch.fnmatch(entry.name, filter_pattern):
            continue
        images.append(entry)
    return images


def _expand_gallery(
    raw_opts: str | None,
    *,
    env: jinja2.Environment,
    source_dir: Path,
    meta_cache: dict[Path, dict[str, dict]],
    resolved_root: Path | None = None,
) -> str:
    opts = _parse_options(raw_opts)
    sort_key = opts.get("sort", "name")
    if sort_key not in ("name", "date"):
        raise GalleryError(f"Unknown gallery sort key: {sort_key}")
    reverse = bool(opts.get("reverse", False))
    rel_path = opts.get("path")

    target_dir = source_dir / rel_path if rel_path else source_dir
    if (
        rel_path
        and resolved_root is not None
        and not target_dir.resolve().is_relative_to(resolved_root)
    ):
        raise GalleryError(f"Shortcode path escapes source tree: {rel_path}")
    if not target_dir.is_dir():
        raise GalleryError(f"Gallery directory not found: {target_dir}")

    filter_pattern = opts.get("filter")
    if isinstance(filter_pattern, bool):
        filter_pattern = None
    images = _collect_gallery_images(target_dir, filter_pattern)

    if sort_key == "name":
        images.sort(key=lambda p: p.name.lower(), reverse=reverse)
    elif sort_key == "date":
        images.sort(
            key=lambda p: resolve_date(p, get_image_metadata(p, meta_cache)),
            reverse=reverse,
        )

    items = []
    for img in images:
        stem = img.stem
        image_meta = get_image_metadata(img, meta_cache)
        items.append(
            {
                "path": str(img.relative_to(source_dir)),
                "filename": img.name,
                "stem": stem,
                "extension": img.suffix.lower(),
                "alt": resolve_alt(stem, image_meta),
                "title": resolve_title(stem, image_meta),
                "page_url": f"{stem}.html",
                "exif": image_meta["exif"],
                "iptc": image_meta["iptc"],
                "xmp": image_meta["xmp"],
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


def shortcode_dependencies(
    body: str,
    source_dir: Path,
    source_root: Path | None = None,
) -> set[Path]:
    """Return resolved file paths referenced by shortcodes in body text."""
    resolved_root = source_root.resolve() if source_root is not None else None
    deps: set[Path] = set()
    body = body.replace("\\<<", "")

    for match in _SHORTCODE_RE.finditer(body):
        path_str = match.group(1)
        raw_opts = match.group(2)

        if "." not in path_str:
            if path_str == "gallery":
                result = _resolve_gallery_dir(raw_opts, source_dir, resolved_root)
                if result is not None:
                    target_dir, filter_pattern = result
                    deps.update(_collect_gallery_images(target_dir, filter_pattern))
            continue

        resolved = _resolve_file_path(path_str, source_dir, resolved_root)
        if resolved is not None:
            deps.add(resolved)

    return deps


def expand_shortcodes(
    body: str,
    env: jinja2.Environment,
    source_dir: Path,
    meta_cache: dict[Path, dict[str, dict]] | None = None,
    source_root: Path | None = None,
) -> str:
    if meta_cache is None:
        meta_cache = {}
    resolved_root = source_root.resolve() if source_root is not None else None
    body = body.replace("\\<<", _ESCAPE_PLACEHOLDER)

    def _replace(match: re.Match) -> str:
        path_str = match.group(1)
        raw_opts = match.group(2)

        if "." not in path_str:
            handler = _DIRECTIVE_HANDLERS.get(path_str)
            if handler is None:
                raise GalleryError(f"Unknown shortcode directive: {path_str}")
            return handler(
                raw_opts,
                env=env,
                source_dir=source_dir,
                meta_cache=meta_cache,
                resolved_root=resolved_root,
            )

        alt = raw_opts
        pp = PurePosixPath(path_str)
        ext = pp.suffix.lower()

        type_name = _shortcode_type(ext)
        if type_name == "code" and ext not in _KNOWN_CODE_EXTENSIONS:
            print(
                f"Warning: unknown shortcode file type '{ext}', treating as code: {path_str}",
                file=sys.stderr,
            )

        resolved = source_dir / path_str
        if resolved_root is not None and not resolved.resolve().is_relative_to(
            resolved_root
        ):
            raise GalleryError(f"Shortcode path escapes source tree: {path_str}")
        if not resolved.is_file():
            raise GalleryError(f"Shortcode file not found: {resolved}")

        context: dict[str, str] = {
            "path": path_str,
            "filename": pp.name,
            "stem": pp.stem,
            "extension": ext,
            "alt": alt if alt is not None else stem_to_alt(pp.stem),
        }

        if type_name in _INLINE_TYPES:
            try:
                context["content"] = resolved.read_text(encoding="utf-8")
            except OSError as exc:
                raise GalleryError(f"Cannot read shortcode file {resolved}: {exc}")
            context["language"] = _language_for(ext)

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

    return _SHORTCODE_RE.sub(_replace, body).replace(_ESCAPE_PLACEHOLDER, "<<")
