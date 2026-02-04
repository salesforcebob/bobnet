//! Click simulation - selecting and fetching links.

use crate::html::LinkWithRate;
use rand::prelude::*;
use reqwest::Client;
use std::time::Duration;
use tokio::time::sleep;
use tracing;

/// Extract domain from a URL for filtering.
fn extract_domain(url: &str) -> String {
    url.split("//")
        .nth(1)
        .and_then(|s| s.split('/').next())
        .unwrap_or(url)
        .to_lowercase()
}

/// Filter links by domain allow/deny lists and unsubscribe links.
///
/// Unsubscribe links matching `cl.S4.exct.net/unsub_center.aspx` are filtered out
/// unless they have a `data-click-rate` override (click_rate is Some).
pub fn filter_links_with_rates(
    links: &[LinkWithRate],
    allow: Option<&[String]>,
    deny: Option<&[String]>,
) -> Vec<LinkWithRate> {
    links
        .iter()
        .filter(|link| {
            let url_lower = link.url.to_lowercase();
            
            // Filter out ExactTarget unsubscribe links unless they have a click-rate override
            if url_lower.contains("cl.s4.exct.net/unsub_center.aspx") {
                // Only allow if there's an explicit data-click-rate override
                if link.click_rate.is_none() {
                    tracing::debug!(
                        url = %link.url,
                        "filtered_unsubscribe_link_no_override"
                    );
                    return false;
                }
                // If it has an override, log and allow it
                tracing::debug!(
                    url = %link.url,
                    click_rate = link.click_rate,
                    "allowing_unsubscribe_link_with_override"
                );
            }

            let host = extract_domain(&link.url);

            // Check deny list first
            if let Some(deny_list) = deny {
                if deny_list.iter().any(|d| host.contains(&d.to_lowercase())) {
                    return false;
                }
            }

            // Check allow list
            if let Some(allow_list) = allow {
                if !allow_list.iter().any(|a| host.contains(&a.to_lowercase())) {
                    return false;
                }
            }

            true
        })
        .cloned()
        .collect()
}

/// Choose links using weighted random selection based on click rates.
///
/// Each link's effective click rate is either its individual data-click-rate
/// or the global_rate if not specified. Links with higher rates are selected
/// more frequently.
pub fn choose_links_weighted(
    links: &[LinkWithRate],
    max_clicks: usize,
    global_rate: f64,
) -> Vec<String> {
    if max_clicks == 0 || links.is_empty() {
        return Vec::new();
    }

    // Calculate effective rates (weights) for each link
    let weights: Vec<f64> = links
        .iter()
        .map(|link| link.click_rate.unwrap_or(global_rate))
        .collect();

    // Check if all weights are zero
    if weights.iter().all(|&w| w == 0.0) {
        tracing::warn!(
            total_links = links.len(),
            "choose_links_weighted_all_zero_weights"
        );
        return Vec::new();
    }

    let mut rng = thread_rng();
    let mut chosen = Vec::with_capacity(max_clicks);

    // Use weighted random selection
    for _ in 0..max_clicks {
        let total_weight: f64 = weights.iter().sum();
        if total_weight <= 0.0 {
            break;
        }

        let mut target = rng.gen::<f64>() * total_weight;
        
        for (i, &weight) in weights.iter().enumerate() {
            target -= weight;
            if target <= 0.0 {
                chosen.push(links[i].url.clone());
                break;
            }
        }
    }

    tracing::info!(
        total_links = links.len(),
        max_clicks = max_clicks,
        chosen_count = chosen.len(),
        chosen_urls = ?chosen.iter().map(|u| &u[..u.len().min(80)]).collect::<Vec<_>>(),
        "choose_links_weighted_complete"
    );

    chosen
}

