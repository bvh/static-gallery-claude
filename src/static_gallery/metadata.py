from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pyexiv2


def _shorten_key(key: str) -> str:
    """Strip the two-segment namespace prefix, keeping the rest.

    Examples:
        "Iptc.Application2.ObjectName" → "ObjectName"
        "Xmp.dc.title" → "title"
        "Xmp.crs.FilterList/crs:Filters[1]/crs:Title" → "FilterList/crs:Filters[1]/crs:Title"
    """
    parts = key.split(".", 2)
    if len(parts) == 3:
        return parts[2]
    return key


def _extract_lang_alt(value: object) -> str | None:
    """Extract the default language string from an XMP lang-alt dict."""
    if isinstance(value, dict):
        return value.get('lang="x-default"')
    return None


def stem_to_title(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").title()


def stem_to_alt(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ")


def get_image_metadata(
    path: Path, cache: dict[Path, dict[str, dict]]
) -> dict[str, dict]:
    """Cached wrapper around read_image_metadata."""
    if path not in cache:
        cache[path] = read_image_metadata(path)
    return cache[path]


def read_image_metadata(path: Path) -> dict[str, dict]:
    """Read EXIF, IPTC, and XMP metadata from an image file.

    Returns {"exif": {...}, "iptc": {...}, "xmp": {...}} with shortened keys.
    On failure, returns empty dicts — metadata is supplemental.
    """
    result: dict[str, dict] = {"exif": {}, "iptc": {}, "xmp": {}}
    try:
        img = pyexiv2.Image(str(path))
        try:
            for category, reader in [
                ("exif", img.read_exif),
                ("iptc", img.read_iptc),
                ("xmp", img.read_xmp),
            ]:
                raw = reader()
                result[category] = {_shorten_key(k): v for k, v in raw.items()}
        finally:
            img.close()
    except Exception as exc:
        print(f"Warning: could not read metadata from {path}: {exc}", file=sys.stderr)
    return result


def resolve_date(path: Path, metadata: dict[str, dict]) -> float:
    """EXIF DateTimeOriginal if available, else filesystem mtime."""
    dto = metadata.get("exif", {}).get("DateTimeOriginal")
    if dto and isinstance(dto, str):
        try:
            return datetime.datetime.strptime(dto, "%Y:%m:%d %H:%M:%S").timestamp()
        except ValueError:
            pass
    return os.path.getmtime(path)


def resolve_title(stem: str, metadata: dict[str, dict]) -> str:
    """Determine image title from metadata, falling back to filename stem."""
    iptc_title = metadata.get("iptc", {}).get("ObjectName")
    if iptc_title:
        return iptc_title

    xmp_title = metadata.get("xmp", {}).get("title")
    if xmp_title:
        extracted = _extract_lang_alt(xmp_title)
        if extracted:
            return extracted

    return stem_to_title(stem)


def resolve_alt(stem: str, metadata: dict[str, dict]) -> str:
    """Determine alt text from metadata, falling back to filename stem."""
    xmp_alt = metadata.get("xmp", {}).get("AltTextAccessibility")
    if xmp_alt:
        extracted = _extract_lang_alt(xmp_alt)
        if extracted:
            return extracted

    return stem_to_alt(stem)


_KEEP_EXIF = {
    "Exif.Image.Artist",
    "Exif.Image.Copyright",
    "Exif.Image.ImageDescription",
    "Exif.Image.DateTime",
    "Exif.Photo.DateTimeOriginal",
    "Exif.Photo.DateTimeDigitized",
}

_KEEP_IPTC = {
    "Iptc.Application2.Byline",
    "Iptc.Application2.Copyright",
    "Iptc.Application2.Caption",
    "Iptc.Application2.DateCreated",
    "Iptc.Application2.TimeCreated",
}

_KEEP_XMP = {
    "Xmp.dc.creator",
    "Xmp.dc.rights",
    "Xmp.dc.description",
    "Xmp.dc.title",
    "Xmp.xmp.CreateDate",
    "Xmp.photoshop.DateCreated",
}


def copy_image_stripped(source: Path, dest: Path) -> None:
    """Copy an image file, stripping metadata except artist/copyright/description/date."""
    fd, tmp = tempfile.mkstemp(suffix=source.suffix, dir=dest.parent)
    try:
        os.close(fd)
        tmp_path = Path(tmp)
        shutil.copy2(source, tmp_path)
        img = pyexiv2.Image(str(tmp_path))
        try:
            exif = {k: v for k, v in img.read_exif().items() if k in _KEEP_EXIF}
            iptc = {k: v for k, v in img.read_iptc().items() if k in _KEEP_IPTC}
            xmp = {k: v for k, v in img.read_xmp().items() if k in _KEEP_XMP}
            img.clear_exif()
            img.clear_iptc()
            img.clear_xmp()
            if exif:
                img.modify_exif(exif)
            if iptc:
                img.modify_iptc(iptc)
            if xmp:
                img.modify_xmp(xmp)
        finally:
            img.close()
        tmp_path.replace(dest)
    except Exception as exc:
        Path(tmp).unlink(missing_ok=True)
        print(
            f"Warning: could not strip metadata from {source}: {exc}", file=sys.stderr
        )
        shutil.copy2(source, dest)
