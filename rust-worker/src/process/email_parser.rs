//! RFC 5322 Email Parser using mailparse.
//!
//! This module provides functions to parse raw RFC 5322 email content
//! and extract HTML body and Message-Id headers. Used by the processor
//! to parse Cloudflare's raw_content field.

use anyhow::{Context, Result};
use mailparse::{parse_mail, MailHeaderMap, ParsedMail};
use tracing::{info, warn};

/// Parsed email result.
#[derive(Debug, Default)]
pub struct ParsedEmail {
    /// Message-Id header value (without angle brackets)
    pub message_id: Option<String>,
    /// Subject header value
    pub subject: Option<String>,
    /// HTML body content
    pub html: Option<String>,
}

/// Parse raw RFC 5322 email content.
///
/// # Arguments
///
/// * `raw_content` - Raw email string (headers + body)
///
/// # Returns
///
/// A `ParsedEmail` containing the extracted Message-Id, Subject, and HTML body.
pub fn parse_raw_email(raw_content: &str) -> Result<ParsedEmail> {
    info!(
        raw_content_length = raw_content.len(),
        raw_content_preview = &raw_content[..raw_content.len().min(200)],
        "email_parse_start"
    );

    let mail = parse_mail(raw_content.as_bytes()).context("Failed to parse email")?;

    // Extract Message-Id header
    let message_id = mail
        .headers
        .get_first_value("Message-Id")
        .or_else(|| mail.headers.get_first_value("Message-ID"))
        .map(|id| id.trim_matches(|c| c == '<' || c == '>').to_string());

    // Extract Subject header
    let subject = mail.headers.get_first_value("Subject");

    // Extract HTML body
    let html = extract_html_body(&mail);

    let result = ParsedEmail {
        message_id: message_id.clone(),
        subject: subject.clone(),
        html: html.clone(),
    };

    info!(
        message_id = ?message_id,
        subject = ?subject,
        has_html = html.is_some(),
        html_length = html.as_ref().map(|h| h.len()).unwrap_or(0),
        "email_parse_complete"
    );

    Ok(result)
}

/// Extract HTML body from a parsed email.
///
/// Handles various email structures:
/// - text/html (direct HTML content)
/// - multipart/alternative (prefers HTML over plain text)
/// - multipart/related (finds HTML part within)
/// - multipart/mixed (searches for HTML part)
fn extract_html_body(mail: &ParsedMail) -> Option<String> {
    let content_type = mail.ctype.mimetype.as_str();

    info!(
        content_type = content_type,
        subparts_count = mail.subparts.len(),
        "email_extract_html_start"
    );

    // Direct HTML content
    if content_type == "text/html" {
        return extract_body_text(mail);
    }

    // Multipart message - search through parts
    if content_type.starts_with("multipart/") {
        return find_html_in_parts(&mail.subparts);
    }

    // Not HTML and not multipart - check if it contains HTML anyway
    if content_type == "text/plain" {
        let body = extract_body_text(mail)?;
        // Check if plain text actually contains HTML
        let body_lower = body.to_lowercase();
        if body_lower.contains("<html") || body_lower.contains("<body") {
            warn!("email_plain_contains_html");
            return Some(body);
        }
    }

    warn!(
        content_type = content_type,
        "email_no_html_found"
    );
    None
}

/// Find HTML content within multipart subparts.
fn find_html_in_parts(parts: &[ParsedMail]) -> Option<String> {
    let mut html_parts: Vec<String> = Vec::new();

    for (index, part) in parts.iter().enumerate() {
        let part_type = part.ctype.mimetype.as_str();

        info!(
            part_index = index,
            part_type = part_type,
            subparts_count = part.subparts.len(),
            "email_examining_part"
        );

        if part_type == "text/html" {
            if let Some(html) = extract_body_text(part) {
                if !html.trim().is_empty() {
                    info!(
                        part_index = index,
                        html_length = html.len(),
                        "email_html_part_found"
                    );
                    html_parts.push(html);
                }
            }
        } else if part_type.starts_with("multipart/") {
            // Recursively search nested multipart
            if let Some(html) = find_html_in_parts(&part.subparts) {
                html_parts.push(html);
            }
        }
    }

    if html_parts.is_empty() {
        None
    } else if html_parts.len() == 1 {
        Some(html_parts.remove(0))
    } else {
        // Multiple HTML parts - combine them
        info!(
            html_parts_count = html_parts.len(),
            "email_multiple_html_parts"
        );
        Some(html_parts.join("\n"))
    }
}

/// Extract the body text from a mail part.
fn extract_body_text(mail: &ParsedMail) -> Option<String> {
    match mail.get_body() {
        Ok(body) => {
            if body.trim().is_empty() {
                None
            } else {
                Some(body)
            }
        }
        Err(e) => {
            warn!(error = %e, "email_body_extraction_failed");
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_html_email() {
        let raw = r#"Message-Id: <test123@example.com>
Subject: Test Subject
Content-Type: text/html

<html><body>Hello World</body></html>"#;

        let result = parse_raw_email(raw).unwrap();

        assert_eq!(result.message_id, Some("test123@example.com".to_string()));
        assert_eq!(result.subject, Some("Test Subject".to_string()));
        assert!(result.html.is_some());
        assert!(result.html.unwrap().contains("Hello World"));
    }

    #[test]
    fn test_parse_multipart_alternative() {
        let raw = r#"Message-Id: <multi123@example.com>
Subject: Multipart Test
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain

Plain text version

--boundary123
Content-Type: text/html

<html><body>HTML version</body></html>

--boundary123--"#;

        let result = parse_raw_email(raw).unwrap();

        assert_eq!(result.message_id, Some("multi123@example.com".to_string()));
        assert!(result.html.is_some());
        assert!(result.html.unwrap().contains("HTML version"));
    }

    #[test]
    fn test_parse_message_id_without_brackets() {
        let raw = r#"Message-Id: test456@example.com
Content-Type: text/html

<html>Test</html>"#;

        let result = parse_raw_email(raw).unwrap();

        // Should work with or without angle brackets
        assert!(result.message_id.is_some());
        assert!(!result.message_id.unwrap().contains('<'));
    }

    #[test]
    fn test_parse_no_message_id() {
        let raw = r#"Subject: No Message ID
Content-Type: text/html

<html>Test</html>"#;

        let result = parse_raw_email(raw).unwrap();

        assert!(result.message_id.is_none());
        assert!(result.html.is_some());
    }

    #[test]
    fn test_parse_no_html() {
        let raw = r#"Message-Id: <plain@example.com>
Content-Type: text/plain

This is plain text only."#;

        let result = parse_raw_email(raw).unwrap();

        assert!(result.message_id.is_some());
        assert!(result.html.is_none());
    }

    #[test]
    fn test_parse_nested_multipart() {
        let raw = r#"Message-Id: <nested@example.com>
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/alternative; boundary="inner"

--inner
Content-Type: text/plain

Plain text

--inner
Content-Type: text/html

<html><body>Nested HTML</body></html>

--inner--

--outer--"#;

        let result = parse_raw_email(raw).unwrap();

        assert!(result.html.is_some());
        assert!(result.html.unwrap().contains("Nested HTML"));
    }
}
