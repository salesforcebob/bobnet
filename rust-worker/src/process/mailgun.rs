//! Mailgun webhook payload processing.
//!
//! This module processes raw Mailgun form payloads into SimulatorJobs.
//! Mailgun provides pre-parsed email content, so no RFC 5322 parsing is needed.

use anyhow::Result;
use sha2::{Digest, Sha256};
use tracing::{info, warn};

use crate::queue::{MailgunRawPayload, SimulatorJob};

/// Process a raw Mailgun payload into a SimulatorJob.
///
/// Mailgun provides the email body already extracted, so we just need to:
/// 1. Extract Message-Id from the headers JSON
/// 2. Get the HTML body (preferring body_html over stripped_html)
/// 3. Build the SimulatorJob
pub fn process_mailgun(payload: MailgunRawPayload) -> Result<SimulatorJob> {
    info!(
        recipient = %payload.recipient,
        has_body_html = payload.body_html.is_some(),
        body_html_length = payload.body_html.as_ref().map(|s| s.len()).unwrap_or(0),
        has_stripped_html = payload.stripped_html.is_some(),
        has_message_headers = payload.message_headers.is_some(),
        "mailgun_process_start"
    );

    // Extract Message-Id from headers JSON
    let message_id = extract_message_id_from_headers(&payload.message_headers)
        .unwrap_or_else(|| generate_fallback_id(&payload.subject, &payload.recipient));

    // Determine HTML source for logging
    let body_html_is_valid = payload.body_html.as_ref().map(|s| !s.is_empty()).unwrap_or(false);
    let stripped_html_is_valid = payload.stripped_html.as_ref().map(|s| !s.is_empty()).unwrap_or(false);

    let html_source = if body_html_is_valid {
        "body_html"
    } else if stripped_html_is_valid {
        "stripped_html"
    } else {
        "none"
    };

    // Get HTML content - prefer body_html, fall back to stripped_html
    let html = payload
        .body_html
        .filter(|s| !s.is_empty())
        .or_else(|| payload.stripped_html.filter(|s| !s.is_empty()));

    info!(
        message_id = %message_id,
        html_source = html_source,
        html_length = html.as_ref().map(|s| s.len()).unwrap_or(0),
        "mailgun_process_complete"
    );

    Ok(SimulatorJob::new(message_id, payload.recipient, html))
}

/// Extract Message-Id from Mailgun's message-headers JSON string.
///
/// Mailgun provides headers as a JSON array of [name, value] pairs, e.g.:
/// `[["Message-Id", "<abc123@example.com>"], ["Subject", "Hello"], ...]`
fn extract_message_id_from_headers(message_headers: &Option<String>) -> Option<String> {
    let headers = message_headers.as_ref()?;

    if headers.is_empty() {
        return None;
    }

    // Parse JSON array of [name, value] pairs
    let parsed: Result<Vec<Vec<String>>, _> = serde_json::from_str(headers);

    match parsed {
        Ok(header_pairs) => {
            for pair in header_pairs {
                if pair.len() >= 2 {
                    let name = &pair[0];
                    let value = &pair[1];
                    if name.to_lowercase() == "message-id" {
                        // Remove angle brackets if present
                        let clean_id = value
                            .trim()
                            .trim_matches(|c| c == '<' || c == '>')
                            .to_string();

                        if !clean_id.is_empty() {
                            info!(
                                message_id = %clean_id,
                                "mailgun_message_id_extracted"
                            );
                            return Some(clean_id);
                        }
                    }
                }
            }
            warn!("mailgun_no_message_id_in_headers");
            None
        }
        Err(e) => {
            warn!(
                error = %e,
                headers_preview = &headers[..headers.len().min(200)],
                "mailgun_headers_parse_failed"
            );
            None
        }
    }
}

/// Generate a fallback Message-Id using SHA256 hash.
fn generate_fallback_id(subject: &str, recipient: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(format!("{}-{}", subject, recipient).as_bytes());
    let hash = hex::encode(hasher.finalize());

    info!(
        subject = %subject,
        recipient = %recipient,
        generated_id = %hash,
        "mailgun_message_id_fallback"
    );

    hash
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_message_id_from_headers() {
        let headers =
            r#"[["Message-Id", "<abc123@example.com>"], ["Subject", "Hello"]]"#.to_string();

        let result = extract_message_id_from_headers(&Some(headers));

        assert_eq!(result, Some("abc123@example.com".to_string()));
    }

    #[test]
    fn test_extract_message_id_case_insensitive() {
        let headers =
            r#"[["message-id", "<test@example.com>"], ["subject", "Test"]]"#.to_string();

        let result = extract_message_id_from_headers(&Some(headers));

        assert_eq!(result, Some("test@example.com".to_string()));
    }

    #[test]
    fn test_extract_message_id_no_brackets() {
        let headers = r#"[["Message-Id", "test@example.com"]]"#.to_string();

        let result = extract_message_id_from_headers(&Some(headers));

        assert_eq!(result, Some("test@example.com".to_string()));
    }

    #[test]
    fn test_extract_message_id_missing() {
        let headers = r#"[["Subject", "Hello"], ["From", "test@example.com"]]"#.to_string();

        let result = extract_message_id_from_headers(&Some(headers));

        assert!(result.is_none());
    }

    #[test]
    fn test_extract_message_id_invalid_json() {
        let headers = "not valid json".to_string();

        let result = extract_message_id_from_headers(&Some(headers));

        assert!(result.is_none());
    }

    #[test]
    fn test_extract_message_id_empty() {
        assert!(extract_message_id_from_headers(&None).is_none());
        assert!(extract_message_id_from_headers(&Some("".to_string())).is_none());
    }

    #[test]
    fn test_generate_fallback_id() {
        let id1 = generate_fallback_id("Subject", "test@example.com");
        let id2 = generate_fallback_id("Subject", "test@example.com");
        let id3 = generate_fallback_id("Different", "test@example.com");

        // Same inputs should produce same hash
        assert_eq!(id1, id2);
        // Different inputs should produce different hash
        assert_ne!(id1, id3);
        // Should be valid hex
        assert!(id1.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_process_mailgun_with_body_html() {
        let payload = MailgunRawPayload {
            recipient: "test@example.com".to_string(),
            sender: "sender@example.com".to_string(),
            subject: "Test".to_string(),
            body_html: Some("<html>Test</html>".to_string()),
            body_plain: None,
            stripped_html: None,
            message_headers: Some(r#"[["Message-Id", "<msg@example.com>"]]"#.to_string()),
            from_field: "sender@example.com".to_string(),
            timestamp: "".to_string(),
            token: "".to_string(),
        };

        let job = process_mailgun(payload).unwrap();

        assert_eq!(job.message_id, "msg@example.com");
        assert_eq!(job.to, "test@example.com");
        assert_eq!(job.html, Some("<html>Test</html>".to_string()));
    }

    #[test]
    fn test_process_mailgun_fallback_to_stripped() {
        let payload = MailgunRawPayload {
            recipient: "test@example.com".to_string(),
            sender: "".to_string(),
            subject: "Test".to_string(),
            body_html: None,
            body_plain: None,
            stripped_html: Some("<html>Stripped</html>".to_string()),
            message_headers: None,
            from_field: "".to_string(),
            timestamp: "".to_string(),
            token: "".to_string(),
        };

        let job = process_mailgun(payload).unwrap();

        assert_eq!(job.html, Some("<html>Stripped</html>".to_string()));
    }
}
