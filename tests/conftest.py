from static_gallery.model import Node, NodeType

PAGE_TEMPLATE = "<html><head><title>{{ page.title }}</title></head><body>{{ content }}</body></html>"
IMAGE_TEMPLATE = '<html><head><title>{{ page.title }}</title></head><body><img src="{{ content }}"></body></html>'
LISTING_TEMPLATE = "<html><head><title>{{ page.title }}</title></head><body>{% for d in children.directories %}dir:{{ d.name }} {% endfor %}{% for p in children.pages %}page:{{ p.title }} {% endfor %}{% for i in children.images %}img:{{ i.stem }} {% endfor %}</body></html>"

SHORTCODE_IMAGE_TEMPLATE = '<img src="{{ path }}" alt="{{ alt }}">'
SHORTCODE_CODE_TEMPLATE = (
    '<pre><code class="language-{{ language }}">{{ content }}</code></pre>'
)

EMPTY_META = {"exif": {}, "iptc": {}, "xmp": {}}


def site_config():
    return {"title": "Test Site", "url": "https://example.com/", "language": "en-us"}


def make_tree(*children):
    root = Node(node_type=None, name="", source=None, parent=None)
    for c in children:
        c.parent = root
        root.children.append(c)
    return root


def make_index_tree(source, *children):
    root = make_tree(*children)
    root.node_type = NodeType.MARKDOWN
    root.source = source
    return root


def make_child(node_type, name, source, parent=None):
    return Node(node_type=node_type, name=name, source=source, parent=parent)


def setup_theme(source, page=PAGE_TEMPLATE, image=IMAGE_TEMPLATE, listing=None):
    theme = source / ".theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme / "page.html").write_text(page)
    (theme / "image.html").write_text(image)
    if listing is not None:
        (theme / "listing.html").write_text(listing)
    sc = theme / "shortcodes"
    sc.mkdir(exist_ok=True)
    (sc / "image.html").write_text(SHORTCODE_IMAGE_TEMPLATE)
    (sc / "code.html").write_text(SHORTCODE_CODE_TEMPLATE)
