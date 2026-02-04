//! Job processing module - core email simulation logic.
//!
//! This module contains the main processing logic that simulates email opens
//! and clicks based on configurable probabilities.

use std::time::Duration;

use rand::Rng;
use reqwest::Client;
use serde::Deserialize;
use tokio::time::sleep;
use tracing::info;

use crate::config::Config;
use crate::html::{
    extract_image_sources, extract_links_with_rates, find_exacttarget_open_pixel,
    find_global_click_rate,
};
use crate::simulate::clicker::{choose_links_weighted, filter_links_with_rates, perform_clicks};
use crate::simulate::opener::{fetch_single_url, simulate_open};
use crate::util::user_agent::{build_headers, pick_user_agent};

/// Job payload received from the RabbitMQ queue.
#[derive(Debug, Deserialize)]
pub struct Job {
    /// Unique message identifier
    pub message_id: Option<String>,
    /// Recipient email address (may contain plus addressing)
    pub to: String,
    /// HTML content of the email
    pub html: Option<String>,
}

/// Result of processing a job.
#[derive(Debug)]
pub struct ProcessResult {
    /// Message ID from the job
    pub message_id: String,
    /// Recipient email address
    pub to: String,
    /// Customer tag extracted from plus addressing (e.g., "tag" from "user+tag@example.com")
    pub customer_tag: Option<String>,
    /// Whether the email open was simulated successfully
    pub opened: bool,
    /// Number of successful link clicks
    pub clicks: usize,
}

/// Extract plus tag from an email address.
///
/// For "user+tag@example.com", returns Some("tag").
/// For "user@example.com", returns None.
fn extract_plus_tag(email: &str) -> Option<String> {
    let local = email.split('@').next()?;
    if local.contains('+') {
        local.split_once('+').map(|(_, tag)| tag.to_string())
    } else {
        None
    }
}

