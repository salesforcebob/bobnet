//! RabbitMQ consumer module using lapin.
//!
//! This module handles connecting to RabbitMQ, consuming messages from the
//! email_simulator queue, and spawning async tasks to process each message
//! concurrently.

use std::sync::Arc;

use anyhow::{Context, Result};
use futures::StreamExt;
use lapin::{
    options::{BasicAckOptions, BasicConsumeOptions, BasicNackOptions, BasicQosOptions, QueueDeclareOptions},
    types::FieldTable,
    Connection, ConnectionProperties,
};
use reqwest::Client;
use tokio::signal;
use tracing::{error, info, warn};

use bobnet::{Config, SIMULATOR_QUEUE};
use crate::processor::{process_job, Job};

/// Run the RabbitMQ consumer.
///
/// This function:
/// 1. Connects to RabbitMQ using the configured URL
/// 2. Sets up QoS with high prefetch for concurrent processing
/// 3. Declares the queue (idempotent operation)
/// 4. Starts consuming messages, spawning a task for each
/// 5. Handles graceful shutdown on SIGINT/SIGTERM
pub async fn run(config: Config) -> Result<()> {
    let config = Arc::new(config);

    // Connect to RabbitMQ
    info!(url_length = config.cloudamqp_url.len(), "rabbitmq_connecting");

    let conn = Connection::connect(
        &config.cloudamqp_url,
        ConnectionProperties::default(),
    )
    .await
    .context("Failed to connect to RabbitMQ")?;

    info!("rabbitmq_connected");

    // Create a channel
    let channel = conn.create_channel().await.context("Failed to create channel")?;

    info!("rabbitmq_channel_created");

    // Set QoS with high prefetch for concurrent processing
    let prefetch_count = config.worker_concurrency as u16;
    channel
        .basic_qos(prefetch_count, BasicQosOptions::default())
        .await
        .context("Failed to set QoS")?;

    info!(prefetch_count = prefetch_count, "rabbitmq_qos_set");

    // Declare the queue (durable to match Python publisher)
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
        .context("Failed to declare queue")?;

    info!(queue = SIMULATOR_QUEUE, "rabbitmq_queue_declared");

    // Create a shared HTTP client for all requests
    let client = Client::builder()
        .pool_max_idle_per_host(100)
        .build()
        .context("Failed to create HTTP client")?;

    let client = Arc::new(client);

    // Start consuming messages
    let mut consumer = channel
        .basic_consume(
            SIMULATOR_QUEUE,
            "rust-worker",
            BasicConsumeOptions::default(),
            FieldTable::default(),
        )
        .await
        .context("Failed to start consumer")?;

    info!(queue = SIMULATOR_QUEUE, "rabbitmq_consumer_started");
    info!("worker_ready");

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
                info!("worker_stopping");
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
                            queue = SIMULATOR_QUEUE,
                            message_id = %message_id,
                            delivery_tag = delivery_tag,
                            "rabbitmq_job_received"
                        );

                        // Clone resources for the spawned task
                        let client = Arc::clone(&client);
                        let config = Arc::clone(&config);
                        let channel = Arc::clone(&channel);

                        // Spawn a task to process this message
                        tokio::spawn(async move {
                            // Parse the job JSON
                            let job: Result<Job, _> = serde_json::from_slice(&delivery.data);

                            match job {
                                Ok(job) => {
                                    // Process the job
                                    let _result = process_job(&client, &config, &job).await;

                                    // Acknowledge the message
                                    if let Err(e) = channel
                                        .basic_ack(delivery_tag, BasicAckOptions::default())
                                        .await
                                    {
                                        error!(
                                            delivery_tag = delivery_tag,
                                            error = %e,
                                            "rabbitmq_ack_failed"
                                        );
                                    } else {
                                        info!(
                                            queue = SIMULATOR_QUEUE,
                                            message_id = %message_id,
                                            "rabbitmq_job_completed"
                                        );
                                    }
                                }
                                Err(e) => {
                                    error!(
                                        message_id = %message_id,
                                        error = %e,
                                        "rabbitmq_job_parse_failed"
                                    );

                                    // Reject and requeue the message
                                    if let Err(nack_err) = channel
                                        .basic_nack(
                                            delivery_tag,
                                            BasicNackOptions {
                                                requeue: true,
                                                ..Default::default()
                                            },
                                        )
                                        .await
                                    {
                                        error!(
                                            delivery_tag = delivery_tag,
                                            error = %nack_err,
                                            "rabbitmq_nack_failed"
                                        );
                                    }
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

    info!("worker_shutdown_complete");
    Ok(())
}
