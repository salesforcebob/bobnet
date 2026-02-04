//! Async RabbitMQ publisher for enqueueing messages.
//!
//! This module provides a connection-pooled publisher that can be shared
//! across multiple async tasks for high-throughput message publishing.

use std::sync::Arc;

use anyhow::{Context, Result};
use lapin::{
    options::{BasicPublishOptions, QueueDeclareOptions},
    types::FieldTable,
    BasicProperties, Channel, Connection, ConnectionProperties,
};
use tokio::sync::RwLock;
use tracing::{info, warn};

use super::types::{InboundWebhook, SimulatorJob, INBOUND_QUEUE, SIMULATOR_QUEUE};

/// Async RabbitMQ publisher with connection management.
///
/// The publisher maintains a persistent connection and channel to RabbitMQ,
/// automatically reconnecting on failure.
#[derive(Clone)]
pub struct Publisher {
    inner: Arc<PublisherInner>,
}

struct PublisherInner {
    url: String,
    connection: RwLock<Option<Connection>>,
    channel: RwLock<Option<Channel>>,
}

impl Publisher {
    /// Create a new publisher with the given RabbitMQ URL.
    pub fn new(url: String) -> Self {
        Self {
            inner: Arc::new(PublisherInner {
                url,
                connection: RwLock::new(None),
                channel: RwLock::new(None),
            }),
        }
    }

    /// Ensure we have a valid connection and channel.
    async fn ensure_connected(&self) -> Result<Channel> {
        // Check if we have a valid channel
        {
            let channel = self.inner.channel.read().await;
            if let Some(ch) = channel.as_ref() {
                if ch.status().connected() {
                    return Ok(ch.clone());
                }
            }
        }

        // Need to reconnect
        let mut connection = self.inner.connection.write().await;
        let mut channel = self.inner.channel.write().await;

        // Double-check after acquiring write lock
        if let Some(ch) = channel.as_ref() {
            if ch.status().connected() {
                return Ok(ch.clone());
            }
        }

        info!("rabbitmq_publisher_connecting");

        // Create new connection
        let conn = Connection::connect(&self.inner.url, ConnectionProperties::default())
            .await
            .context("Failed to connect to RabbitMQ")?;

        info!("rabbitmq_publisher_connected");

        // Create new channel
        let ch = conn
            .create_channel()
            .await
            .context("Failed to create channel")?;

        // Declare both queues (idempotent operation)
        ch.queue_declare(
            INBOUND_QUEUE,
            QueueDeclareOptions {
                durable: true,
                ..Default::default()
            },
            FieldTable::default(),
        )
        .await
        .context("Failed to declare inbound queue")?;

        ch.queue_declare(
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

        *connection = Some(conn);
        *channel = Some(ch.clone());

        Ok(ch)
    }

    /// Publish a raw inbound webhook to the inbound_webhooks queue.
    pub async fn publish_inbound(&self, webhook: &InboundWebhook) -> Result<()> {
        let channel = self.ensure_connected().await?;

        let body = serde_json::to_vec(webhook).context("Failed to serialize webhook")?;

        // Generate a message ID for tracking
        let message_id = match webhook {
            InboundWebhook::Mailgun(p) => format!("mailgun-{}", &p.recipient),
            InboundWebhook::Cloudflare(p) => format!("cloudflare-{}", &p.to),
        };

        channel
            .basic_publish(
                "",
                INBOUND_QUEUE,
                BasicPublishOptions::default(),
                &body,
                BasicProperties::default()
                    .with_delivery_mode(2) // Persistent
                    .with_content_type("application/json".into())
                    .with_message_id(message_id.clone().into()),
            )
            .await
            .context("Failed to publish to inbound queue")?
            .await
            .context("Failed to confirm publish")?;

        info!(
            queue = INBOUND_QUEUE,
            message_id = %message_id,
            body_length = body.len(),
            "rabbitmq_inbound_published"
        );

        Ok(())
    }

    /// Publish a parsed job to the email_simulator queue.
    pub async fn publish_simulator(&self, job: &SimulatorJob) -> Result<()> {
        let channel = self.ensure_connected().await?;

        let body = serde_json::to_vec(job).context("Failed to serialize job")?;

        channel
            .basic_publish(
                "",
                SIMULATOR_QUEUE,
                BasicPublishOptions::default(),
                &body,
                BasicProperties::default()
                    .with_delivery_mode(2) // Persistent
                    .with_content_type("application/json".into())
                    .with_message_id(job.message_id.clone().into()),
            )
            .await
            .context("Failed to publish to simulator queue")?
            .await
            .context("Failed to confirm publish")?;

        info!(
            queue = SIMULATOR_QUEUE,
            message_id = %job.message_id,
            body_length = body.len(),
            "rabbitmq_simulator_published"
        );

        Ok(())
    }

    /// Close the connection gracefully.
    pub async fn close(&self) {
        let mut connection = self.inner.connection.write().await;
        let mut channel = self.inner.channel.write().await;

        if let Some(ch) = channel.take() {
            if let Err(e) = ch.close(200, "Normal shutdown").await {
                warn!(error = %e, "rabbitmq_channel_close_error");
            }
        }

        if let Some(conn) = connection.take() {
            if let Err(e) = conn.close(200, "Normal shutdown").await {
                warn!(error = %e, "rabbitmq_connection_close_error");
            }
        }

        info!("rabbitmq_publisher_closed");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_publisher_creation() {
        let publisher = Publisher::new("amqp://localhost:5672".to_string());
        // Just verify it can be created
        assert!(Arc::strong_count(&publisher.inner) == 1);
    }
}
