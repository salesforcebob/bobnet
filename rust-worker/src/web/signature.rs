//! Mailgun webhook signature verification.
//!
//! Mailgun signs webhook requests using HMAC-SHA256.
//! Reference: https://documentation.mailgun.com/docs/mailgun/user-manual/events/webhooks/#securing-webhooks

use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::warn;

type HmacSha256 = Hmac<Sha256>;

/// Verify a Mailgun webhook signature.
///
/// Mailgun webhooks include three fields for signature verification:
/// - timestamp: Unix epoch seconds when the webhook was generated
/// - token: A randomly generated string
/// - signature: HMAC-SHA256 hex digest of timestamp + token
///
/// # Arguments
///
/// * `signing_key` - Your Mailgun HTTP webhook signing key
/// * `timestamp` - The 'timestamp' field from the webhook payload
/// * `token` - The 'token' field from the webhook payload
/// * `signature` - The 'signature' field from the webhook payload
/// * `max_age_seconds` - Maximum allowed age of the timestamp (prevents replay attacks)
///
/// # Returns
///
/// `true` if the signature is valid and not stale, `false` otherwise.
pub fn verify_mailgun_signature(
    signing_key: &str,
    timestamp: &str,
    token: &str,
    signature: &str,
    max_age_seconds: u64,
) -> bool {
    // Check for empty inputs
    if signing_key.is_empty() || timestamp.is_empty() || token.is_empty() || signature.is_empty() {
        warn!(
            has_signing_key = !signing_key.is_empty(),
            has_timestamp = !timestamp.is_empty(),
            has_token = !token.is_empty(),
            has_signature = !signature.is_empty(),
            "mailgun_signature_missing_fields"
        );
        return false;
    }

    // Verify timestamp is not stale (prevents replay attacks)
    let webhook_time: u64 = match timestamp.parse() {
        Ok(t) => t,
        Err(_) => {
            warn!(timestamp = %timestamp, "mailgun_signature_invalid_timestamp");
            return false;
        }
    };

    let current_time = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let age = if current_time > webhook_time {
        current_time - webhook_time
    } else {
        webhook_time - current_time
    };

    if age > max_age_seconds {
        warn!(
            webhook_time = webhook_time,
            current_time = current_time,
            age_seconds = age,
            max_age_seconds = max_age_seconds,
            "mailgun_signature_stale"
        );
        return false;
    }

    // Compute expected signature: HMAC-SHA256(signing_key, timestamp + token)
    let mut mac = match HmacSha256::new_from_slice(signing_key.as_bytes()) {
        Ok(m) => m,
        Err(_) => {
            warn!("mailgun_signature_invalid_key");
            return false;
        }
    };

    mac.update(format!("{}{}", timestamp, token).as_bytes());

    let expected_signature = hex::encode(mac.finalize().into_bytes());

    // Constant-time comparison to prevent timing attacks
    let valid = constant_time_compare(&expected_signature, signature);

    if !valid {
        warn!(
            expected_length = expected_signature.len(),
            actual_length = signature.len(),
            "mailgun_signature_mismatch"
        );
    }

    valid
}

/// Constant-time string comparison to prevent timing attacks.
fn constant_time_compare(a: &str, b: &str) -> bool {
    if a.len() != b.len() {
        return false;
    }

    let mut result = 0u8;
    for (x, y) in a.bytes().zip(b.bytes()) {
        result |= x ^ y;
    }
    result == 0
}

/// Check if Mailgun signature verification is enabled.
pub fn is_signature_verification_enabled(signing_key: &Option<String>) -> bool {
    signing_key
        .as_ref()
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verify_signature_missing_fields() {
        assert!(!verify_mailgun_signature("", "123", "token", "sig", 300));
        assert!(!verify_mailgun_signature("key", "", "token", "sig", 300));
        assert!(!verify_mailgun_signature("key", "123", "", "sig", 300));
        assert!(!verify_mailgun_signature("key", "123", "token", "", 300));
    }

    #[test]
    fn test_verify_signature_invalid_timestamp() {
        assert!(!verify_mailgun_signature(
            "key",
            "not-a-number",
            "token",
            "sig",
            300
        ));
    }

    #[test]
    fn test_verify_signature_stale() {
        // Very old timestamp (year 2000)
        assert!(!verify_mailgun_signature(
            "key",
            "946684800",
            "token",
            "sig",
            300
        ));
    }

    #[test]
    fn test_verify_signature_valid() {
        use std::time::{SystemTime, UNIX_EPOCH};

        let signing_key = "test-signing-key";
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs()
            .to_string();
        let token = "random-token";

        // Compute expected signature
        let mut mac = HmacSha256::new_from_slice(signing_key.as_bytes()).unwrap();
        mac.update(format!("{}{}", timestamp, token).as_bytes());
        let signature = hex::encode(mac.finalize().into_bytes());

        assert!(verify_mailgun_signature(
            signing_key,
            &timestamp,
            token,
            &signature,
            300
        ));
    }

    #[test]
    fn test_constant_time_compare() {
        assert!(constant_time_compare("abc", "abc"));
        assert!(!constant_time_compare("abc", "abd"));
        assert!(!constant_time_compare("abc", "abcd"));
    }

    #[test]
    fn test_is_signature_verification_enabled() {
        assert!(!is_signature_verification_enabled(&None));
        assert!(!is_signature_verification_enabled(&Some("".to_string())));
        assert!(!is_signature_verification_enabled(&Some("   ".to_string())));
        assert!(is_signature_verification_enabled(&Some(
            "key123".to_string()
        )));
    }
}
