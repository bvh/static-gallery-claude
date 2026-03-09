from pathlib import Path
from unittest.mock import patch, MagicMock

from static_gallery.metadata import (
    copy_image_stripped,
    get_image_metadata,
    read_image_metadata,
    resolve_title,
    resolve_alt,
    _shorten_key,
    _extract_lang_alt,
)


class TestShortenKey:
    def test_iptc_key(self):
        assert _shorten_key("Iptc.Application2.ObjectName") == "ObjectName"

    def test_exif_key(self):
        assert _shorten_key("Exif.Photo.ISO") == "ISO"

    def test_xmp_simple_key(self):
        assert _shorten_key("Xmp.dc.title") == "title"

    def test_xmp_structured_key_preserves_path(self):
        key = "Xmp.crs.FilterList/crs:Filters[1]/crs:Title"
        assert _shorten_key(key) == "FilterList/crs:Filters[1]/crs:Title"

    def test_xmp_camera_profile_key(self):
        key = "Xmp.photoshop.CameraProfiles[1]/stCamera:CameraPrettyName"
        assert _shorten_key(key) == "CameraProfiles[1]/stCamera:CameraPrettyName"

    def test_single_segment(self):
        assert _shorten_key("Title") == "Title"

    def test_two_segments(self):
        assert _shorten_key("Exif.ISO") == "Exif.ISO"


class TestExtractLangAlt:
    def test_extracts_default(self):
        assert _extract_lang_alt({'lang="x-default"': "Hello"}) == "Hello"

    def test_returns_none_for_missing_key(self):
        assert _extract_lang_alt({"other": "value"}) is None

    def test_returns_none_for_non_dict(self):
        assert _extract_lang_alt("plain string") is None


class TestResolveTitle:
    def test_iptc_object_name_first(self):
        meta = {
            "iptc": {"ObjectName": "My Title"},
            "xmp": {"title": {'lang="x-default"': "XMP Title"}},
        }
        assert resolve_title("filename-stem", meta) == "My Title"

    def test_xmp_title_second(self):
        meta = {"iptc": {}, "xmp": {"title": {'lang="x-default"': "XMP Title"}}}
        assert resolve_title("filename-stem", meta) == "XMP Title"

    def test_falls_back_to_stem(self):
        meta = {"iptc": {}, "xmp": {}}
        assert resolve_title("my-cool_photo", meta) == "My Cool Photo"

    def test_empty_metadata(self):
        assert resolve_title("test-image", {}) == "Test Image"


class TestResolveAlt:
    def test_xmp_alt_text(self):
        meta = {
            "xmp": {"AltTextAccessibility": {'lang="x-default"': "A beautiful sunset"}}
        }
        assert resolve_alt("sunset", meta) == "A beautiful sunset"

    def test_falls_back_to_stem(self):
        meta = {"xmp": {}}
        assert resolve_alt("my-cool_photo", meta) == "my cool photo"

    def test_empty_metadata(self):
        assert resolve_alt("test-image", {}) == "test image"


class TestReadImageMetadata:
    def test_returns_empty_on_failure(self, tmp_path):
        fake = tmp_path / "nonexistent.jpg"
        result = read_image_metadata(fake)
        assert result == {
            "exif": {},
            "iptc": {},
            "xmp": {},
            "width": None,
            "height": None,
        }

    def test_returns_empty_on_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "bad.jpg"
        corrupt.write_bytes(b"not an image")
        result = read_image_metadata(corrupt)
        assert result == {
            "exif": {},
            "iptc": {},
            "xmp": {},
            "width": None,
            "height": None,
        }

    def test_reads_real_image(self):
        path = Path("BVH_0497-4x5.jpg")
        if not path.exists():
            return  # skip if test image not available
        result = read_image_metadata(path)
        assert result["iptc"]["ObjectName"] == "Space Needle at Night"
        assert "exif" in result
        assert "xmp" in result
        assert isinstance(result["width"], int) and result["width"] > 0
        assert isinstance(result["height"], int) and result["height"] > 0

    def test_keys_are_shortened(self):
        mock_img = MagicMock()
        mock_img.read_exif.return_value = {"Exif.Photo.ISO": "400"}
        mock_img.read_iptc.return_value = {"Iptc.Application2.ObjectName": "Test"}
        mock_img.read_xmp.return_value = {
            "Xmp.dc.title": "Title",
            "Xmp.crs.FilterList/crs:Filters[1]/crs:Name": "Enhance",
        }
        mock_img.get_pixel_width.return_value = 1920
        mock_img.get_pixel_height.return_value = 1080

        with patch("static_gallery.metadata.pyexiv2.Image", return_value=mock_img):
            result = read_image_metadata(Path("test.jpg"))

        assert result["exif"] == {"ISO": "400"}
        assert result["iptc"] == {"ObjectName": "Test"}
        assert result["xmp"] == {
            "title": "Title",
            "FilterList/crs:Filters[1]/crs:Name": "Enhance",
        }
        assert result["width"] == 1920
        assert result["height"] == 1080
        mock_img.close.assert_called_once()

    def test_dimensions_flow_through_cache(self):
        mock_img = MagicMock()
        mock_img.read_exif.return_value = {}
        mock_img.read_iptc.return_value = {}
        mock_img.read_xmp.return_value = {}
        mock_img.get_pixel_width.return_value = 800
        mock_img.get_pixel_height.return_value = 600

        cache = {}
        path = Path("cached.jpg")
        with patch("static_gallery.metadata.pyexiv2.Image", return_value=mock_img):
            result = get_image_metadata(path, cache)

        assert result["width"] == 800
        assert result["height"] == 600
        # Second call should use cache
        result2 = get_image_metadata(path, cache)
        assert result2 is result

    def test_warns_on_failure(self, tmp_path, capsys):
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"not an image")
        read_image_metadata(bad)
        captured = capsys.readouterr()
        assert "Warning: could not read metadata" in captured.err


