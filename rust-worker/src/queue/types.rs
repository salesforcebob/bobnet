//! Queue message types for the two-queue architecture.
//!
//! This module defines the message formats for:
//! - `inbound_webhooks` queue: Raw webhook payloads from web server
//! - `email_simulator` queue: Parsed jobs ready for simulation

use serde::{Deserialize, Serialize};

/// Queue name for raw inbound webhooks.
pub const INBOUND_QUEUE: &str = "inbound_webhooks";

/// Queue name for parsed email simulation jobs.
pub const SIMULATOR_QUEUE: &str = "email_simulator";

// =============================================================================
// Inbound Webhook Types (inbound_webhooks queue)
// =============================================================================

/// Raw inbound webhook payload stored in the inbound_webhooks queue.
///
/// The web server immediately enqueues raw payloads without parsing,
/// allowing it to respond in microseconds.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "provider")]
pub enum InboundWebhook {
    /// Raw Mailgun form data
    #[serde(rename = "mailgun")]
    Mailgun(MailgunRawPayload),
    /// Raw Cloudflare JSON payload
    #[serde(rename = "cloudflare")]
    Cloudflare(CloudflareRawPayload),
}

/// Raw Mailgun webhook payload (form-encoded data).
///
/// Field names match Mailgun's form field names.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MailgunRawPayload {
    /// Email recipient
    pub recipient: String,
    /// Sender email address
    #[serde(default)]
    pub sender: String,
    /// Email subject
    #[serde(default)]
    pub subject: String,
    /// HTML body content
    #[serde(default, rename = "body_html")]
    pub body_html: Option<String>,
    /// Plain text body content
    #[serde(default, rename = "body_plain")]
    pub body_plain: Option<String>,
    /// Stripped HTML content
    #[serde(default, rename = "stripped_html")]
    pub stripped_html: Option<String>,
    /// JSON-encoded message headers array
    #[serde(default, rename = "message_headers")]
    pub message_headers: Option<String>,
    /// From field (may differ from sender)
    #[serde(default, rename = "from_field")]
    pub from_field: String,
    /// Webhook timestamp (for signature verification - already verified by web server)
    #[serde(default)]
    pub timestamp: String,
    /// Webhook token (for signature verification - already verified by web server)
    #[serde(default)]
    pub token: String,
}

/// Raw Cloudflare webhook payload (JSON).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CloudflareRawPayload {
    /// Sender email address
    #[serde(rename = "from")]
    pub from_field: String,
    /// Recipient email address
    pub to: String,
    /// Email subject
    pub subject: String,
    /// Webhook timestamp
    pub timestamp: String,
    /// Raw RFC 5322 email content (headers + body)
    pub raw_content: String,
}

// =============================================================================
// Simulator Job Types (email_simulator queue)
// =============================================================================

/// Parsed job ready for email simulation.
///
/// This is the format expected by the worker's email simulator.
/// It matches the existing Python job format for compatibility.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulatorJob {
    /// Unique message identifier
    pub message_id: String,
    /// Recipient email address
    pub to: String,
    /// HTML content to simulate opens/clicks on
    pub html: Option<String>,
}

impl SimulatorJob {
    /// Create a new simulator job.
    pub fn new(message_id: String, to: String, html: Option<String>) -> Self {
        Self { message_id, to, html }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_inbound_webhook_mailgun_serialization() {
        let payload = InboundWebhook::Mailgun(MailgunRawPayload {
            recipient: "test@example.com".to_string(),
            sender: "sender@example.com".to_string(),
            subject: "Test Subject".to_string(),
            body_html: Some("<html>Test</html>".to_string()),
            body_plain: None,
            stripped_html: None,
            message_headers: Some("[[\"Message-Id\", \"<abc123>\"]]".to_string()),
            from_field: "sender@example.com".to_string(),
            timestamp: "1234567890".to_string(),
            token: "token123".to_string(),
        });

        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("\"provider\":\"mailgun\""));

        let parsed: InboundWebhook = serde_json::from_str(&json).unwrap();
        match parsed {
            InboundWebhook::Mailgun(p) => {
                assert_eq!(p.recipient, "test@example.com");
            }
            _ => panic!("Expected Mailgun variant"),
        }
    }

    #[test]
    fn test_inbound_webhook_cloudflare_serialization() {
        let payload = InboundWebhook::Cloudflare(CloudflareRawPayload {
            from_field: "sender@example.com".to_string(),
            to: "recipient@example.com".to_string(),
            subject: "Test Subject".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            raw_content: "From: sender@example.com\r\n\r\nBody".to_string(),
        });

        let json = serde_json::to_string(&payload).unwrap();
        assert!(json.contains("\"provider\":\"cloudflare\""));
    }

    #[test]
    fn test_simulator_job_serialization() {
        let job = SimulatorJob::new(
            "msg123".to_string(),
            "test@example.com".to_string(),
            Some("<html>Test</html>".to_string()),
        );

        let json = serde_json::to_string(&job).unwrap();
        let parsed: SimulatorJob = serde_json::from_str(&json).unwrap();

        assert_eq!(parsed.message_id, "msg123");
        assert_eq!(parsed.to, "test@example.com");
        assert_eq!(parsed.html, Some("<html>Test</html>".to_string()));
    }
}
