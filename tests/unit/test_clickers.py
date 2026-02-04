from app.simulate.clickers import (
    choose_links_weighted,
    filter_links_with_rates,
    LinkWithRate,
)


def test_filter_links_with_rates_no_filters():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
        LinkWithRate(url="https://test.com/page2", click_rate=None),
    ]
    filtered = filter_links_with_rates(links, None, None)
    assert len(filtered) == 2
    assert filtered == links


def test_filter_links_with_rates_allow_domain():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
        LinkWithRate(url="https://test.com/page2", click_rate=None),
    ]
    filtered = filter_links_with_rates(links, ["example.com"], None)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/page1"


def test_filter_links_with_rates_deny_domain():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
        LinkWithRate(url="https://test.com/page2", click_rate=None),
    ]
    filtered = filter_links_with_rates(links, None, ["example.com"])
    assert len(filtered) == 1
    assert filtered[0].url == "https://test.com/page2"


def test_choose_links_weighted_empty_list():
    chosen = choose_links_weighted([], 5, 0.3)
    assert chosen == []


def test_choose_links_weighted_zero_max_clicks():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
    ]
    chosen = choose_links_weighted(links, 0, 0.3)
    assert chosen == []


def test_choose_links_weighted_single_link():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
    ]
    chosen = choose_links_weighted(links, 3, 0.3)
    assert len(chosen) == 3
    assert all(url == "https://example.com/page1" for url in chosen)


def test_choose_links_weighted_uses_global_rate():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=None),
        LinkWithRate(url="https://example.com/page2", click_rate=None),
    ]
    chosen = choose_links_weighted(links, 10, 0.5)
    assert len(chosen) == 10
    # Both links should be selected with equal probability (both use global rate 0.5)
    assert all(url.startswith("https://example.com/") for url in chosen)


def test_choose_links_weighted_uses_individual_rates():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.8),
        LinkWithRate(url="https://example.com/page2", click_rate=0.2),
    ]
    chosen = choose_links_weighted(links, 100, 0.5)
    assert len(chosen) == 100
    # Link 1 should be selected more often than Link 2 (0.8 vs 0.2)
    link1_count = sum(1 for url in chosen if url == "https://example.com/page1")
    link2_count = sum(1 for url in chosen if url == "https://example.com/page2")
    assert link1_count > link2_count  # Should be approximately 4x more, but allow variance


def test_choose_links_weighted_mixed_rates():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.5),
        LinkWithRate(url="https://example.com/page2", click_rate=None),
    ]
    chosen = choose_links_weighted(links, 10, 0.3)
    assert len(chosen) == 10
    # Link 1 uses 0.5, Link 2 uses 0.3 (global)
    link1_count = sum(1 for url in chosen if url == "https://example.com/page1")
    link2_count = sum(1 for url in chosen if url == "https://example.com/page2")
    assert link1_count > link2_count  # Link 1 should be selected more often


def test_choose_links_weighted_all_zero_rates():
    links = [
        LinkWithRate(url="https://example.com/page1", click_rate=0.0),
        LinkWithRate(url="https://example.com/page2", click_rate=0.0),
    ]
    chosen = choose_links_weighted(links, 10, 0.0)
    assert chosen == []  # All weights are zero, should return empty list