class TestCopyImageStripped:
    def test_keeps_allowed_fields_removes_others(self, tmp_path):
        src = tmp_path / "src.jpg"
        dest = tmp_path / "dest.jpg"
        src.write_bytes(b"fake")

        mock_img = MagicMock()
        mock_img.read_exif.return_value = {
            "Exif.Image.Artist": "Alice",
            "Exif.Image.Make": "Canon",
            "Exif.Photo.DateTimeOriginal": "2025:01:01 12:00:00",
            "Exif.Photo.LensModel": "50mm",
        }
        mock_img.read_iptc.return_value = {
            "Iptc.Application2.Copyright": "2025 Alice",
            "Iptc.Application2.Keywords": "test",
        }
        mock_img.read_xmp.return_value = {
            "Xmp.dc.title": {'lang="x-default"': "My Photo"},
            "Xmp.crs.Version": "15.0",
        }

        with patch("static_gallery.metadata.pyexiv2.Image", return_value=mock_img):
            copy_image_stripped(src, dest)

        mock_img.clear_exif.assert_called_once()
        mock_img.clear_iptc.assert_called_once()
        mock_img.clear_xmp.assert_called_once()

        exif_written = mock_img.modify_exif.call_args[0][0]
        assert exif_written == {
            "Exif.Image.Artist": "Alice",
            "Exif.Photo.DateTimeOriginal": "2025:01:01 12:00:00",
        }

        iptc_written = mock_img.modify_iptc.call_args[0][0]
        assert iptc_written == {"Iptc.Application2.Copyright": "2025 Alice"}

        xmp_written = mock_img.modify_xmp.call_args[0][0]
        assert xmp_written == {"Xmp.dc.title": {'lang="x-default"': "My Photo"}}

        mock_img.close.assert_called_once()
        assert dest.read_bytes() == b"fake"

    def test_no_modify_called_when_no_fields_kept(self, tmp_path):
        src = tmp_path / "src.jpg"
        dest = tmp_path / "dest.jpg"
        src.write_bytes(b"fake")

        mock_img = MagicMock()
        mock_img.read_exif.return_value = {"Exif.Image.Make": "Canon"}
        mock_img.read_iptc.return_value = {}
        mock_img.read_xmp.return_value = {"Xmp.crs.Version": "15.0"}

        with patch("static_gallery.metadata.pyexiv2.Image", return_value=mock_img):
            copy_image_stripped(src, dest)

        mock_img.modify_exif.assert_not_called()
        mock_img.modify_iptc.assert_not_called()
        mock_img.modify_xmp.assert_not_called()

    def test_still_copies_on_metadata_failure(self, tmp_path, capsys):
        src = tmp_path / "src.jpg"
        dest = tmp_path / "dest.jpg"
        src.write_bytes(b"image data")

        with patch(
            "static_gallery.metadata.pyexiv2.Image", side_effect=Exception("bad")
        ):
            copy_image_stripped(src, dest)

        assert dest.read_bytes() == b"image data"
        captured = capsys.readouterr()
        assert "Warning: could not strip metadata" in captured.err

    def test_real_image(self, tmp_path):
        path = Path("BVH_0497-4x5.jpg")
        if not path.exists():
            return

        dest = tmp_path / "stripped.jpg"
        copy_image_stripped(path, dest)
        meta = read_image_metadata(dest)
        assert meta["iptc"].get("Copyright")
        assert meta["exif"].get("Artist")
        assert meta["exif"].get("DateTimeOriginal")
        # Editing metadata should be gone
        assert "LensModel" not in meta["exif"]
        assert "Make" not in meta["exif"]
