import os
from typing import Tuple, Optional


def _parse_range(name: str, default: str) -> Tuple[int, int]:
    raw = os.getenv(name, default)
    try:
        parts = [int(p.strip()) for p in raw.split(",")]
        if len(parts) != 2 or parts[0] < 0 or parts[1] < parts[0]:
            raise ValueError
        return parts[0], parts[1]
    except Exception:
        # Fallback to default if malformed
        dparts = [int(p.strip()) for p in default.split(",")]
        return dparts[0], dparts[1]


def _csv(name: str) -> Optional[list[str]]:
    raw = os.getenv(name)
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


class Settings:
    # RabbitMQ connection (CloudAMQP)
    cloudamqp_url: str = os.getenv("CLOUDAMQP_URL", "amqp://guest:guest@localhost:5672/")

    # Mailgun settings (for /webhooks/mailgun endpoint)
    mailgun_signing_key: Optional[str] = os.getenv("MAILGUN_SIGNING_KEY")
    mailgun_domain: str = os.getenv("MAILGUN_DOMAIN", "")

    simulate_with_browser: bool = os.getenv("SIMULATE_WITH_BROWSER", "false").lower() == "true"
    simulate_open_probability: float = float(os.getenv("SIMULATE_OPEN_PROBABILITY", "0.7"))
    simulate_click_probability: float = float(os.getenv("SIMULATE_CLICK_PROBABILITY", "0.3"))
    max_clicks: int = int(os.getenv("MAX_CLICKS", "2"))

    open_delay_ms: Tuple[int, int] = _parse_range("OPEN_DELAY_RANGE_MS", "500,5000")
    click_delay_ms: Tuple[int, int] = _parse_range("CLICK_DELAY_RANGE_MS", "300,4000")

    user_agent_pool: Optional[list[str]] = _csv("USER_AGENT_POOL")
    allow_domains: Optional[list[str]] = _csv("LINK_DOMAIN_ALLOWLIST")
    deny_domains: Optional[list[str]] = _csv("LINK_DOMAIN_DENYLIST")

    request_timeout_ms: int = int(os.getenv("REQUEST_TIMEOUT_MS", "8000"))


settings = Settings()
