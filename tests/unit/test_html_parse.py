from app.simulate.html_parse import (
    extract_image_sources,
    extract_links,
    extract_links_with_rates,
    find_global_click_rate,
    LinkWithRate,
)


def test_extract_image_sources_basic():
    html = '<img src="https://a/p1.png"><img src="/local.png"><img src="http://b/p2.jpg">'
    urls = extract_image_sources(html)
    assert urls == ["https://a/p1.png", "http://b/p2.jpg"]


def test_extract_links_dedup_and_scheme():
    html = '<a href="https://x/a">A</a><a href="https://x/a">B</a><a href="mailto:foo">M</a>'
    links = extract_links(html)
    assert links == ["https://x/a"]


def test_find_global_click_rate_valid():
    html = '<div data-scope="global" data-click-rate="0.7"></div>'
    rate = find_global_click_rate(html)
    assert rate == 0.7


def test_find_global_click_rate_not_found():
    html = '<div data-click-rate="0.7"></div>'
    rate = find_global_click_rate(html)
    assert rate is None


def test_find_global_click_rate_multiple_divs():
    html = '<div data-scope="global" data-click-rate="0.5"></div><div data-scope="global" data-click-rate="0.8"></div>'
    rate = find_global_click_rate(html)
    assert rate == 0.5  # Should use first one


def test_find_global_click_rate_invalid_value():
    html = '<div data-scope="global" data-click-rate="invalid"></div>'
    rate = find_global_click_rate(html)
    assert rate is None


def test_find_global_click_rate_out_of_range_below():
    html = '<div data-scope="global" data-click-rate="-0.5"></div>'
    rate = find_global_click_rate(html)
    assert rate == 0.0  # Should clamp to 0.0


def test_find_global_click_rate_out_of_range_above():
    html = '<div data-scope="global" data-click-rate="1.5"></div>'
    rate = find_global_click_rate(html)
    assert rate == 1.0  # Should clamp to 1.0


def test_find_global_click_rate_no_html():
    rate = find_global_click_rate("")
    assert rate is None


def test_extract_links_with_rates_no_rates():
    html = '<a href="https://example.com/page1">Link 1</a><a href="https://example.com/page2">Link 2</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 2
    assert links[0].url == "https://example.com/page1"
    assert links[0].click_rate is None
    assert links[1].url == "https://example.com/page2"
    assert links[1].click_rate is None


def test_extract_links_with_rates_with_individual_rates():
    html = '<a href="https://example.com/page1" data-click-rate="0.5">Link 1</a><a href="https://example.com/page2" data-click-rate="0.25">Link 2</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 2
    assert links[0].url == "https://example.com/page1"
    assert links[0].click_rate == 0.5
    assert links[1].url == "https://example.com/page2"
    assert links[1].click_rate == 0.25


def test_extract_links_with_rates_mixed():
    html = '<a href="https://example.com/page1" data-click-rate="0.5">Link 1</a><a href="https://example.com/page2">Link 2</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 2
    assert links[0].url == "https://example.com/page1"
    assert links[0].click_rate == 0.5
    assert links[1].url == "https://example.com/page2"
    assert links[1].click_rate is None


def test_extract_links_with_rates_dedup():
    html = '<a href="https://example.com/page1" data-click-rate="0.5">Link 1</a><a href="https://example.com/page1" data-click-rate="0.7">Link 1 again</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 1
    assert links[0].url == "https://example.com/page1"
    assert links[0].click_rate == 0.5  # Should preserve first occurrence


def test_extract_links_with_rates_invalid_rate():
    html = '<a href="https://example.com/page1" data-click-rate="invalid">Link 1</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 1
    assert links[0].url == "https://example.com/page1"
    assert links[0].click_rate is None  # Invalid rate should result in None


def test_extract_links_with_rates_out_of_range():
    html = '<a href="https://example.com/page1" data-click-rate="1.5">Link 1</a><a href="https://example.com/page2" data-click-rate="-0.5">Link 2</a>'
    links = extract_links_with_rates(html, None)
    assert len(links) == 2
    assert links[0].click_rate == 1.0  # Should clamp to 1.0
    assert links[1].click_rate == 0.0  # Should clamp to 0.0
