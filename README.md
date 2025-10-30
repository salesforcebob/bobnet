# BobNet Email Simulator

Simulates customer behavior (opens and clicks) on inbound marketing emails delivered via CloudMailIn. Runs on Heroku with a `web` dyno (FastAPI webhook) and a `worker` dyno (RQ).

[Deploy to Heroku](https://heroku.com/deploy)

## Features
- Receives CloudMailIn JSON webhook and enqueues jobs
- Randomized open simulation via direct pixel fetch (default)
- Randomized click simulation with domain allow/deny filters
- Idempotency by message-id (Redis NX key)
- Structured JSON logging

## CloudMailIn Reference
- Heroku Dev Center — Receiving Email with Heroku: https://devcenter.heroku.com/articles/cloudmailin#receiving-email-with-heroku

## Project Layout
```
app/
  web.py                 # FastAPI app (webhook + health)
  worker.py              # RQ worker job
  config.py              # Env configuration
  logging.py             # JSON logging
  models.py              # Pydantic models
  queue.py               # Redis + RQ setup
  simulate/
    html_parse.py        # HTML parsing helpers
    openers.py           # Open simulation (direct)
    clickers.py          # Click selection + execution
  utils/
    idempotency.py       # Redis NX TTL helper
    user_agents.py       # UA rotation
```

## Configuration
Environment variables:
- `CLOUDMAILIN_FORWARD_ADDRESS` (required): `c96be77c591e99f5c6bf@cloudmailin.net`
- `WEBHOOK_SECRET` (optional): shared secret header `X-Webhook-Secret`
- `REDIS_URL`: provided by Heroku Redis
- `SIMULATE_WITH_BROWSER` (default `false`): optional headless path (not enabled by default)
- `SIMULATE_OPEN_PROBABILITY` (default `0.7`)
- `SIMULATE_CLICK_PROBABILITY` (default `0.3`)
- `MAX_CLICKS` (default `2`)
- `OPEN_DELAY_RANGE_MS` (default `500,5000`)
- `CLICK_DELAY_RANGE_MS` (default `300,4000`)
- `REQUEST_TIMEOUT_MS` (default `8000`)

## Local Development
1. Python 3.11+
2. Redis (e.g., `docker run -p 6379:6379 redis:7`)
3. Create `.env` (or export env vars)
4. Install deps: `pip install -r requirements.txt`
5. Run web: `uvicorn app.web:app --reload --port 8000`
6. Run worker: `rq worker --url $REDIS_URL email_simulator`

Webhook endpoint: `POST http://localhost:8000/webhooks/cloudmailin`

## Heroku Deployment
This repo includes:
- `Procfile` (web + worker)
- `runtime.txt` (Python)
- `app.json` (one-click deploy + addons)

Using the one-click button opens Heroku’s deploy UI pre-configured with:
- Add-ons: CloudMailIn (`cloudmailin:starter`) and Heroku Redis (`hobby-dev`)
- Buildpack: heroku/python
- Formation: 1× web, 1× worker

To manually deploy:
```bash
heroku git:remote -a bob-net
heroku buildpacks:add heroku/python
# Ensure addons exist:
# heroku addons:create cloudmailin:starter --app bob-net --target=https://bob-net.herokuapp.com/webhooks/cloudmailin
# heroku addons:create heroku-redis:hobby-dev --app bob-net
# Set config vars as needed
# Push code (main is auto-deployed in your setup)
```

## Testing
- Unit tests cover HTML parsing, plus-tag detection, idempotency.
- Integration tests cover webhook enqueue using FastAPI TestClient and a running Redis.

Run (requires Redis):
```bash
pytest -q
```

## Webhook Contract
- `POST /webhooks/cloudmailin`
  - Headers: `Content-Type: application/json`, optional `X-Webhook-Secret`
  - Body: CloudMailIn JSON (subset used: `headers.message_id`, `envelope.to`, `html`)
  - Response: `202 Accepted` with `{ "status": "enqueued", "message_id": "...", "job_id": "..." }`

## Notes
- Default open simulation uses direct `img` fetches; enable headless path only if required.
- Attachments are ignored; payload size should be limited upstream.

For full details, see `docs/email-simulator-prd.md`.
