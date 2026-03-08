# Suggestions for Improvement

## Bugs



## Design

### Config keys `source`, `target`, `theme` leak into template context

`parse_config` returns all keys from site.conf. The new `source`, `target`, and `theme` directory keys end up in `site_config`, which is passed to every template as `{{ site.source }}` etc. This exposes filesystem paths in rendered HTML and could hijack a site that already uses one of these key names for display purposes. Consider stripping the directory keys from `site_config` after resolving them in `_resolve_dirs`.

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

### Test templates are duplicated

The test templates are duplicated across `test_builder.py` and `test_cli.py`. A shared `conftest.py` fixture for creating a minimal site would reduce that.

