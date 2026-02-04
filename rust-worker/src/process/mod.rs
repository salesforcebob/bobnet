//! Webhook payload processing module.
//!
//! This module processes raw webhook payloads from the inbound_webhooks queue
//! into SimulatorJobs for the email_simulator queue.
//!
//! ## Processing Flow
//!
//! ```text
//! InboundWebhook → process_webhook() → SimulatorJob
//! ```

pub mod cloudflare;
pub mod email_parser;
pub mod mailgun;

use anyhow::Result;
use tracing::info;

use crate::queue::{InboundWebhook, SimulatorJob};

pub use cloudflare::process_cloudflare;
pub use email_parser::{parse_raw_email, ParsedEmail};
pub use mailgun::process_mailgun;

/// Process an inbound webhook into a simulator job.
///
/// Routes to the appropriate provider-specific processor based on the
/// webhook type.
pub fn process_webhook(webhook: InboundWebhook) -> Result<SimulatorJob> {
    info!("webhook_process_start");

    let job = match webhook {
        InboundWebhook::Mailgun(payload) => {
            info!(provider = "mailgun", "webhook_routing");
            process_mailgun(payload)?
        }
        InboundWebhook::Cloudflare(payload) => {
            info!(provider = "cloudflare", "webhook_routing");
            process_cloudflare(payload)?
        }
    };

    info!(
        message_id = %job.message_id,
        to = %job.to,
        has_html = job.html.is_some(),
        "webhook_process_complete"
    );

    Ok(job)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::queue::{CloudflareRawPayload, MailgunRawPayload};

    #[test]
    fn test_process_webhook_mailgun() {
        let webhook = InboundWebhook::Mailgun(MailgunRawPayload {
            recipient: "test@example.com".to_string(),
            sender: "".to_string(),
            subject: "Test".to_string(),
            body_html: Some("<html>Test</html>".to_string()),
            body_plain: None,
            stripped_html: None,
            message_headers: Some(r#"[["Message-Id", "<msg@example.com>"]]"#.to_string()),
            from_field: "".to_string(),
            timestamp: "".to_string(),
            token: "".to_string(),
        });

        let job = process_webhook(webhook).unwrap();

        assert_eq!(job.message_id, "msg@example.com");
        assert_eq!(job.to, "test@example.com");
    }

    #[test]
    fn test_process_webhook_cloudflare() {
        let webhook = InboundWebhook::Cloudflare(CloudflareRawPayload {
            from_field: "sender@example.com".to_string(),
            to: "recipient@example.com".to_string(),
            subject: "Test".to_string(),
            timestamp: "".to_string(),
            raw_content: r#"Message-Id: <cf@example.com>
Content-Type: text/html

<html>Test</html>"#
                .to_string(),
        });

        let job = process_webhook(webhook).unwrap();

        assert_eq!(job.message_id, "cf@example.com");
        assert_eq!(job.to, "recipient@example.com");
    }
}
