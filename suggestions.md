# Suggestions for Improvement

## Bugs



## Design

### Front matter parsing is mutated in `builder.py`

`del metadata["type"]` in `_build_markdown` is a side effect hidden in the build step. Extracting the template type should happen more explicitly, or `parse_front_matter` could return it separately.

### `parse_front_matter` unpacking is fragile

Line 59 in `config.py` does `key, value = _parse_line(...)` without guarding against a `None` return. It works only because the blank-line check on line 56 fires first. If `_parse_line` ever gains another `None`-return path (or if the iteration order changes), this will raise `TypeError`. Safer to check explicitly.

### Builder re-derives index.md status

`_target_paths` in `builder.py` checks `node.source.name.lower() == "index.md"` to determine path layout, but the scanner already knows this during index.md collapsing. A boolean field on `Node` (e.g. `is_index`) would remove that coupling and make the intent clearer.

### Shortcode type map is a maintenance burden

`_SHORTCODE_TYPE_MAP` and `_LANGUAGE_MAP` in `shortcodes.py` must be kept in sync and extended for every new file type. Consider a fallback for unrecognized extensions (e.g. treat as generic text, or derive the template name directly from the extension) to make the system open for extension without modifying the map.

### The builder does too much

Template loading, markdown rendering, image processing, static copying, listing generation, metadata extraction, and target sync are all in one module. The sync logic in particular is independent — it could be its own function called from `main()` after `build()`, which would make the separation between "generate files" and "clean up stale files" explicit in the orchestration.

## Testing

