//! Webhook endpoint handlers.
//!
//! These handlers are designed to be extremely fast - they only:
//! 1. Verify authentication
//! 2. Enqueue the raw payload to RabbitMQ
//! 3. Return immediately
//!
//! All parsing and processing happens in the background processor.

use std::sync::Arc;

use axum::{
    extract::{Form, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};
use tracing::{error, info, warn};

use crate::queue::{CloudflareRawPayload, InboundWebhook, MailgunRawPayload, Publisher};
use crate::web::signature::{is_signature_verification_enabled, verify_mailgun_signature};
use crate::Config;

/// Shared application state.
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
    pub publisher: Publisher,
}

impl AppState {
    pub fn new(config: Config, publisher: Publisher) -> Self {
        Self {
            config: Arc::new(config),
            publisher,
        }
    }
}

// =============================================================================
// Health Check
// =============================================================================

/// Health check response.
#[derive(Serialize)]
pub struct HealthResponse {
    pub status: &'static str,
}

/// Health check endpoint.
pub async fn health() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

// =============================================================================
// Mailgun Webhook
// =============================================================================

/// Mailgun form payload.
///
/// Mailgun sends form-encoded data, not JSON.
/// Field names use hyphens, which are aliased here.
#[derive(Debug, Deserialize)]
pub struct MailgunForm {
    pub recipient: String,
    #[serde(default)]
    pub sender: String,
    #[serde(default)]
    pub subject: String,
    #[serde(default, rename = "body-html")]
    pub body_html: Option<String>,
    #[serde(default, rename = "body-plain")]
    pub body_plain: Option<String>,
    #[serde(default, rename = "stripped-html")]
    pub stripped_html: Option<String>,
    #[serde(default, rename = "stripped-text")]
    pub stripped_text: Option<String>,
    #[serde(default, rename = "message-headers")]
    pub message_headers: Option<String>,
    #[serde(default, rename = "from")]
    pub from_field: String,
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub token: String,
    #[serde(default)]
    pub signature: String,
}

/// Webhook response.
#[derive(Serialize)]
pub struct WebhookResponse {
    pub status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message_id: Option<String>,
}

/// Mailgun webhook endpoint.
///
/// This endpoint:
/// 1. Verifies the HMAC signature (if configured)
/// 2. Enqueues the raw payload immediately
/// 3. Returns 200 OK
pub async fn mailgun_webhook(
    State(state): State<AppState>,
    Form(form): Form<MailgunForm>,
) -> impl IntoResponse {
    info!(
        recipient = %form.recipient,
        has_body_html = form.body_html.is_some(),
        body_html_length = form.body_html.as_ref().map(|s| s.len()).unwrap_or(0),
        has_signature = !form.signature.is_empty(),
        "mailgun_webhook_received"
    );

    // Verify signature if signing key is configured
    if is_signature_verification_enabled(&state.config.mailgun_signing_key) {
        let signing_key = state.config.mailgun_signing_key.as_ref().unwrap();
        if !verify_mailgun_signature(
            signing_key,
            &form.timestamp,
            &form.token,
            &form.signature,
            state.config.mailgun_signature_max_age,
        ) {
            warn!(recipient = %form.recipient, "mailgun_signature_invalid");
            return (
                StatusCode::UNAUTHORIZED,
                Json(WebhookResponse {
                    status: "unauthorized",
                    message_id: None,
                }),
            );
        }
    }

    // Optional: Validate recipient matches configured domain
    if let Some(domain) = &state.config.mailgun_domain {
        if !form.recipient.ends_with(&format!("@{}", domain)) {
            warn!(
                recipient = %form.recipient,
                expected_domain = %domain,
                "mailgun_invalid_recipient_domain"
            );
            return (
                StatusCode::BAD_REQUEST,
                Json(WebhookResponse {
                    status: "invalid_domain",
                    message_id: None,
                }),
            );
        }
    }

    // Convert form to raw payload and enqueue immediately
    let payload = InboundWebhook::Mailgun(MailgunRawPayload {
        recipient: form.recipient.clone(),
        sender: form.sender,
        subject: form.subject,
        body_html: form.body_html,
        body_plain: form.body_plain,
        stripped_html: form.stripped_html,
        message_headers: form.message_headers,
        from_field: form.from_field,
        timestamp: form.timestamp,
        token: form.token,
    });

    if let Err(e) = state.publisher.publish_inbound(&payload).await {
        error!(error = %e, "mailgun_publish_failed");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(WebhookResponse {
                status: "error",
                message_id: None,
            }),
        );
    }

    info!(recipient = %form.recipient, "mailgun_enqueued");

    (
        StatusCode::OK,
        Json(WebhookResponse {
            status: "enqueued",
            message_id: Some(form.recipient),
        }),
    )
}

// =============================================================================
// Cloudflare Webhook
// =============================================================================

/// Cloudflare JSON payload.
#[derive(Debug, Deserialize)]
pub struct CloudflarePayload {
    #[serde(rename = "from")]
    pub from_field: String,
    pub to: String,
    pub subject: String,
    pub timestamp: String,
    pub raw_content: String,
}

/// Cloudflare webhook endpoint.
///
/// This endpoint:
/// 1. Verifies the X-Custom-Auth header
/// 2. Enqueues the raw payload immediately
/// 3. Returns 200 OK
pub async fn cloudflare_webhook(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CloudflarePayload>,
) -> impl IntoResponse {
    info!(
        from = %payload.from_field,
        to = %payload.to,
        subject = %payload.subject,
        raw_content_length = payload.raw_content.len(),
        "cloudflare_webhook_received"
    );

    // Verify authentication header
    let auth_header = headers
        .get("X-Custom-Auth")
        .and_then(|v| v.to_str().ok());

    let expected_token = state.config.cloudflare_auth_token.as_deref();

    match (auth_header, expected_token) {
        (Some(provided), Some(expected)) if provided == expected => {
            // Auth passes
        }
        (None, Some(_)) => {
            warn!(to = %payload.to, "cloudflare_auth_missing");
            return (
                StatusCode::UNAUTHORIZED,
                Json(WebhookResponse {
                    status: "unauthorized",
                    message_id: None,
                }),
            );
        }
        (Some(_), Some(_)) => {
            warn!(to = %payload.to, "cloudflare_auth_invalid");
            return (
                StatusCode::UNAUTHORIZED,
                Json(WebhookResponse {
                    status: "unauthorized",
                    message_id: None,
                }),
            );
        }
        (_, None) => {
            // No auth configured, allow through
            warn!("cloudflare_auth_not_configured");
        }
    }

    // Convert payload to raw payload and enqueue immediately
    let webhook = InboundWebhook::Cloudflare(CloudflareRawPayload {
        from_field: payload.from_field,
        to: payload.to.clone(),
        subject: payload.subject,
        timestamp: payload.timestamp,
        raw_content: payload.raw_content,
    });

    if let Err(e) = state.publisher.publish_inbound(&webhook).await {
        error!(error = %e, "cloudflare_publish_failed");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(WebhookResponse {
                status: "error",
                message_id: None,
            }),
        );
    }

    info!(to = %payload.to, "cloudflare_enqueued");

    (
        StatusCode::OK,
        Json(WebhookResponse {
            status: "enqueued",
            message_id: Some(payload.to),
        }),
    )
}
