//! Configuration module for environment variable parsing.
//!
//! Reads all configuration from environment variables, matching the Python implementation.

use std::env;
use tracing::warn;

/// Application configuration loaded from environment variables.
#[derive(Debug, Clone)]
pub struct Config {
    /// RabbitMQ connection URL (CloudAMQP)
    pub cloudamqp_url: String,

    /// Probability of simulating an email open (0.0 - 1.0)
    pub simulate_open_probability: f64,

    /// Probability of simulating a click (0.0 - 1.0)
    pub simulate_click_probability: f64,

    /// Maximum number of links to click per email
    pub max_clicks: usize,

    /// Delay range in milliseconds before opening (min, max)
    pub open_delay_ms: (u64, u64),

    /// Delay range in milliseconds between clicks (min, max)
    pub click_delay_ms: (u64, u64),

    /// HTTP request timeout in milliseconds
    pub request_timeout_ms: u64,

    /// Optional list of allowed domains for clicking
    pub allow_domains: Option<Vec<String>>,

    /// Optional list of denied domains for clicking
    pub deny_domains: Option<Vec<String>>,

    /// Optional pool of user agents to rotate through
    pub user_agent_pool: Option<Vec<String>>,

    /// Maximum number of concurrent jobs to process
    pub worker_concurrency: usize,

    // =========================================================================
    // Web Server Configuration (NEW)
    // =========================================================================

    /// Port for the web server to listen on
    pub port: u16,

    /// Cloudflare authentication token for webhook verification
    pub cloudflare_auth_token: Option<String>,

    /// Mailgun signing key for HMAC signature verification
    pub mailgun_signing_key: Option<String>,

    /// Mailgun domain for recipient validation
    pub mailgun_domain: Option<String>,

    /// Maximum age in seconds for Mailgun webhook timestamps
    pub mailgun_signature_max_age: u64,
}

impl Config {
    /// Load configuration from environment variables.
    pub fn from_env() -> Self {
        Config {
            cloudamqp_url: env::var("CLOUDAMQP_URL")
                .unwrap_or_else(|_| "amqp://guest:guest@localhost:5672/".to_string()),

            simulate_open_probability: env::var("SIMULATE_OPEN_PROBABILITY")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(0.7),

            simulate_click_probability: env::var("SIMULATE_CLICK_PROBABILITY")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(0.3),

            max_clicks: env::var("MAX_CLICKS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(2),

            open_delay_ms: parse_range("OPEN_DELAY_RANGE_MS", (500, 5000)),

            click_delay_ms: parse_range("CLICK_DELAY_RANGE_MS", (300, 4000)),

            request_timeout_ms: env::var("REQUEST_TIMEOUT_MS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(8000),

            allow_domains: parse_csv("LINK_DOMAIN_ALLOWLIST"),

            deny_domains: parse_csv("LINK_DOMAIN_DENYLIST"),

            user_agent_pool: parse_csv("USER_AGENT_POOL"),

            worker_concurrency: env::var("WORKER_CONCURRENCY")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(100),

            // Web server configuration
            port: env::var("PORT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(8080),

            cloudflare_auth_token: env::var("CLOUDFLARE_AUTH_TOKEN").ok(),

            mailgun_signing_key: env::var("MAILGUN_SIGNING_KEY").ok(),

            mailgun_domain: env::var("MAILGUN_DOMAIN").ok(),

            mailgun_signature_max_age: env::var("MAILGUN_SIGNATURE_MAX_AGE")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(300), // 5 minutes default
        }
    }
}

/// Parse a comma-separated range like "500,5000" into a tuple.
fn parse_range(name: &str, default: (u64, u64)) -> (u64, u64) {
    let raw = match env::var(name) {
        Ok(v) => v,
        Err(_) => return default,
    };

    let parts: Vec<&str> = raw.split(',').collect();
    if parts.len() != 2 {
        warn!(env_var = name, value = %raw, "Invalid range format, using default");
        return default;
    }

    let min = parts[0].trim().parse::<u64>();
    let max = parts[1].trim().parse::<u64>();

    match (min, max) {
        (Ok(min), Ok(max)) if min <= max => (min, max),
        _ => {
            warn!(env_var = name, value = %raw, "Invalid range values, using default");
            default
        }
    }
}

/// Parse a comma-separated list of strings.
fn parse_csv(name: &str) -> Option<Vec<String>> {
    env::var(name).ok().map(|raw| {
        raw.split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_range_valid() {
        env::set_var("TEST_RANGE", "100,500");
        let result = parse_range("TEST_RANGE", (0, 0));
        assert_eq!(result, (100, 500));
        env::remove_var("TEST_RANGE");
    }

    #[test]
    fn test_parse_range_default() {
        let result = parse_range("NONEXISTENT_VAR", (10, 20));
        assert_eq!(result, (10, 20));
    }

    #[test]
    fn test_parse_csv() {
        env::set_var("TEST_CSV", "foo, bar, baz");
        let result = parse_csv("TEST_CSV");
        assert_eq!(result, Some(vec!["foo".to_string(), "bar".to_string(), "baz".to_string()]));
        env::remove_var("TEST_CSV");
    }
}
