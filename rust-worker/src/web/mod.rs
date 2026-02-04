//! Web server module for handling inbound webhooks.
//!
//! This module provides a thin, fast web server that:
//! - Receives webhooks from Mailgun and Cloudflare
//! - Verifies authentication
//! - Immediately enqueues raw payloads to RabbitMQ
//! - Returns 200 OK in microseconds
//!
//! All parsing and processing happens in the background processor.

pub mod handlers;
pub mod signature;

pub use handlers::{
    cloudflare_webhook, health, mailgun_webhook, AppState, CloudflarePayload,
    HealthResponse, MailgunForm, WebhookResponse,
};
pub use signature::{is_signature_verification_enabled, verify_mailgun_signature};
