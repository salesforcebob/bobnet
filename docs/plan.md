## Project Plan

### Current Focus
- Email behavior simulation via CloudMailIn on Heroku (Python background worker).

### Primary Specification
- See detailed PRD + Implementation Plan in `docs/email-simulator-prd.md`.

### High-Level Delivery Stages
1. Scaffold FastAPI webhook + RQ worker + Redis.
2. Implement direct open and click simulation (default).
3. Add optional Playwright headless path behind feature flag.
4. Add observability, idempotency, and configuration toggles.
5. E2E tests and Heroku deployment (web + worker dynos).
