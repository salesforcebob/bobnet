# BobNet Email Simulator

Simulates customer behavior (opens and clicks) on inbound marketing emails. Runs on Heroku with a `web` dyno (FastAPI webhook) and a `worker` dyno (RabbitMQ consumer).

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/salesforcebob/bobnet)

Just name it. Defaults are good.

## Features
- Inbound email processing via **Mailgun** (unlimited inbound on Foundation plan)
- Randomized open simulation via direct pixel fetch (default)
- Randomized click simulation with domain allow/deny filters
- Message queue via **RabbitMQ** (CloudAMQP)
- Structured JSON logging
- HMAC signature verification for Mailgun webhooks

## Quick Start

1. Sign up for Mailgun Foundation plan ($35/month, unlimited inbound emails)
2. Add your domain and configure MX records (see [Mailgun Setup](#mailgun-setup) below)
3. Create an inbound route pointing to `https://<your-app>.herokuapp.com/webhooks/mailgun`
4. Set up CloudAMQP (see [CloudAMQP Setup](#cloudamqp-setup) below)
5. Set environment variables in Heroku config vars

## Provider References
- **Mailgun**: [Inbound Email Routing](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/routes)
- **CloudAMQP**: [Getting Started](https://www.cloudamqp.com/docs/index.html)

## Project Layout
```
app/
  web.py                 # FastAPI app (webhooks + health)
  worker.py              # Job processing logic
  worker_entry.py        # RabbitMQ consumer entrypoint
  config.py              # Env configuration
  logging.py             # JSON logging
  models.py              # Pydantic models
  queue.py               # RabbitMQ publisher
  simulate/
    html_parse.py        # HTML parsing helpers
    openers.py           # Open simulation (direct)
    clickers.py          # Click selection + execution
  utils/
    mailgun_signature.py # Mailgun HMAC signature verification
    user_agents.py       # UA rotation
```

## Configuration

### Required Settings

- `CLOUDAMQP_URL`: RabbitMQ connection URL from CloudAMQP (format: `amqps://user:pass@host/vhost`)

### Mailgun Settings

- `MAILGUN_SIGNING_KEY` (recommended): HTTP webhook signing key from Mailgun dashboard (Settings > API Security)
- `MAILGUN_DOMAIN` (optional): Restrict accepted recipients to this domain (e.g., `inbound.example.com`)

### Simulation Settings

- `SIMULATE_WITH_BROWSER` (default `false`): optional headless path (not enabled by default)
- `SIMULATE_OPEN_PROBABILITY` (default `0.7`)
- `SIMULATE_CLICK_PROBABILITY` (default `0.3`)
- `MAX_CLICKS` (default `2`)
- `OPEN_DELAY_RANGE_MS` (default `500,5000`)
- `CLICK_DELAY_RANGE_MS` (default `300,4000`)
- `REQUEST_TIMEOUT_MS` (default `8000`)

## Local Development

1. Python 3.11+ (version managed via `.python-version`, currently `3.11`)
2. RabbitMQ (e.g., `docker run -p 5672:5672 rabbitmq:3`)
3. Create `.env` with `CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/`
4. Install deps: `pip install -r requirements.txt`
5. Run web: `uvicorn app.web:app --reload --port 8000`
6. Run worker: `python -m app.worker_entry`

Webhook endpoint:
- Mailgun: `POST http://localhost:8000/webhooks/mailgun` (form-encoded)

## Heroku Deployment

This repo includes:
- `Procfile` (web + worker)
- `.python-version` (Python major version)
- `app.json` (one-click deploy)

Using the one-click button opens Heroku's deploy UI pre-configured with:
- Buildpack: heroku/python
- Formation: 1× web, 1× worker

### CloudAMQP Setup

1. **Create a CloudAMQP instance** at [cloudamqp.com](https://www.cloudamqp.com)
   - The free "Little Lemur" plan works for development/testing
   - For production, choose an appropriate paid plan
2. **Copy the AMQP URL** from your CloudAMQP dashboard
3. **Set Heroku config var**:
   ```bash
   heroku config:set CLOUDAMQP_URL=amqps://user:pass@host/vhost --app your-app
   ```

CloudAMQP provides:
- Management UI for queue inspection
- Message browsing and manual requeue
- Consumer metrics and monitoring
- Dead letter queues for failed messages

### Mailgun Setup

Mailgun offers unlimited inbound emails on the Foundation plan ($35/month).

1. **Sign up** at [mailgun.com](https://www.mailgun.com) for the Foundation plan
2. **Add your domain** (e.g., `inbound.yourdomain.com`) in the Mailgun dashboard
3. **Configure DNS records** at your DNS provider:
   - MX: `10 mxa.mailgun.org`
   - MX: `10 mxb.mailgun.org`
   - TXT (SPF): `v=spf1 include:mailgun.org ~all`
   - DKIM record (provided by Mailgun)
4. **Create an inbound route** in Mailgun (Receive > Create Route):
   - Match expression: `match_recipient(".*@inbound.yourdomain.com")`
   - Action: `forward("https://<your-app>.herokuapp.com/webhooks/mailgun")`
5. **Get your signing key** from Mailgun dashboard (Settings > API Security > HTTP Webhook Signing Key)
6. **Set Heroku config vars**:
   ```bash
   heroku config:set MAILGUN_SIGNING_KEY=your-signing-key --app your-app
   heroku config:set MAILGUN_DOMAIN=inbound.yourdomain.com --app your-app  # optional
   ```

Note: Mailgun expects HTTP 200 for success; 406 rejects the message; other codes trigger retries.

## Testing

- Unit tests cover HTML parsing, plus-tag detection, and Mailgun signature verification.
- Integration tests cover the Mailgun webhook endpoint using FastAPI TestClient with mocked RabbitMQ.

Run:
```bash
pytest -q
```

## Webhook Contract

### Mailgun Endpoint
- `POST /webhooks/mailgun`
  - Headers: `Content-Type: application/x-www-form-urlencoded` or `multipart/form-data`
  - Body: Form fields including `recipient`, `body-html`, `message-headers`, `timestamp`, `token`, `signature`
  - Response: `200 OK` with `{ "status": "enqueued", "message_id": "..." }`
  - Security: HMAC-SHA256 signature verification when `MAILGUN_SIGNING_KEY` is set

## Notes
- Default open simulation uses direct `img` fetches; enable headless path only if required.
- Attachments are ignored; payload size should be limited upstream.
- Workers acknowledge messages after successful processing; failed messages are requeued for retry.

For full details, see `docs/email-simulator-prd.md`.
