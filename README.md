# BobNet Email Simulator

Simulates customer behavior (opens and clicks) on inbound marketing emails. Runs on Heroku with a `web` dyno (FastAPI webhook) and a `worker` dyno (RQ).

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/salesforcebob/bobnet)

Just name it. Defaults are good.

## Features
- Dual inbound email provider support: **CloudMailIn** and **Mailgun**
- Randomized open simulation via direct pixel fetch (default)
- Randomized click simulation with domain allow/deny filters
- Idempotency by message-id (Redis NX key)
- Structured JSON logging
- HMAC signature verification for Mailgun webhooks

## Inbound Email Providers

This app supports two inbound email providers that can run simultaneously:

| Provider | Webhook Endpoint | Payload Format | Best For |
|----------|-----------------|----------------|----------|
| CloudMailIn | `/webhooks/cloudmailin` | JSON | Heroku add-on convenience |
| Mailgun | `/webhooks/mailgun` | Form-encoded | High volume (unlimited inbound) |

Both endpoints normalize payloads to the same internal format, so the worker processes them identically.

## Quick Start

### Option A: CloudMailIn (Heroku Add-on)
1. After installing, check your Heroku Config Vars to get `CLOUDMAILIN_FORWARD_ADDRESS` (e.g., `12345566@cloudmailin.net`)
2. Use plus-addressing for variations: `12345566+bobisanerd@cloudmailin.net`

