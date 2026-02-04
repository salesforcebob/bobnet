# BobNet Email Simulator

High-performance email simulation system that simulates customer behavior (opens and clicks) on inbound marketing emails. Built in **Rust** for maximum throughput and efficiency.

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/salesforcebob/bobnet)

Just name it. Defaults are good.

## Architecture

```
Webhooks → Rust Web Server → inbound_webhooks → Rust Processor → email_simulator → Rust Worker
                (auth + enqueue)       (queue)        (parse)          (queue)       (simulate)
```

The system uses a **two-queue architecture** for maximum webhook throughput:

1. **Web Server** (`bobnet-web`): Thin, fast Axum server that authenticates and immediately enqueues raw webhook payloads
2. **Processor** (`bobnet-processor`): Background process that parses webhooks and prepares simulation jobs
3. **Worker** (`bobnet-worker`): Email simulator that performs opens and clicks

## Features
- **Cost-efficient inbound email processing via Cloudflare** (free tier available, Workers-based)
- **High-throughput webhook reception** - web server responds in microseconds
- Randomized open simulation via direct pixel fetch (default)
  - Prioritizes ExactTarget/Salesforce Marketing Cloud open pixels (`cl.s4.exct.net/open.aspx`)
  - Falls back to fetching other image resources in the email
- Randomized click simulation with domain allow/deny filters
- **Two-queue RabbitMQ architecture** for burst handling (CloudAMQP)
- Structured JSON logging with detailed open/click tracking
- Custom auth header verification for Cloudflare webhooks
- HMAC-SHA256 signature verification for Mailgun webhooks
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
rust-worker/             # All Rust binaries (web, processor, worker)
  Cargo.toml             # Package with 3 binaries
  src/
    lib.rs               # Shared library
    main.rs              # Worker binary entry point
    bin/
      web.rs             # Web server binary
      processor.rs       # Processor binary
    config.rs            # Env configuration
    consumer.rs          # RabbitMQ consumer (lapin)
    processor.rs         # Job processing logic
    queue/               # Queue types and publisher
      mod.rs
      types.rs           # InboundWebhook, SimulatorJob
      publisher.rs       # Async RabbitMQ publisher
    process/             # Webhook processing
      mod.rs
      email_parser.rs    # RFC 5322 parsing (mailparse)
      mailgun.rs         # Mailgun payload processing
      cloudflare.rs      # Cloudflare payload processing
    web/                 # Web server handlers
      mod.rs
      handlers.rs        # Endpoint handlers
      signature.rs       # HMAC signature verification
    html/                # HTML parsing (scraper)
    simulate/            # Open/click simulation (reqwest)
    util/                # User agent rotation
app/                     # Legacy Python code (deprecated)
  web.py                 # FastAPI app (webhooks + health)
  worker.py              # Job processing logic
  ...
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

#### Unsubscribe Link Filtering

**ExactTarget unsubscribe links are automatically excluded from click simulation** unless they have an explicit `data-click-rate` override.

Unsubscribe links matching the pattern `https://cl.S4.exct.net/unsub_center.aspx` (case-insensitive) will be filtered out during link selection to prevent accidental unsubscribes.

**To allow clicking an unsubscribe link**, add a `data-click-rate` attribute:

```html
<a href="https://cl.S4.exct.net/unsub_center.aspx?email=test@example.com" data-click-rate="0.1">
  Unsubscribe
</a>
```

**Behavior:**
- Unsubscribe links **without** `data-click-rate` are **never clicked** (filtered out)
- Unsubscribe links **with** `data-click-rate` are **eligible for clicking** based on their rate
- This protection applies regardless of global click rate settings or domain allow/deny lists

## Local Development

### Quick Start (Rust)

1. Install Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
2. Start RabbitMQ: `docker run -p 5672:5672 rabbitmq:3`
3. Set environment: `export CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/`
4. Build: `cargo build --release`
5. Run (in separate terminals):
   ```bash
   ./target/release/bobnet-web
   ./target/release/bobnet-processor
   ./target/release/bobnet-worker
   ```

### Legacy Python (Deprecated)

1. Python 3.11+ (version managed via `.python-version`)
2. Install deps: `pip install -r requirements.txt`
3. Run web: `uvicorn app.web:app --reload --port 8000`
4. Run worker: `python -m app.worker_entry`

