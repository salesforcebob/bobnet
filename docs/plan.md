## Project Plan

### Current Focus
- Email behavior simulation via Mailgun inbound routing on Heroku (Python background worker).

### Architecture
- **Web dyno**: FastAPI webhook receiving Mailgun inbound emails
- **Worker dyno**: RabbitMQ consumer processing simulation jobs
- **Message queue**: CloudAMQP (RabbitMQ)
- **Inbound email**: Mailgun Foundation plan (unlimited inbound)

### Primary Specification
- See detailed PRD in `docs/email-simulator-prd.md` (note: originally written for CloudMailIn, now using Mailgun).

### Completed
1. Scaffold FastAPI webhook + RabbitMQ worker.
2. Implement direct open and click simulation (default).
3. Mailgun inbound email integration with signature verification.
4. Structured JSON logging.
5. Heroku deployment (web + worker dynos).

### Future Enhancements
1. Add optional Playwright headless path behind feature flag.
2. Dead letter queue handling for persistent failures.
3. Metrics and monitoring dashboards.
