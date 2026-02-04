//! BobNet Worker - High-performance async RabbitMQ consumer for email simulation.
//!
//! This worker processes email simulation jobs from the email_simulator queue,
//! simulating email opens (fetching tracking pixels) and clicks (following links)
//! with configurable probabilities and delays.

mod consumer;
mod processor;

use anyhow::Result;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use bobnet::Config;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize structured JSON logging
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().json().flatten_event(true))
        .init();

    tracing::info!("worker_starting");

    // Load configuration from environment
    let config = Config::from_env();
    tracing::info!(
        cloudamqp_url_set = !config.cloudamqp_url.is_empty(),
        open_probability = config.simulate_open_probability,
        click_probability = config.simulate_click_probability,
        max_clicks = config.max_clicks,
        concurrency = config.worker_concurrency,
        "config_loaded"
    );

    // Start the consumer
    consumer::run(config).await?;

    Ok(())
}
