//! BobNet Web Server - High-performance webhook receiver.
//!
//! This binary provides a thin, fast web server that:
//! - Receives webhooks from Mailgun and Cloudflare
//! - Verifies authentication
//! - Immediately enqueues raw payloads to RabbitMQ
//! - Returns 200 OK in microseconds
//!
//! All parsing and processing happens in the background processor.

use std::net::SocketAddr;

use anyhow::{Context, Result};
use axum::{
    routing::{get, post},
    Router,
};
use tokio::{net::TcpListener, signal};
use tower_http::trace::TraceLayer;
use tracing::info;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use bobnet::web::{cloudflare_webhook, health, mailgun_webhook, AppState};
use bobnet::{Config, Publisher};

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize structured JSON logging
    let filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().json().flatten_event(true))
        .init();

    info!("web_server_starting");

    // Load configuration
    let config = Config::from_env();
    info!(
        port = config.port,
        cloudflare_auth_configured = config.cloudflare_auth_token.is_some(),
        mailgun_signing_configured = config.mailgun_signing_key.is_some(),
        mailgun_domain = ?config.mailgun_domain,
        "config_loaded"
    );

    // Create RabbitMQ publisher
    let publisher = Publisher::new(config.cloudamqp_url.clone());
    info!("rabbitmq_publisher_created");

    // Create application state
    let state = AppState::new(config.clone(), publisher.clone());

    // Build the router
    let app = Router::new()
        .route("/health", get(health))
        .route("/webhooks/mailgun", post(mailgun_webhook))
        .route("/webhooks/cloudflare", post(cloudflare_webhook))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    // Bind to address
    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    let listener = TcpListener::bind(addr)
        .await
        .context("Failed to bind to address")?;

    info!(address = %addr, "web_server_listening");

    // Run server with graceful shutdown
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .context("Server error")?;

    // Close publisher connection
    publisher.close().await;

    info!("web_server_shutdown_complete");

    Ok(())
}

/// Create a future that completes when a shutdown signal is received.
async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => info!("Received SIGINT"),
        _ = terminate => info!("Received SIGTERM"),
    }

    info!("web_server_shutting_down");
}
