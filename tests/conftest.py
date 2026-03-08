PAGE_TEMPLATE = "<html><head><title>{{ page.title }}</title></head><body>{{ content }}</body></html>"
IMAGE_TEMPLATE = '<html><head><title>{{ page.title }}</title></head><body><img src="{{ content }}"></body></html>'
LISTING_TEMPLATE = "<html><head><title>{{ page.title }}</title></head><body>{% for d in children.directories %}dir:{{ d.name }} {% endfor %}{% for p in children.pages %}page:{{ p.title }} {% endfor %}{% for i in children.images %}img:{{ i.stem }} {% endfor %}</body></html>"

SHORTCODE_IMAGE_TEMPLATE = '<img src="{{ path }}" alt="{{ alt }}">'
SHORTCODE_CODE_TEMPLATE = (
    '<pre><code class="language-{{ language }}">{{ content }}</code></pre>'
)


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
