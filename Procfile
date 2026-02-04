# Rust Web Server - receives webhooks and enqueues to inbound_webhooks queue
web: rust-worker/target/release/bobnet-web

# Rust Processor - processes inbound webhooks and enqueues to email_simulator queue
processor: rust-worker/target/release/bobnet-processor

# Rust Worker - simulates email opens and clicks from email_simulator queue
rust-worker: rust-worker/target/release/bobnet-worker

# Legacy Python Web Server (keep for migration, remove after Rust web server is stable)
# python-web: gunicorn app.web:app -k uvicorn.workers.UvicornWorker --log-level info
