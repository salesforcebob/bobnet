//! HTML parsing utilities for extracting images, links, and click rates.

use scraper::{Html, Selector};
use tracing::{debug, info, warn};

use super::types::LinkWithRate;

/// Extract all image source URLs from HTML.
pub fn extract_image_sources(html: &str) -> Vec<String> {
    let document = Html::parse_document(html);
    let selector = Selector::parse("img[src]").expect("Invalid selector");

    let urls: Vec<String> = document
        .select(&selector)
        .filter_map(|img| img.value().attr("src"))
        .filter(|src| src.starts_with("http://") || src.starts_with("https://"))
        .map(|s| s.to_string())
        .collect();

    debug!(count = urls.len(), "Extracted image sources");
    urls
}

/// Extract all link URLs from HTML (deduplicated).
#[allow(dead_code)] // Used in tests
pub fn extract_links(html: &str) -> Vec<String> {
    let document = Html::parse_document(html);
    let selector = Selector::parse("a[href]").expect("Invalid selector");

    let mut seen = std::collections::HashSet::new();
    let mut urls = Vec::new();

    for a in document.select(&selector) {
        if let Some(href) = a.value().attr("href") {
            if (href.starts_with("http://") || href.starts_with("https://")) && seen.insert(href.to_string()) {
                urls.push(href.to_string());
            }
        }
    }

    debug!(count = urls.len(), "Extracted links");
    urls
}

/// Find Salesforce Marketing Cloud open pixel URL if present.
///
/// Searches for an `<img>` whose src matches SFMC open pixel patterns:
/// - ExactTarget/SFMC Classic: `://cl.s4.exct.net/open.aspx`
/// - SFMC Advanced: `tracking.e360.salesforce.com/open`
pub fn find_sfmc_open_pixel(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    let selector = Selector::parse("img[src]").expect("Invalid selector");

    let all_imgs: Vec<_> = document.select(&selector).collect();
    
    info!(
        total_img_tags = all_imgs.len(),
        html_length = html.len(),
        "Searching for SFMC open pixel"
    );

    for (idx, img) in all_imgs.iter().enumerate() {
        if let Some(src) = img.value().attr("src") {
            let low = src.to_lowercase();
            let matches = low.contains("://cl.s4.exct.net/open.aspx")
                || low.contains("tracking.e360.salesforce.com/open");

            debug!(
                img_index = idx,
                src_length = src.len(),
                matches_pattern = matches,
                "Checking image for SFMC open pixel"
            );

            if matches {
                info!(img_index = idx, url = src, "Found SFMC open pixel");
                return Some(src.to_string());
            }
        }
    }

    info!(total_imgs_checked = all_imgs.len(), "SFMC open pixel not found");
    None
}