/// Process a single email simulation job.
///
/// This function:
/// 1. Extracts the plus tag from the recipient address
/// 2. Applies a random delay before opening
/// 3. With configured probability, simulates email open by fetching tracking pixels
/// 4. With configured probability, simulates link clicks using weighted selection
///
/// # Arguments
///
/// * `client` - Shared HTTP client for making requests
/// * `config` - Application configuration
/// * `job` - The job to process
///
/// # Returns
///
/// A `ProcessResult` containing the outcome of the simulation.
pub async fn process_job(client: &Client, config: &Config, job: &Job) -> ProcessResult {
    let message_id = job.message_id.clone().unwrap_or_else(|| "unknown".to_string());
    let html = job.html.as_deref().unwrap_or("");
    let html_length = html.len();

    info!(
        message_id = %message_id,
        to = %job.to,
        html_length = html_length,
        html_is_empty = html.is_empty(),
        "worker_job_received"
    );

    // Extract customer tag from plus addressing
    let customer_tag = extract_plus_tag(&job.to);

    // Pick a random user agent and build headers
    let user_agent = pick_user_agent(config.user_agent_pool.as_deref());
    let headers = build_headers(&user_agent);
    let timeout = Duration::from_millis(config.request_timeout_ms);

    // Generate all random values upfront (ThreadRng is not Send)
    let (delay_ms, open_roll, click_roll) = {
        let mut rng = rand::thread_rng();
        let delay = rng.gen_range(config.open_delay_ms.0..=config.open_delay_ms.1);
        let open: f64 = rng.gen();
        let click: f64 = rng.gen();
        (delay, open, click)
    };

    // Random delay before potential open
    info!(
        message_id = %message_id,
        delay_ms = delay_ms,
        "worker_delay_start"
    );
    sleep(Duration::from_millis(delay_ms)).await;

    // Simulate open with probability check
    let mut opened = false;
    let will_attempt_open = open_roll < config.simulate_open_probability;

    info!(
        message_id = %message_id,
        roll = open_roll,
        threshold = config.simulate_open_probability,
        will_attempt_open = will_attempt_open,
        "worker_open_roll"
    );

    if will_attempt_open {
        // Look for ExactTarget/SFMC open pixel first
        let special_pixel = find_exacttarget_open_pixel(html);
        let mut images = extract_image_sources(html);

        info!(
            message_id = %message_id,
            special_pixel_found = special_pixel.is_some(),
            total_images_found = images.len(),
            "worker_open_analysis"
        );

        // Fetch special pixel if found
        if let Some(ref pixel_url) = special_pixel {
            info!(
                message_id = %message_id,
                url = %pixel_url,
                "worker_pixel_fetch_starting"
            );

            let pixel_result = fetch_single_url(client, pixel_url, &headers, timeout).await;

            info!(
                message_id = %message_id,
                success = pixel_result,
                "worker_pixel_fetch"
            );

            if pixel_result {
                opened = true;
            }

            // Remove special pixel from regular images list
            images.retain(|u| u != pixel_url);
        }

        // Simulate open via regular images
        let open_result = simulate_open(client, &images, &headers, timeout).await;
        opened = open_result || opened;

        let opened_source = if special_pixel.is_some() && opened {
            "special_pixel"
        } else if open_result {
            "regular_images"
        } else {
            "none"
        };

        info!(
            message_id = %message_id,
            opened = opened,
            opened_source = opened_source,
            "worker_open_final_status"
        );
    } else {
        info!(
            message_id = %message_id,
            reason = "probability_check_failed",
            "worker_open_skipped"
        );
    }

    // Simulate clicks with probability check
    let mut clicks = 0;

    // Check for global click rate override in HTML
    let global_click_rate = find_global_click_rate(html);
    let effective_click_probability = global_click_rate.unwrap_or(config.simulate_click_probability);

    info!(
        message_id = %message_id,
        global_override_found = global_click_rate.is_some(),
        global_override_value = ?global_click_rate,
        effective_probability = effective_click_probability,
        "worker_click_rate_determined"
    );

    let will_attempt_click = click_roll < effective_click_probability;

    info!(
        message_id = %message_id,
        roll = click_roll,
        threshold = effective_click_probability,
        will_attempt_click = will_attempt_click,
        "worker_click_roll"
    );

    if will_attempt_click {
        // Extract links with their individual click rates
        let links_with_rates = extract_links_with_rates(html, global_click_rate);

        // Filter by domain allow/deny lists
        let filtered_links = filter_links_with_rates(
            &links_with_rates,
            config.allow_domains.as_deref(),
            config.deny_domains.as_deref(),
        );

        // Choose links using weighted selection
        let chosen = choose_links_weighted(
            &filtered_links,
            config.max_clicks,
            effective_click_probability,
        );

        info!(
            message_id = %message_id,
            total_links_found = links_with_rates.len(),
            links_after_filter = filtered_links.len(),
            links_chosen = chosen.len(),
            "worker_click_analysis"
        );

        if !chosen.is_empty() {
            clicks = perform_clicks(
                client,
                &chosen,
                &headers,
                timeout,
                config.click_delay_ms,
            )
            .await;
        }
    }

    let result = ProcessResult {
        message_id: message_id.clone(),
        to: job.to.clone(),
        customer_tag,
        opened,
        clicks,
    };

    info!(
        message_id = %result.message_id,
        to = %result.to,
        customer_tag = ?result.customer_tag,
        opened = result.opened,
        clicks = result.clicks,
        "email_simulation_complete"
    );

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_plus_tag() {
        assert_eq!(
            extract_plus_tag("user+tag@example.com"),
            Some("tag".to_string())
        );
        assert_eq!(
            extract_plus_tag("user+customer123@example.com"),
            Some("customer123".to_string())
        );
        assert_eq!(extract_plus_tag("user@example.com"), None);
        assert_eq!(extract_plus_tag("user"), None);
    }

    #[test]
    fn test_job_deserialization() {
        let json = r#"{
            "message_id": "msg-123",
            "to": "test+tag@example.com",
            "html": "<html><body>Test</body></html>"
        }"#;

        let job: Job = serde_json::from_str(json).unwrap();
        assert_eq!(job.message_id, Some("msg-123".to_string()));
        assert_eq!(job.to, "test+tag@example.com");
        assert!(job.html.is_some());
    }

    #[test]
    fn test_job_deserialization_minimal() {
        let json = r#"{"to": "test@example.com"}"#;

        let job: Job = serde_json::from_str(json).unwrap();
        assert_eq!(job.message_id, None);
        assert_eq!(job.to, "test@example.com");
        assert_eq!(job.html, None);
    }
}
