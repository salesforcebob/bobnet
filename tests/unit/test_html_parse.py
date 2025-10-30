from app.simulate.html_parse import extract_image_sources, extract_links


def test_extract_image_sources_basic():
    html = '<img src="https://a/p1.png"><img src="/local.png"><img src="http://b/p2.jpg">'
    urls = extract_image_sources(html)
    assert urls == ["https://a/p1.png", "http://b/p2.jpg"]


def test_extract_links_dedup_and_scheme():
    html = '<a href="https://x/a">A</a><a href="https://x/a">B</a><a href="mailto:foo">M</a>'
    links = extract_links(html)
    assert links == ["https://x/a"]