/// Find global open rate override from HTML.
///
/// Searches for `<div data-scope="global" data-open-rate="...">` and returns
/// the parsed float value (0.0-1.0).
pub fn find_global_open_rate(html: &str) -> Option<f64> {
    let document = Html::parse_document(html);
    let selector = Selector::parse(r#"div[data-scope="global"]"#).expect("Invalid selector");

    let global_divs: Vec<_> = document.select(&selector).collect();

    info!(
        total_divs_with_scope_global = global_divs.len(),
        html_length = html.len(),
        "Searching for global open rate"
    );

    for (idx, div) in global_divs.iter().enumerate() {
        if let Some(rate_attr) = div.value().attr("data-open-rate") {
            match rate_attr.parse::<f64>() {
                Ok(rate) => {
                    let clamped = rate.clamp(0.0, 1.0);
                    
                    if rate < 0.0 {
                        warn!(div_index = idx, value = rate, clamped_to = 0.0, "Global open rate below zero");
                    } else if rate > 1.0 {
                        warn!(div_index = idx, value = rate, clamped_to = 1.0, "Global open rate above one");
                    }

                    if idx > 0 {
                        warn!(
                            using_first = true,
                            total_found = global_divs.len(),
                            "Multiple global open rate divs found"
                        );
                    }

                    info!(div_index = idx, value = clamped, raw_attribute = rate_attr, "Found global open rate");
                    return Some(clamped);
                }
                Err(e) => {
                    warn!(
                        div_index = idx,
                        raw_attribute = rate_attr,
                        error = %e,
                        "Invalid global open rate value"
                    );
                }
            }
        }
    }

    info!(total_divs_checked = global_divs.len(), "Global open rate not found");
    None
}

/// Find global click rate override from HTML.
///
/// Searches for `<div data-scope="global" data-click-rate="...">` and returns
/// the parsed float value (0.0-1.0).
pub fn find_global_click_rate(html: &str) -> Option<f64> {
    let document = Html::parse_document(html);
    let selector = Selector::parse(r#"div[data-scope="global"]"#).expect("Invalid selector");

    let global_divs: Vec<_> = document.select(&selector).collect();

    info!(
        total_divs_with_scope_global = global_divs.len(),
        html_length = html.len(),
        "Searching for global click rate"
    );

    for (idx, div) in global_divs.iter().enumerate() {
        if let Some(rate_attr) = div.value().attr("data-click-rate") {
            match rate_attr.parse::<f64>() {
                Ok(rate) => {
                    let clamped = rate.clamp(0.0, 1.0);
                    
                    if rate < 0.0 {
                        warn!(div_index = idx, value = rate, clamped_to = 0.0, "Global click rate below zero");
                    } else if rate > 1.0 {
                        warn!(div_index = idx, value = rate, clamped_to = 1.0, "Global click rate above one");
                    }

                    if idx > 0 {
                        warn!(
                            using_first = true,
                            total_found = global_divs.len(),
                            "Multiple global click rate divs found"
                        );
                    }

                    info!(div_index = idx, value = clamped, raw_attribute = rate_attr, "Found global click rate");
                    return Some(clamped);
                }
                Err(e) => {
                    warn!(
                        div_index = idx,
                        raw_attribute = rate_attr,
                        error = %e,
                        "Invalid global click rate value"
                    );
                }
            }
        }
    }

    info!(total_divs_checked = global_divs.len(), "Global click rate not found");
    None
}

/// Extract links with their individual click rates.
///
/// Finds all `<a>` tags with http/https URLs and extracts their `data-click-rate`
/// attributes if present.
pub fn extract_links_with_rates(html: &str, global_rate: Option<f64>) -> Vec<LinkWithRate> {
    let document = Html::parse_document(html);
    let selector = Selector::parse("a[href]").expect("Invalid selector");

    let mut seen = std::collections::HashSet::new();
    let mut links = Vec::new();

    for a in document.select(&selector) {
        let href = match a.value().attr("href") {
            Some(h) if h.starts_with("http://") || h.starts_with("https://") => h,
            _ => continue,
        };

        // Deduplicate
        if !seen.insert(href.to_string()) {
            continue;
        }

        let click_rate = a.value().attr("data-click-rate").and_then(|attr| {
            match attr.parse::<f64>() {
                Ok(rate) => {
                    let clamped = rate.clamp(0.0, 1.0);
                    if rate < 0.0 {
                        warn!(url = &href[..href.len().min(100)], value = rate, clamped_to = 0.0, "Link click rate below zero");
                    } else if rate > 1.0 {
                        warn!(url = &href[..href.len().min(100)], value = rate, clamped_to = 1.0, "Link click rate above one");
                    }
                    Some(clamped)
                }
                Err(e) => {
                    warn!(
                        url = &href[..href.len().min(100)],
                        raw_attribute = attr,
                        error = %e,
                        "Invalid link click rate value"
                    );
                    None
                }
            }
        });

        links.push(LinkWithRate {
            url: href.to_string(),
            click_rate,
        });
    }

    let with_rates = links.iter().filter(|l| l.click_rate.is_some()).count();
    let using_global = links.iter().filter(|l| l.click_rate.is_none()).count();

    info!(
        total_links_found = links.len(),
        links_with_individual_rates = with_rates,
        links_using_global_rate = using_global,
        global_rate = ?global_rate,
        "Extracted links with rates"
    );

    links
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_image_sources() {
        let html = r#"
            <html>
                <img src="https://example.com/img1.png">
                <img src="http://example.com/img2.jpg">
                <img src="/relative/path.png">
                <img>
            </html>
        "#;

        let images = extract_image_sources(html);
        assert_eq!(images.len(), 2);
        assert!(images.contains(&"https://example.com/img1.png".to_string()));
        assert!(images.contains(&"http://example.com/img2.jpg".to_string()));
    }

    #[test]
    fn test_extract_links_deduplicates() {
        let html = r#"
            <html>
                <a href="https://example.com/page1">Link 1</a>
                <a href="https://example.com/page1">Link 1 again</a>
                <a href="https://example.com/page2">Link 2</a>
            </html>
        "#;

        let links = extract_links(html);
        assert_eq!(links.len(), 2);
    }

    #[test]
    fn test_find_sfmc_classic_open_pixel() {
        let html = r#"
            <html>
                <img src="https://example.com/logo.png">
                <img src="https://cl.s4.exct.net/open.aspx?ffcb10-fe">
                <img src="https://other.com/pixel.gif">
            </html>
        "#;

        let pixel = find_sfmc_open_pixel(html);
        assert!(pixel.is_some());
        assert!(pixel.unwrap().contains("cl.s4.exct.net/open.aspx"));
    }

    #[test]
    fn test_find_sfmc_advanced_open_pixel() {
        let html = r#"
            <html>
                <img src="https://example.com/logo.png">
                <img src="https://tracking.e360.salesforce.com/open?id=abc123&subscriber=test">
                <img src="https://other.com/pixel.gif">
            </html>
        "#;

        let pixel = find_sfmc_open_pixel(html);
        assert!(pixel.is_some());
        assert!(pixel.unwrap().contains("tracking.e360.salesforce.com/open"));
    }

    #[test]
    fn test_find_sfmc_open_pixel_not_found() {
        let html = r#"
            <html>
                <img src="https://example.com/logo.png">
            </html>
        "#;

        let pixel = find_sfmc_open_pixel(html);
        assert!(pixel.is_none());
    }

    #[test]
    fn test_find_global_open_rate() {
        let html = r#"
            <html>
                <div data-scope="global" data-open-rate="0.85"></div>
            </html>
        "#;

        let rate = find_global_open_rate(html);
        assert_eq!(rate, Some(0.85));
    }

    #[test]
    fn test_find_global_open_rate_clamped() {
        let html = r#"
            <html>
                <div data-scope="global" data-open-rate="1.5"></div>
            </html>
        "#;

        let rate = find_global_open_rate(html);
        assert_eq!(rate, Some(1.0));
    }

    #[test]
    fn test_find_global_click_rate() {
        let html = r#"
            <html>
                <div data-scope="global" data-click-rate="0.75"></div>
            </html>
        "#;

        let rate = find_global_click_rate(html);
        assert_eq!(rate, Some(0.75));
    }

    #[test]
    fn test_find_global_click_rate_clamped() {
        let html = r#"
            <html>
                <div data-scope="global" data-click-rate="1.5"></div>
            </html>
        "#;

        let rate = find_global_click_rate(html);
        assert_eq!(rate, Some(1.0));
    }

    #[test]
    fn test_extract_links_with_rates() {
        let html = r#"
            <html>
                <a href="https://example.com/page1" data-click-rate="0.8">High rate</a>
                <a href="https://example.com/page2" data-click-rate="0.2">Low rate</a>
                <a href="https://example.com/page3">No rate</a>
            </html>
        "#;

        let links = extract_links_with_rates(html, Some(0.5));
        assert_eq!(links.len(), 3);
        assert_eq!(links[0].click_rate, Some(0.8));
        assert_eq!(links[1].click_rate, Some(0.2));
        assert_eq!(links[2].click_rate, None);
    }
}
