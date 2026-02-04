//! Open simulation - fetching tracking pixels and images.

use reqwest::Client;
use std::time::Duration;
use tracing;

/// Fetch a single URL and return whether it succeeded.
pub async fn fetch_single_url(
    client: &Client,
    url: &str,
    headers: &[(String, String)],
    timeout: Duration,
) -> bool {
    tracing::info!(
        url = url,
        url_length = url.len(),
        timeout_seconds = timeout.as_secs_f64(),
        "open_pixel_fetch_starting"
    );

    let mut request = client.get(url).timeout(timeout);
    
    for (key, value) in headers {
        request = request.header(key.as_str(), value.as_str());
    }

    match request.send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let is_success = (200..400).contains(&status);

            tracing::info!(
                url = url,
                status_code = status,
                is_success = is_success,
                "open_pixel_fetch_complete"
            );

            is_success
        }
        Err(e) => {
            if e.is_timeout() {
                tracing::error!(
                    url = url,
                    timeout_seconds = timeout.as_secs_f64(),
                    error = %e,
                    "open_pixel_fetch_timeout"
                );
            } else if e.is_request() {
                tracing::error!(
                    url = url,
                    error = %e,
                    "open_pixel_fetch_request_error"
                );
            } else {
                tracing::error!(
                    url = url,
                    error = %e,
                    "open_pixel_fetch_error"
                );
            }
            false
        }
    }
}

/// Simulate opening an email by fetching tracking images.
///
/// Fetches up to 5 images concurrently and returns true if any succeeded.
pub async fn simulate_open(
    client: &Client,
    image_urls: &[String],
    headers: &[(String, String)],
    timeout: Duration,
) -> bool {
    if image_urls.is_empty() {
        return false;
    }

    // Cap to 5 images to avoid flooding
    let urls_to_fetch: Vec<_> = image_urls.iter().take(5).collect();

    // Fetch all images concurrently
    let futures: Vec<_> = urls_to_fetch
        .iter()
        .map(|url| fetch_single_url(client, url, headers, timeout))
        .collect();

    let results = futures::future::join_all(futures).await;

    let successful = results.iter().filter(|&&r| r).count();
    let any_success = successful > 0;

    tracing::info!(
        images_fetched = urls_to_fetch.len(),
        successful_fetches = successful,
        open_result = any_success,
        "simulate_open_complete"
    );

    any_success
}