/// Perform clicks on selected links.
///
/// Fetches each link with a random delay between clicks.
/// Returns the number of successful clicks.
pub async fn perform_clicks(
    client: &Client,
    links: &[String],
    headers: &[(String, String)],
    timeout: Duration,
    delay_range_ms: (u64, u64),
) -> usize {
    if links.is_empty() {
        return 0;
    }

    // Pre-compute all delays upfront (ThreadRng is not Send)
    let delays: Vec<u64> = {
        let mut rng = thread_rng();
        links
            .iter()
            .map(|_| rng.gen_range(delay_range_ms.0..=delay_range_ms.1))
            .collect()
    };

    let mut clicks = 0;

    for (link, &delay_ms) in links.iter().zip(delays.iter()) {
        // Random delay before click
        sleep(Duration::from_millis(delay_ms)).await;

        let mut request = client.get(link).timeout(timeout);
        
        for (key, value) in headers {
            request = request.header(key.as_str(), value.as_str());
        }

        match request.send().await {
            Ok(resp) => {
                let status = resp.status().as_u16();
                tracing::info!(
                    url = link,
                    status_code = status,
                    "click_fetch"
                );
                if (200..400).contains(&status) {
                    clicks += 1;
                }
            }
            Err(e) => {
                tracing::warn!(
                    url = link,
                    error = %e,
                    "click_fetch_error"
                );
            }
        }
    }

    clicks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_domain() {
        assert_eq!(extract_domain("https://example.com/path"), "example.com");
        assert_eq!(extract_domain("http://sub.example.com/"), "sub.example.com");
        assert_eq!(extract_domain("invalid"), "invalid");
    }

    #[test]
    fn test_filter_links_no_filters() {
        let links = vec![
            LinkWithRate::new("https://example.com".to_string(), None),
            LinkWithRate::new("https://other.com".to_string(), Some(0.5)),
        ];

        let filtered = filter_links_with_rates(&links, None, None);
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_filter_links_allow_list() {
        let links = vec![
            LinkWithRate::new("https://allowed.com/page".to_string(), None),
            LinkWithRate::new("https://blocked.com/page".to_string(), None),
        ];

        let allow = vec!["allowed.com".to_string()];
        let filtered = filter_links_with_rates(&links, Some(&allow), None);
        
        assert_eq!(filtered.len(), 1);
        assert!(filtered[0].url.contains("allowed.com"));
    }

    #[test]
    fn test_filter_links_deny_list() {
        let links = vec![
            LinkWithRate::new("https://allowed.com/page".to_string(), None),
            LinkWithRate::new("https://blocked.com/page".to_string(), None),
        ];

        let deny = vec!["blocked.com".to_string()];
        let filtered = filter_links_with_rates(&links, None, Some(&deny));
        
        assert_eq!(filtered.len(), 1);
        assert!(filtered[0].url.contains("allowed.com"));
    }

    #[test]
    fn test_filter_unsubscribe_link_no_override() {
        let links = vec![
            LinkWithRate::new("https://example.com/page".to_string(), None),
            LinkWithRate::new("https://cl.S4.exct.net/unsub_center.aspx?email=test@example.com".to_string(), None),
            LinkWithRate::new("https://CL.S4.EXCT.NET/unsub_center.aspx".to_string(), None),
        ];

        let filtered = filter_links_with_rates(&links, None, None);
        
        // Should filter out unsubscribe links without override
        assert_eq!(filtered.len(), 1);
        assert!(filtered[0].url.contains("example.com"));
    }

    #[test]
    fn test_filter_unsubscribe_link_with_override() {
        let links = vec![
            LinkWithRate::new("https://example.com/page".to_string(), None),
            LinkWithRate::new("https://cl.S4.exct.net/unsub_center.aspx?email=test@example.com".to_string(), Some(0.5)),
        ];

        let filtered = filter_links_with_rates(&links, None, None);
        
        // Should keep unsubscribe link with override
        assert_eq!(filtered.len(), 2);
        assert!(filtered.iter().any(|l| l.url.contains("unsub_center")));
    }

    #[test]
    fn test_choose_links_weighted_empty() {
        let links: Vec<LinkWithRate> = vec![];
        let chosen = choose_links_weighted(&links, 5, 0.5);
        assert!(chosen.is_empty());
    }

    #[test]
    fn test_choose_links_weighted_zero_max() {
        let links = vec![LinkWithRate::new("https://example.com".to_string(), None)];
        let chosen = choose_links_weighted(&links, 0, 0.5);
        assert!(chosen.is_empty());
    }

    #[test]
    fn test_choose_links_weighted_all_zero_weights() {
        let links = vec![
            LinkWithRate::new("https://example.com".to_string(), Some(0.0)),
            LinkWithRate::new("https://other.com".to_string(), Some(0.0)),
        ];
        let chosen = choose_links_weighted(&links, 5, 0.0);
        assert!(chosen.is_empty());
    }

    #[test]
    fn test_choose_links_weighted_returns_links() {
        let links = vec![
            LinkWithRate::new("https://high.com".to_string(), Some(0.9)),
            LinkWithRate::new("https://low.com".to_string(), Some(0.1)),
        ];
        
        // Run multiple times to verify weighted selection works
        let mut high_count = 0;
        for _ in 0..100 {
            let chosen = choose_links_weighted(&links, 1, 0.5);
            if !chosen.is_empty() && chosen[0].contains("high.com") {
                high_count += 1;
            }
        }
        
        // High-weighted link should be chosen more often
        assert!(high_count > 50, "High-weighted link should be chosen more than 50% of the time, got {}", high_count);
    }
}
