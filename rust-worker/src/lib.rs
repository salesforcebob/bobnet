//! BobNet - High-performance email simulation system.
//!
//! This library provides shared modules for the three BobNet binaries:
//! - `bobnet-web`: Thin web server for receiving webhooks
//! - `bobnet-processor`: Processor for parsing and preparing jobs
//! - `bobnet-worker`: Email simulator for opens and clicks
//!
//! ## Architecture
//!
//! ```text
//! Webhooks → Web Server → inbound_webhooks → Processor → email_simulator → Worker
//! ```

pub mod config;
pub mod html;
pub mod process;
pub mod queue;
pub mod simulate;
pub mod util;
pub mod web;

// Re-export commonly used types
pub use config::Config;
pub use process::{process_webhook, ParsedEmail};
pub use queue::{
    CloudflareRawPayload, InboundWebhook, MailgunRawPayload, Publisher, SimulatorJob,
    INBOUND_QUEUE, SIMULATOR_QUEUE,
};
pub use web::AppState;