### Webhook Endpoints

- Cloudflare: `POST http://localhost:8080/webhooks/cloudflare` (JSON) - **Recommended**
- Mailgun: `POST http://localhost:8080/webhooks/mailgun` (form-encoded) - Alternative

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

## Rust Components

The entire system is built in Rust for maximum throughput and efficiency. All three components use Tokio for async processing.

### Performance

| Component | Throughput | Latency |
|-----------|------------|---------|
| Web Server | 10,000+ req/sec | Sub-millisecond |
| Processor | 5,000+ msg/sec | ~1ms per message |
| Worker | 100+ items/sec | Variable (network-bound) |

### Building

```bash
# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build all binaries
cargo build --release
```

Binaries will be at `./target/release/`:
- `bobnet-web` - Web server
- `bobnet-processor` - Webhook processor
- `bobnet-worker` - Email simulator

### Running Locally

```bash
# Set environment variables
export CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/
export PORT=8080
export CLOUDFLARE_AUTH_TOKEN=your-token  # optional

# Run all three (in separate terminals)
./target/release/bobnet-web
./target/release/bobnet-processor
./target/release/bobnet-worker
```

### Configuration

All components share these environment variables:

- `CLOUDAMQP_URL`: RabbitMQ connection URL (required)
- `WORKER_CONCURRENCY` (default `100`): Max concurrent processors

**Web Server:**
- `PORT` (default `8080`): HTTP port to listen on
- `CLOUDFLARE_AUTH_TOKEN`: Token for X-Custom-Auth header verification
- `MAILGUN_SIGNING_KEY`: Key for HMAC signature verification
- `MAILGUN_DOMAIN`: Optional domain for recipient validation

**Worker:**
- `SIMULATE_OPEN_PROBABILITY` (default `0.7`)
- `SIMULATE_CLICK_PROBABILITY` (default `0.3`)
- `MAX_CLICKS` (default `2`)
- `OPEN_DELAY_RANGE_MS` (default `500,5000`)
- `CLICK_DELAY_RANGE_MS` (default `300,4000`)

### Heroku Deployment

1. Add the Rust buildpack:
   ```bash
   heroku buildpacks:add emk/rust --app your-app
   ```

2. Scale the dynos:
   ```bash
   heroku ps:scale web=1 processor=1 rust-worker=1 --app your-app
   ```

The `Procfile` defines:
- `web`: Rust web server (receives webhooks)
- `processor`: Rust processor (parses webhooks)
- `rust-worker`: Rust worker (simulates opens/clicks)

### Component Features

**Web Server (`bobnet-web`):**
- Axum-based HTTP server
- HMAC-SHA256 signature verification for Mailgun
- Custom header verification for Cloudflare
- Immediate queue publishing (no parsing in request path)
- Graceful shutdown on SIGINT/SIGTERM

**Processor (`bobnet-processor`):**
- Consumes from `inbound_webhooks` queue
- RFC 5322 email parsing using `mailparse`
- Message-Id extraction and fallback generation
- Publishes to `email_simulator` queue
- Concurrent message processing

**Worker (`bobnet-worker`):**
- Consumes from `email_simulator` queue
- Opens: Fetches tracking pixels (prioritizes ExactTarget)
- Clicks: Weighted link selection with domain filtering
- User agent rotation
- Connection pooling via reqwest

## Notes

### Architecture
- **Two-queue system**: `inbound_webhooks` (raw payloads) and `email_simulator` (parsed jobs)
- Web server enqueues immediately, parsing happens asynchronously in the processor
- This allows handling massive webhook bursts without backpressure

### Simulation
- Default open simulation uses direct `img` fetches; enable headless path only if required
- Open simulation prioritizes ExactTarget/Salesforce Marketing Cloud open pixels (`cl.s4.exct.net/open.aspx`)
- Attachments are ignored; payload size should be limited upstream

### Reliability
- Messages are acknowledged after successful processing
- Parse failures in the processor are logged but not requeued (malformed data)
- Simulation failures in the worker are requeued for retry
- Graceful shutdown ensures in-flight messages complete

### Logging
- Comprehensive structured JSON logging
- All components log message flow with correlation IDs
- Probability checks, pixel detection, and fetch results are logged

For full details, see `docs/email-simulator-prd.md`.
