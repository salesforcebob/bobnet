# BobNet Email Simulator

Simulates customer behavior (opens and clicks) on inbound marketing emails. Runs on Heroku with a `web` dyno (FastAPI webhook) and a `worker` dyno (RabbitMQ consumer).

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/salesforcebob/bobnet)

Just name it. Defaults are good.

## Features
- **Cost-efficient inbound email processing via Cloudflare** (free tier available, Workers-based)
- Randomized open simulation via direct pixel fetch (default)
  - Prioritizes ExactTarget/Salesforce Marketing Cloud open pixels (`cl.s4.exct.net/open.aspx`)
  - Falls back to fetching other image resources in the email
- Randomized click simulation with domain allow/deny filters
- Message queue via **RabbitMQ** (CloudAMQP)
- Structured JSON logging with detailed open/click tracking
- Custom auth header verification for Cloudflare webhooks
- **Alternative**: Mailgun support (paid plan required)

## Quick Start (Cloudflare - Recommended)

1. Set up Cloudflare Email Routing (see [Cloudflare Setup](#cloudflare-setup) below)
2. Create a Cloudflare Worker to forward emails to your Heroku app
3. Set up CloudAMQP (see [CloudAMQP Setup](#cloudamqp-setup) below)
4. Deploy to Heroku and set environment variables
5. Configure your Cloudflare Worker with your Heroku app URL

**Why Cloudflare?** Free tier available, no per-email costs, scalable infrastructure, and simple setup.

## Provider References
- **Cloudflare**: [Email Routing](https://developers.cloudflare.com/email-routing/)
- **CloudAMQP**: [Getting Started](https://www.cloudamqp.com/docs/index.html)
- **Mailgun** (alternative): [Inbound Email Routing](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/routes)

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
    email_parse.py       # Raw email parsing (for Cloudflare)
    mailgun_signature.py # Mailgun HMAC signature verification
    user_agents.py       # UA rotation
rust-worker/             # High-performance Rust worker (optional)
  src/
    main.rs              # Entry point
    config.rs            # Env configuration
    consumer.rs          # RabbitMQ consumer (lapin)
    processor.rs         # Job processing logic
    html/                # HTML parsing (scraper)
    simulate/            # Open/click simulation (reqwest)
    util/                # User agent rotation
```

## Configuration

### Required Settings

- `CLOUDAMQP_URL`: RabbitMQ connection URL from CloudAMQP (format: `amqps://user:pass@host/vhost`)

### Cloudflare Settings (Primary)

- `CLOUDFLARE_AUTH_TOKEN` (recommended): Custom auth token for Cloudflare webhook. The `X-Custom-Auth` header in the webhook request must match this value. If not set, requests without the header will be accepted (not recommended for production).

### Mailgun Settings (Alternative)

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

### HTML-Based Overrides

You can override simulation probabilities on a per-email basis by including special HTML attributes in your email content. These overrides take precedence over environment variable settings.

#### Global Overrides (Single Div - Recommended)

You can combine both open and click rate overrides in a single `<div>` with `data-scope="global"`:

```html
<div data-scope="global" data-open-rate="0.9" data-click-rate="0.5">
</div>
```

**Example:** This sets 90% open rate and 50% click rate for the entire email, overriding the `SIMULATE_OPEN_PROBABILITY` and `SIMULATE_CLICK_PROBABILITY` environment variables.

#### Separate Overrides (Optional)

If you prefer, you can also use separate divs for each override:

```html
<!-- Open rate override -->
<div data-scope="global" data-open-rate="0.9">
</div>

<!-- Click rate override -->
<div data-scope="global" data-click-rate="0.5">
</div>
```

**Note:** If multiple `<div data-scope="global">` elements exist, both functions will use the first one that contains their respective attribute. Using a single combined div is recommended for clarity.

#### Per-Link Click Rate Override

You can also set individual click rates on specific links using the `data-click-rate` attribute:

```html
<a href="https://example.com/important" data-click-rate="0.8">Important Link</a>
<a href="https://example.com/regular" data-click-rate="0.2">Regular Link</a>
```

**Behavior:**
- Links with `data-click-rate` use their individual rate
- Links without `data-click-rate` use the global click rate (from `data-scope="global"` or `SIMULATE_CLICK_PROBABILITY`)
- Link selection uses weighted random selection based on these rates

#### Override Rules

1. **Value Range:** All rate values are clamped to `0.0` - `1.0` (values below 0 become 0.0, values above 1.0 become 1.0)
2. **Combined Attributes:** Both `data-open-rate` and `data-click-rate` can be in the same `<div data-scope="global">` element - this is the recommended approach
3. **Multiple Global Divs:** If multiple `<div data-scope="global">` elements are found, both functions will use the first div that contains their respective attribute (a warning is logged if multiple divs exist)

## Local Development

1. Python 3.11+ (version managed via `.python-version`, currently `3.11`)
2. RabbitMQ (e.g., `docker run -p 5672:5672 rabbitmq:3`)
3. Create `.env` with `CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/`
4. Install deps: `pip install -r requirements.txt`
5. Run web: `uvicorn app.web:app --reload --port 8000`
6. Run worker: `python -m app.worker_entry`

Webhook endpoints:
- Cloudflare: `POST http://localhost:8000/webhooks/cloudflare` (JSON) - **Recommended**
- Mailgun: `POST http://localhost:8000/webhooks/mailgun` (form-encoded) - Alternative

## Heroku Deployment

This repo includes:
- `Procfile` (web + worker)
- `.python-version` (Python major version)
- `app.json` (one-click deploy)

Using the one-click button opens Heroku's deploy UI pre-configured with:
- Buildpack: heroku/python
- Formation: 1× web, 1× worker

### Cloudflare Setup (Recommended - Cost-Efficient)

Cloudflare Email Workers provide a cost-effective way to receive inbound emails with no per-email charges on the free tier.

1. **Set up Cloudflare Email Routing**:
   - Sign up for a free Cloudflare account at [cloudflare.com](https://www.cloudflare.com)
   - Add your domain to Cloudflare
   - Navigate to Email > Email Routing in your Cloudflare dashboard
   - Configure your domain's MX records (Cloudflare provides the values)
   - Enable Email Routing

2. **Create a Cloudflare Worker** to forward emails to your Heroku app:
   - Go to Workers & Pages in your Cloudflare dashboard
   - Create a new Worker
   - Use the following code:
   ```javascript
   export default {
     async email(message, env, ctx) {
       const WEBHOOK_URL = "https://<your-app>.herokuapp.com/webhooks/cloudflare";
       const AUTH_TOKEN = "your-secure-token-here";  // Use a strong random token
       
       const payload = {
         from: message.from,
         to: message.to,
         subject: message.headers.get("subject"),
         timestamp: new Date().toISOString(),
         raw_content: await new Response(message.raw).text()
       };
       
       await fetch(WEBHOOK_URL, {
         method: "POST",
         headers: {
           "Content-Type": "application/json",
           "X-Custom-Auth": AUTH_TOKEN
         },
         body: JSON.stringify(payload),
       });
     }
   }
   ```
   - Deploy the Worker
   - Configure Email Routing to send emails to this Worker

3. **Set Heroku config vars**:
   ```bash
   heroku config:set CLOUDFLARE_AUTH_TOKEN=your-secure-token-here --app your-app
   heroku config:set CLOUDAMQP_URL=amqps://user:pass@host/vhost --app your-app
   ```

**Benefits of Cloudflare:**
- ✅ Free tier available (100,000 requests/day)
- ✅ No per-email costs
- ✅ Scalable infrastructure
- ✅ Simple setup with Email Routing
- ✅ Fast and reliable

The Cloudflare webhook endpoint parses raw RFC 5322 email content to extract HTML body and Message-Id headers before publishing to RabbitMQ.

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

### Mailgun Setup (Alternative - Paid)

Mailgun offers unlimited inbound emails on the Foundation plan ($35/month). Use this option if you prefer Mailgun's infrastructure or need features not available in Cloudflare.

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
- Integration tests cover both Cloudflare and Mailgun webhook endpoints using FastAPI TestClient with mocked RabbitMQ.

Run:
```bash
pytest -q
```

## Webhook Contract

### Cloudflare Endpoint (Primary)
- `POST /webhooks/cloudflare`
  - Headers: `Content-Type: application/json`, `X-Custom-Auth: <token>` (required if `CLOUDFLARE_AUTH_TOKEN` is set)
  - Body: JSON payload with `from`, `to`, `subject`, `timestamp`, `raw_content` (full RFC 5322 email)
  - Response: `200 OK` with `{ "status": "enqueued", "message_id": "..." }`
  - Security: Custom auth header verification (configurable via `CLOUDFLARE_AUTH_TOKEN`). If not set, requests without the header are accepted.

### Mailgun Endpoint (Alternative)
- `POST /webhooks/mailgun`
  - Headers: `Content-Type: application/x-www-form-urlencoded` or `multipart/form-data`
  - Body: Form fields including `recipient`, `body-html`, `message-headers`, `timestamp`, `token`, `signature`
  - Response: `200 OK` with `{ "status": "enqueued", "message_id": "..." }`
  - Security: HMAC-SHA256 signature verification when `MAILGUN_SIGNING_KEY` is set

## High-Performance Rust Worker (Optional)

For significantly higher throughput, you can use the Rust-based worker instead of the Python worker. The Rust worker uses Tokio for async processing and can handle hundreds of concurrent messages.

### Performance Comparison

| Worker | Throughput | Latency | Concurrency |
|--------|------------|---------|-------------|
| Python | ~0.11 items/sec | 9+ seconds/item | 1 (sequential) |
| Rust | 50-100+ items/sec | Sub-second/item | 100+ (concurrent) |

### Building the Rust Worker

```bash
# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build the release binary
cd rust-worker
cargo build --release
```

The binary will be at `./target/release/bobnet-worker`.

### Running Locally

```bash
# Set environment variables (same as Python worker)
export CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/

# Run the Rust worker
./target/release/bobnet-worker
```

### Rust Worker Configuration

The Rust worker uses the same environment variables as the Python worker, plus:

- `WORKER_CONCURRENCY` (default `100`): Maximum number of concurrent job processors

### Heroku Deployment with Rust

To deploy the Rust worker on Heroku:

1. Add the Rust buildpack:
   ```bash
   heroku buildpacks:add emk/rust --app your-app
   ```

2. Scale the `rust-worker` dyno:
   ```bash
   heroku ps:scale rust-worker=1 worker=0 --app your-app
   ```

The `Procfile` includes both worker types:
- `worker`: Python worker (sequential processing)
- `rust-worker`: Rust worker (concurrent processing)

### Rust Worker Features

- **Async/concurrent processing**: Uses Tokio runtime for non-blocking I/O
- **High prefetch**: Fetches up to 100 messages at a time from RabbitMQ
- **Connection pooling**: Reuses HTTP connections for efficiency
- **Graceful shutdown**: Handles SIGINT/SIGTERM for clean exits
- **Identical behavior**: Same simulation logic as Python worker

## Notes
- Default open simulation uses direct `img` fetches; enable headless path only if required.
- Open simulation prioritizes ExactTarget/Salesforce Marketing Cloud open pixels (`cl.s4.exct.net/open.aspx`) when present in the email HTML.
- Attachments are ignored; payload size should be limited upstream.
- Workers acknowledge messages after successful processing; failed messages are requeued for retry.
- Comprehensive structured logging is available for debugging open/click simulation behavior, including probability checks, pixel detection, and fetch results.

For full details, see `docs/email-simulator-prd.md`.