### Option B: Mailgun (Recommended for High Volume)
1. Sign up for Mailgun Foundation plan ($35/month, unlimited inbound emails)
2. Add your domain and configure MX records (see [Mailgun Setup](#mailgun-setup) below)
3. Create an inbound route pointing to `https://<your-app>.herokuapp.com/webhooks/mailgun`
4. Set `MAILGUN_SIGNING_KEY` and optionally `MAILGUN_DOMAIN` in Heroku config vars

## Provider References
- **CloudMailIn**: [Heroku Dev Center — Receiving Email](https://devcenter.heroku.com/articles/cloudmailin#receiving-email-with-heroku)
- **Mailgun**: [Inbound Email Routing](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/routes)

## Project Layout
```
app/
  web.py                 # FastAPI app (webhooks + health)
  worker.py              # RQ worker job
  worker_entry.py        # Worker entrypoint (uses configured Redis w/ SSL settings)
  config.py              # Env configuration
  logging.py             # JSON logging
  models.py              # Pydantic models (CloudMailIn + Mailgun)
  queue.py               # Redis + RQ setup
  simulate/
    html_parse.py        # HTML parsing helpers
    openers.py           # Open simulation (direct)
    clickers.py          # Click selection + execution
  utils/
    idempotency.py       # Redis NX TTL helper
    mailgun_signature.py # Mailgun HMAC signature verification
    user_agents.py       # UA rotation
```

## Configuration (Automated)
* Envs can be adjusted via the installer or the Heroku Dashboard after deployment

### Inbound Email Provider Settings

**CloudMailIn** (Heroku add-on):
- `CLOUDMAILIN_FORWARD_ADDRESS`: Your CloudMailIn address (e.g., `xxxxxx@cloudmailin.net`)
- `WEBHOOK_SECRET` (optional): Shared secret for `X-Webhook-Secret` header

**Mailgun** (external provider):
- `MAILGUN_SIGNING_KEY` (recommended): HTTP webhook signing key from Mailgun dashboard (Settings > API Security)
- `MAILGUN_DOMAIN` (optional): Restrict accepted recipients to this domain (e.g., `inbound.example.com`)

### General Settings

- `REDIS` or `REDIS_URL`: Redis connection URL (Heroku Key-Value Store uses `REDIS_URL`)
- `REDIS_SSL_CERT_REQS` (default `none`): Redis TLS cert verification mode; set to `required` if your provider presents a trusted chain
- `SIMULATE_WITH_BROWSER` (default `false`): optional headless path (not enabled by default)
- `SIMULATE_OPEN_PROBABILITY` (default `0.7`)
- `SIMULATE_CLICK_PROBABILITY` (default `0.3`)
- `MAX_CLICKS` (default `2`)
- `OPEN_DELAY_RANGE_MS` (default `500,5000`)
- `CLICK_DELAY_RANGE_MS` (default `300,4000`)
- `REQUEST_TIMEOUT_MS` (default `8000`)

## Local Development
1. Python 3.11+ (version managed via `.python-version`, currently `3.11`)
2. Redis (e.g., `docker run -p 6379:6379 redis:7`)
3. Create `.env` (or export env vars)
4. Install deps: `pip install -r requirements.txt`
5. Run web: `uvicorn app.web:app --reload --port 8000`
6. Run worker: `python -m app.worker_entry`

Webhook endpoints:
- CloudMailIn: `POST http://localhost:8000/webhooks/cloudmailin` (JSON)
- Mailgun: `POST http://localhost:8000/webhooks/mailgun` (form-encoded)

## Heroku Deployment
This repo includes:
- `Procfile` (web + worker)
- `.python-version` (Python major version)
- `app.json` (one-click deploy + addons)

Using the one-click button opens Heroku’s deploy UI pre-configured with:
- Add-ons: CloudMailIn (`cloudmailin:starter`) and Heroku Redis / Key-Value Store
- Buildpack: heroku/python
- Formation: 1× web, 1× worker

To manually deploy:
```bash
heroku git:remote -a bob-net
heroku buildpacks:add heroku/python
# Ensure addons exist
# heroku addons:create cloudmailin:starter --app bob-net --target=https://bob-net.herokuapp.com/webhooks/cloudmailin
# heroku addons:create heroku-redis:hobby-dev --app bob-net
# If you encounter Redis TLS certificate verification issues, set:
# heroku config:set REDIS_SSL_CERT_REQS=none --app bob-net
# Push code (main is auto-deployed in your setup)
```

### CloudMailIn Target Setup
1. In your Heroku app, open the Resources tab and click the CloudMailIn add-on.
2. In the CloudMailIn dashboard, under "Receive Email", locate your email address row and click "Manage".
3. Click the "Edit Target" button.
4. Set the target to your app’s webhook URL, for example:
   - `https://<your-app>.herokuapp.com/webhooks/cloudmailin`
   - or your custom domain equivalent
5. Choose JSON - Normalized (recommended) for the POST format
6. Save changes. Send a test email to `CLOUDMAILIN_FORWARD_ADDRESS` (or a plus-address variant) and verify a 202 response in app logs.

Note: CloudMailIn accepts messages on 2xx, bounces on 4xx, and retries on 5xx.

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
- Unit tests cover HTML parsing, plus-tag detection, idempotency, and Mailgun signature verification.
- Integration tests cover both CloudMailIn and Mailgun webhook endpoints using FastAPI TestClient and a running Redis.

Run (requires Redis):
```bash
pytest -q
```

## Webhook Contracts

### CloudMailIn Endpoint
- `POST /webhooks/cloudmailin`
  - Headers: `Content-Type: application/json`, optional `X-Webhook-Secret`
  - Body: CloudMailIn JSON (subset used: `headers.message_id`, `envelope.to`, `html`)
  - Response: `202 Accepted` with `{ "status": "enqueued", "message_id": "...", "job_id": "..." }`

### Mailgun Endpoint
- `POST /webhooks/mailgun`
  - Headers: `Content-Type: application/x-www-form-urlencoded` or `multipart/form-data`
  - Body: Form fields including `recipient`, `body-html`, `message-headers`, `timestamp`, `token`, `signature`
  - Response: `200 OK` with `{ "status": "enqueued", "message_id": "...", "job_id": "..." }`
  - Security: HMAC-SHA256 signature verification when `MAILGUN_SIGNING_KEY` is set

## Notes
- Default open simulation uses direct `img` fetches; enable headless path only if required.
- Attachments are ignored; payload size should be limited upstream.

For full details, see `docs/email-simulator-prd.md`.
