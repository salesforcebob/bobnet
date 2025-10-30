## [Unreleased]
### Added
- Initial Python service to simulate CloudMailIn email opens/clicks on Heroku
  - FastAPI webhook `/webhooks/cloudmailin`
  - RQ worker for simulation jobs
  - Direct open via image fetch; randomized clicks
  - Redis-backed idempotency
  - Heroku `Procfile`, `.python-version`, `app.json` (one-click deploy)
  - README with setup and deploy instructions
  - Initial tests (unit + integration)

### Changed
- Replaced deprecated `runtime.txt` with `.python-version` specifying `3.11` to receive latest patch updates automatically.
- Redis TLS: honor `REDIS_SSL_CERT_REQS` (default `none`) to handle self-signed certificate chains presented by some managed instances.
