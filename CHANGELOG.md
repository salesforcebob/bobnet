## [Unreleased]
### Added
- **Cloudflare inbound email support**
  - New `/webhooks/cloudflare` endpoint for JSON payloads from Cloudflare Workers
  - Raw email parsing utility (`app/utils/email_parse.py`) to extract HTML and Message-Id from RFC 5322 emails
  - Custom auth header verification via `X-Custom-Auth` header (configurable via `CLOUDFLARE_AUTH_TOKEN`)
  - Pydantic model (`CloudflareInbound`) for Cloudflare payload parsing
  - Integration tests for Cloudflare webhook endpoint
  - Updated README with Cloudflare setup guide and webhook contract

### Changed
- **Migrated from Redis/RQ to RabbitMQ (CloudAMQP)**
  - Replaced `redis` and `rq` dependencies with `pika` for RabbitMQ
  - Rewrote `app/queue.py` as RabbitMQ publisher using pika
  - Rewrote `app/worker_entry.py` as RabbitMQ consumer with manual acknowledgment
  - Updated `app/config.py` to use `CLOUDAMQP_URL` instead of Redis settings
  - Workers now acknowledge messages after successful processing; failed messages are requeued
  - CloudAMQP provides better queue visibility, management UI, and message inspection

### Removed
- **CloudMailIn support** - removed `/webhooks/cloudmailin` endpoint
- **Redis-based idempotency** - removed `app/utils/idempotency.py`
- Redis and RQ dependencies

---

## [Previous]
### Added
- **Mailgun inbound email support**
  - New `/webhooks/mailgun` endpoint for form-encoded Mailgun payloads
  - HMAC-SHA256 signature verification for webhook security
  - Optional domain validation via `MAILGUN_DOMAIN` config
  - Pydantic model for Mailgun payload parsing
  - Unit tests for signature verification
  - Integration tests for Mailgun webhook endpoint
  - Updated README with Mailgun setup guide

- Initial Python service to simulate email opens/clicks on Heroku
  - FastAPI webhook endpoint
  - Worker for simulation jobs
  - Direct open via image fetch; randomized clicks
  - Heroku `Procfile`, `.python-version`, `app.json` (one-click deploy)
  - README with setup and deploy instructions
  - Initial tests (unit + integration)

### Changed
- Replaced deprecated `runtime.txt` with `.python-version` specifying `3.11` to receive latest patch updates automatically.
