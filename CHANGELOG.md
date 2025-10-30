## [Unreleased]
### Added
- Initial Python service to simulate CloudMailIn email opens/clicks on Heroku
  - FastAPI webhook `/webhooks/cloudmailin`
  - RQ worker for simulation jobs
  - Direct open via image fetch; randomized clicks
  - Redis-backed idempotency
  - Heroku `Procfile`, `runtime.txt`, `app.json` (one-click deploy)
  - README with setup and deploy instructions
  - Initial tests (unit + integration)
