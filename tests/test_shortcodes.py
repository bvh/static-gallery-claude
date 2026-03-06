from static_gallery.shortcodes import expand_shortcodes


class TestExpandShortcodes:
    def test_basic(self):
        assert expand_shortcodes("<<photo.jpg>>") == '<img src="photo.jpg" alt="photo">'

    def test_subdirectory_path(self):
        assert expand_shortcodes("<<photos/sunset.png>>") == '<img src="photos/sunset.png" alt="sunset">'

    def test_whitespace_tolerance(self):
        assert expand_shortcodes("<< photo.jpg >>") == '<img src="photo.jpg" alt="photo">'

    def test_multiple_same_line(self):
        result = expand_shortcodes("<<a.jpg>> and <<b.png>>")
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_multiple_separate_lines(self):
        result = expand_shortcodes("<<a.jpg>>\n<<b.png>>")
        assert '<img src="a.jpg" alt="a">' in result
        assert '<img src="b.png" alt="b">' in result

    def test_no_shortcodes(self):
        text = "Just some normal text."
        assert expand_shortcodes(text) == text

    def test_auto_alt_dashes_underscores(self):
        assert expand_shortcodes("<<my-cool_photo.jpg>>") == '<img src="my-cool_photo.jpg" alt="my cool photo">'

    def test_explicit_alt(self):
        assert expand_shortcodes("<<sunset.png A beautiful sunset>>") == '<img src="sunset.png" alt="A beautiful sunset">'

    def test_explicit_alt_with_padding(self):
        assert expand_shortcodes("<< sunset.png A beautiful sunset >>") == '<img src="sunset.png" alt="A beautiful sunset">'
