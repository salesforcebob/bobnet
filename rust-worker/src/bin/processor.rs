//! BobNet Processor - Webhook payload processor.
//!
//! This binary:
//! 1. Consumes raw webhook payloads from the inbound_webhooks queue
//! 2. Parses and processes them (email parsing, Message-Id extraction)
//! 3. Publishes prepared jobs to the email_simulator queue
//!
//! This separates the heavy lifting (parsing) from the web server,
//! allowing the web server to remain extremely fast and responsive.

use std::sync::Arc;

use anyhow::{Context, Result};
use futures::StreamExt;
use lapin::{
    options::{BasicAckOptions, BasicConsumeOptions, BasicNackOptions, BasicQosOptions, QueueDeclareOptions},
    types::FieldTable,
    Connection, ConnectionProperties,
};
use tokio::signal;
use tracing::{error, info, warn};
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use bobnet::{
    process_webhook, Config, InboundWebhook, Publisher, INBOUND_QUEUE, SIMULATOR_QUEUE,
};

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize structured JSON logging
    let filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().json().flatten_event(true))
        .init();

    info!("processor_starting");

    // Load configuration
    let config = Config::from_env();
    info!(
        concurrency = config.worker_concurrency,
        "config_loaded"
    );

    // Run the processor
    run(config).await?;

    Ok(())
}

/// Run the processor.
async fn run(config: Config) -> Result<()> {
    let config = Arc::new(config);

    // Connect to RabbitMQ for consuming
    info!(url_length = config.cloudamqp_url.len(), "rabbitmq_connecting");

    let conn = Connection::connect(&config.cloudamqp_url, ConnectionProperties::default())
        .await
        .context("Failed to connect to RabbitMQ")?;

    info!("rabbitmq_connected");

    // Create a channel for consuming
    let channel = conn
        .create_channel()
        .await
        .context("Failed to create channel")?;

    info!("rabbitmq_channel_created");

    // Set QoS with high prefetch for concurrent processing
    let prefetch_count = config.worker_concurrency as u16;
    channel
        .basic_qos(prefetch_count, BasicQosOptions::default())
        .await
        .context("Failed to set QoS")?;

    info!(prefetch_count = prefetch_count, "rabbitmq_qos_set");

    // Declare both queues
    channel
        .queue_declare(
            INBOUND_QUEUE,
            QueueDeclareOptions {
                durable: true,
                ..Default::default()
            },
            FieldTable::default(),
        )
        .await
        .context("Failed to declare inbound queue")?;

    channel
        .queue_declare(
            SIMULATOR_QUEUE,
            QueueDeclareOptions {
                durable: true,
                ..Default::default()
            },
            FieldTable::default(),
        )
        .await
        .context("Failed to declare simulator queue")?;

    info!(
        inbound_queue = INBOUND_QUEUE,
        simulator_queue = SIMULATOR_QUEUE,
        "rabbitmq_queues_declared"
    );

    // Create publisher for output queue
    let publisher = Publisher::new(config.cloudamqp_url.clone());
    let publisher = Arc::new(publisher);

    // Start consuming from inbound queue
    let mut consumer = channel
        .basic_consume(
            INBOUND_QUEUE,
            "rust-processor",
            BasicConsumeOptions::default(),
            FieldTable::default(),
        )
        .await
        .context("Failed to start consumer")?;

    info!(queue = INBOUND_QUEUE, "rabbitmq_consumer_started");
    info!("processor_ready");

    // Clone channel for use in message handler
    let channel = Arc::new(channel);

    // Create shutdown signal future
    let shutdown = async {
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
    };

    // Pin the shutdown future
    tokio::pin!(shutdown);

    // Process messages until shutdown
    loop {
        tokio::select! {
            // Check for shutdown signal
            _ = &mut shutdown => {
                info!("processor_stopping");
                break;
            }
            // Process next message
            delivery = consumer.next() => {
                match delivery {
                    Some(Ok(delivery)) => {
                        let delivery_tag = delivery.delivery_tag;
                        let message_id = delivery
                            .properties
                            .message_id()
                            .as_ref()
                            .map(|s| s.to_string())
                            .unwrap_or_else(|| "unknown".to_string());

                        info!(
                            queue = INBOUND_QUEUE,
                            message_id = %message_id,
                            delivery_tag = delivery_tag,
                            body_length = delivery.data.len(),
                            "rabbitmq_webhook_received"
                        );

                        // Clone resources for the spawned task
                        let publisher = Arc::clone(&publisher);
                        let channel = Arc::clone(&channel);

                        // Spawn a task to process this message
                        tokio::spawn(async move {
                            // Parse the inbound webhook
                            let webhook: Result<InboundWebhook, _> =
                                serde_json::from_slice(&delivery.data);

                            match webhook {
                                Ok(webhook) => {
                                    // Process the webhook into a simulator job
                                    match process_webhook(webhook) {
                                        Ok(job) => {
                                            // Publish to simulator queue
                                            if let Err(e) =
                                                publisher.publish_simulator(&job).await
                                            {
                                                error!(
                                                    message_id = %job.message_id,
                                                    error = %e,
                                                    "rabbitmq_publish_failed"
                                                );
                                                // Nack and requeue on publish failure
                                                let _ = channel
                                                    .basic_nack(
                                                        delivery_tag,
                                                        BasicNackOptions {
                                                            requeue: true,
                                                            ..Default::default()
                                                        },
                                                    )
                                                    .await;
                                                return;
                                            }

                                            // Acknowledge the original message
                                            if let Err(e) = channel
                                                .basic_ack(
                                                    delivery_tag,
                                                    BasicAckOptions::default(),
                                                )
                                                .await
                                            {
                                                error!(
                                                    delivery_tag = delivery_tag,
                                                    error = %e,
                                                    "rabbitmq_ack_failed"
                                                );
                                            } else {
                                                info!(
                                                    message_id = %job.message_id,
                                                    to = %job.to,
                                                    has_html = job.html.is_some(),
                                                    "webhook_processed"
                                                );
                                            }
                                        }
                                        Err(e) => {
                                            error!(
                                                message_id = %message_id,
                                                error = %e,
                                                "webhook_process_failed"
                                            );

                                            // Nack and don't requeue on processing error
                                            // (the message is likely malformed)
                                            let _ = channel
                                                .basic_nack(
                                                    delivery_tag,
                                                    BasicNackOptions {
                                                        requeue: false,
                                                        ..Default::default()
                                                    },
                                                )
                                                .await;
                                        }
                                    }
                                }
                                Err(e) => {
                                    error!(
                                        message_id = %message_id,
                                        error = %e,
                                        body_preview = %String::from_utf8_lossy(
                                            &delivery.data[..delivery.data.len().min(500)]
                                        ),
                                        "webhook_parse_failed"
                                    );

                                    // Nack and don't requeue on parse error
                                    let _ = channel
                                        .basic_nack(
                                            delivery_tag,
                                            BasicNackOptions {
                                                requeue: false,
                                                ..Default::default()
                                            },
                                        )
                                        .await;
                                }
                            }
                        });
                    }
                    Some(Err(e)) => {
                        error!(error = %e, "rabbitmq_delivery_error");
                    }
                    None => {
                        warn!("rabbitmq_consumer_closed");
                        break;
                    }
                }
            }
        }
    }

    // Close publisher
    publisher.close().await;

    info!("processor_shutdown_complete");
    Ok(())
}
