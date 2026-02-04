//! Queue module for RabbitMQ operations.
//!
//! This module provides:
//! - Message types for the two-queue architecture
//! - Async publisher for enqueueing messages
//!
//! ## Architecture
//!
//! ```text
//! Web Server → inbound_webhooks queue → Processor → email_simulator queue → Worker
//! ```

pub mod publisher;
pub mod types;

pub use publisher::Publisher;
pub use types::{
    CloudflareRawPayload, InboundWebhook, MailgunRawPayload, SimulatorJob,
    INBOUND_QUEUE, SIMULATOR_QUEUE,
};
