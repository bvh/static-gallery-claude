# Suggestions for Improvement

## Bugs

### ~~Same-stem images silently collide on HTML target~~ (Fixed)

~~The scanner now detects duplicate image stems per directory and raises `GalleryError` listing the conflicting files. Images demoted to STATIC by markdown collision are excluded from the check. Case-insensitive.~~

### ~~Path traversal in shortcodes~~ (Fixed)

~~`expand_shortcodes` resolves `source_dir / path_str` with no confinement check. A shortcode like `<<../../etc/passwd.txt>>` would read files outside the source tree. After resolving, verify that the result is still within the source root (e.g. `resolved.resolve().is_relative_to(source_root)`).~~

### Custom --target inside source causes feedback loop

A user running `--target ./output` (no dot prefix) means the scanner will pick up previously-built HTML as source files on the next run. The default `.public` is safe because dotdirs are excluded, but nothing prevents a non-dot target inside source. Either warn/error when target is inside source without a dot prefix, or explicitly exclude the target path during scanning.

### ~~Gallery shortcode path option has same traversal issue~~ (Fixed)

~~`_expand_gallery` uses `source_dir / rel_path` for the `path=` option without verifying the result stays within the source tree. `<<gallery path=../../>>` would scan outside the source root.~~

### ~~Incremental build misses content dependencies~~ (Fixed)

~~Shortcodes can inline external files (code, text, csv), but the mtime check only considers the markdown source and the global mtime (templates + config). If an inlined file changes but the markdown file doesn't, the page won't be rebuilt. `shortcode_dependencies()` now scans markdown text for referenced files and gallery images; their mtimes are checked during incremental builds.~~

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

### Test templates are duplicated

The test templates are duplicated across `test_builder.py` and `test_cli.py`. A shared `conftest.py` fixture for creating a minimal site would reduce that.

### No tests for edge cases in `_sync_target` with symlinks or special files

`_sync_target` uses `rglob("*")` and checks `is_file()` / `is_dir()`, but doesn't account for symlinks, sockets, or other non-regular files that might exist in the target. Unlikely in practice but worth a defensive check or test.

### No tests for metadata stripping

`copy_image_stripped` has a silent fallback (copies without stripping on failure), but there are no tests verifying that the kept/stripped metadata sets are correct, or that the fallback path works.
