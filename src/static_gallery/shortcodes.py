import re
from pathlib import PurePosixPath

_SHORTCODE_RE = re.compile(r"<<\s*([^\s>]+)(?:\s+(.+?))?\s*>>")


def _replace_image(match: re.Match) -> str:
    path = match.group(1)
    alt = match.group(2)
    if alt is None:
        stem = PurePosixPath(path).stem
        alt = stem.replace("-", " ").replace("_", " ")
    return f'<img src="{path}" alt="{alt}">'


def expand_shortcodes(body: str) -> str:
    return _SHORTCODE_RE.sub(_replace_image, body)
