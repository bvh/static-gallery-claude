from __future__ import annotations

from pathlib import Path

from static_gallery.errors import GalleryError


def _parse_line(line: str, *, allow_comments: bool) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if allow_comments and stripped.startswith("#"):
        return None
    if ":" not in stripped:
        raise GalleryError(f"Malformed line (no colon): {line.rstrip()}")
    key, _, value = stripped.partition(":")
    return key.strip().lower(), value.strip()


def parse_config(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GalleryError(f"Cannot read config file: {exc}")

    config: dict[str, str] = {}
    for line in text.splitlines():
        result = _parse_line(line, allow_comments=True)
        if result is None:
            continue
        key, value = result
        config[key] = value

    for required in ("title", "url", "language"):
        if required not in config:
            raise GalleryError(f"Missing required config key: {required}")

    return config


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text:
        return {}, ""

    lines = text.splitlines()

    # Check if first line looks like a key:value pair
    first = lines[0].strip()
    if not first or ":" not in first:
        return {}, text

    meta: dict[str, str] = {}
    body_start = len(lines)

    for i, line in enumerate(lines):
        if line.strip() == "":
            body_start = i + 1
            break
        key, value = _parse_line(line, allow_comments=False)
        meta[key] = value

    body = "\n".join(lines[body_start:])
    return meta, body
