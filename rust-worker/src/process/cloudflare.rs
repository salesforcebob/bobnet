//! Cloudflare webhook payload processing.
//!
//! This module processes raw Cloudflare JSON payloads into SimulatorJobs.
//! Cloudflare provides raw RFC 5322 email content that needs to be parsed.

use anyhow::Result;
use sha2::{Digest, Sha256};
use tracing::info;

use crate::process::email_parser::{parse_raw_email, ParsedEmail};
use crate::queue::{CloudflareRawPayload, SimulatorJob};

/// Process a raw Cloudflare payload into a SimulatorJob.
///
/// Cloudflare provides raw RFC 5322 email content, so we need to:
/// 1. Parse the raw email using mailparse
/// 2. Extract Message-Id and HTML body
/// 3. Build the SimulatorJob
pub fn process_cloudflare(payload: CloudflareRawPayload) -> Result<SimulatorJob> {
    info!(
        from = %payload.from_field,
        to = %payload.to,
        subject = %payload.subject,
        raw_content_length = payload.raw_content.len(),
        "cloudflare_process_start"
    );

    // Parse the raw email content
    let parsed: ParsedEmail = match parse_raw_email(&payload.raw_content) {
        Ok(p) => p,
        Err(e) => {
            // If parsing fails, use fallback values
            tracing::warn!(
                error = %e,
                "cloudflare_email_parse_failed"
            );
            ParsedEmail {
                message_id: None,
                subject: Some(payload.subject.clone()),
                html: None,
            }
        }
    };

    // Use parsed Message-Id or generate fallback
    let message_id = parsed
        .message_id
        .unwrap_or_else(|| generate_fallback_id(&payload.subject, &payload.to));

    // Use parsed subject if available, otherwise use payload subject
    let _subject = parsed.subject.unwrap_or_else(|| payload.subject.clone());

    info!(
        message_id = %message_id,
        has_html = parsed.html.is_some(),
        html_length = parsed.html.as_ref().map(|s| s.len()).unwrap_or(0),
        "cloudflare_process_complete"
    );

    Ok(SimulatorJob::new(message_id, payload.to, parsed.html))
}

/// Generate a fallback Message-Id using SHA256 hash.
fn generate_fallback_id(subject: &str, to: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(format!("{}-{}", subject, to).as_bytes());
    let hash = hex::encode(hasher.finalize());

    info!(
        subject = %subject,
        to = %to,
        generated_id = %hash,
        "cloudflare_message_id_fallback"
    );

    hash
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_cloudflare_simple_html() {
        let payload = CloudflareRawPayload {
            from_field: "sender@example.com".to_string(),
            to: "recipient@example.com".to_string(),
            subject: "Test Subject".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            raw_content: r#"Message-Id: <test123@example.com>
Content-Type: text/html

<html><body>Hello World</body></html>"#
                .to_string(),
        };

        let job = process_cloudflare(payload).unwrap();

        assert_eq!(job.message_id, "test123@example.com");
        assert_eq!(job.to, "recipient@example.com");
        assert!(job.html.is_some());
        assert!(job.html.unwrap().contains("Hello World"));
    }

    #[test]
    fn test_process_cloudflare_fallback_message_id() {
        let payload = CloudflareRawPayload {
            from_field: "sender@example.com".to_string(),
            to: "recipient@example.com".to_string(),
            subject: "No Message ID".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            raw_content: r#"Content-Type: text/html

<html><body>Test</body></html>"#
                .to_string(),
        };

        let job = process_cloudflare(payload).unwrap();

        // Should have generated a fallback hash
        assert!(!job.message_id.is_empty());
        assert!(job.message_id.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_process_cloudflare_multipart() {
        let payload = CloudflareRawPayload {
            from_field: "sender@example.com".to_string(),
            to: "recipient@example.com".to_string(),
            subject: "Multipart Test".to_string(),
            timestamp: "2024-01-01T00:00:00Z".to_string(),
            raw_content: r#"Message-Id: <multi@example.com>
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain

Plain text

--boundary123
Content-Type: text/html

<html><body>HTML content</body></html>

--boundary123--"#
                .to_string(),
        };

        let job = process_cloudflare(payload).unwrap();

        assert_eq!(job.message_id, "multi@example.com");
        assert!(job.html.is_some());
        assert!(job.html.unwrap().contains("HTML content"));
    }

    #[test]
    fn test_generate_fallback_id() {
        let id1 = generate_fallback_id("Subject", "test@example.com");
        let id2 = generate_fallback_id("Subject", "test@example.com");
        let id3 = generate_fallback_id("Different", "test@example.com");

        assert_eq!(id1, id2);
        assert_ne!(id1, id3);
    }
}
