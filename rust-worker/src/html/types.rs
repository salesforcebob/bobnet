//! Type definitions for HTML parsing.

/// Represents a link URL with an optional per-link click rate.
#[derive(Debug, Clone, PartialEq)]
pub struct LinkWithRate {
    /// The URL of the link
    pub url: String,
    /// Optional click rate override (0.0 - 1.0). None means use global rate.
    pub click_rate: Option<f64>,
}

impl LinkWithRate {
    /// Create a new LinkWithRate with an optional click rate.
    pub fn new(url: String, click_rate: Option<f64>) -> Self {
        Self { url, click_rate }
    }

    /// Create a new LinkWithRate with an individual click rate.
    pub fn with_rate(url: String, rate: f64) -> Self {
        Self {
            url,
            click_rate: Some(rate),
        }
    }
}
