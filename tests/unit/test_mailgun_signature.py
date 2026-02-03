"""
Unit tests for Mailgun webhook signature verification.
"""
import hashlib
import hmac
import time

import pytest

from app.utils.mailgun_signature import (
    verify_mailgun_signature,
    is_signature_verification_enabled,
    SIGNATURE_MAX_AGE_SECONDS,
)


def _generate_signature(signing_key: str, timestamp: str, token: str) -> str:
    """Helper to generate a valid Mailgun signature for testing."""
    return hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


class TestVerifyMailgunSignature:
    """Tests for verify_mailgun_signature function."""

    def test_valid_signature_returns_true(self):
        """Valid signature with recent timestamp should return True."""
        signing_key = "test-signing-key-12345"
        timestamp = str(int(time.time()))
        token = "random-token-abcdef123456"
        signature = _generate_signature(signing_key, timestamp, token)

        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=timestamp,
            token=token,
            signature=signature,
        ) is True

    def test_invalid_signature_returns_false(self):
        """Invalid signature should return False."""
        signing_key = "test-signing-key-12345"
        timestamp = str(int(time.time()))
        token = "random-token-abcdef123456"
        invalid_signature = "invalid-signature-that-does-not-match"

        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=timestamp,
            token=token,
            signature=invalid_signature,
        ) is False

    def test_wrong_signing_key_returns_false(self):
        """Signature computed with different key should return False."""
        correct_key = "correct-signing-key"
        wrong_key = "wrong-signing-key"
        timestamp = str(int(time.time()))
        token = "random-token"
        signature = _generate_signature(correct_key, timestamp, token)

        assert verify_mailgun_signature(
            signing_key=wrong_key,
            timestamp=timestamp,
            token=token,
            signature=signature,
        ) is False

    def test_stale_timestamp_returns_false(self):
        """Timestamp older than max_age_seconds should return False."""
        signing_key = "test-signing-key"
        # Timestamp from 10 minutes ago
        old_timestamp = str(int(time.time()) - 600)
        token = "random-token"
        signature = _generate_signature(signing_key, old_timestamp, token)

        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=old_timestamp,
            token=token,
            signature=signature,
            max_age_seconds=SIGNATURE_MAX_AGE_SECONDS,  # 5 minutes
        ) is False

    def test_future_timestamp_within_max_age_returns_true(self):
        """Timestamp slightly in the future should still be valid."""
        signing_key = "test-signing-key"
        # 30 seconds in the future (clock skew tolerance)
        future_timestamp = str(int(time.time()) + 30)
        token = "random-token"
        signature = _generate_signature(signing_key, future_timestamp, token)

        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=future_timestamp,
            token=token,
            signature=signature,
        ) is True

    def test_empty_signing_key_returns_false(self):
        """Empty signing key should return False."""
        timestamp = str(int(time.time()))
        token = "random-token"

        assert verify_mailgun_signature(
            signing_key="",
            timestamp=timestamp,
            token=token,
            signature="any-signature",
        ) is False

    def test_empty_timestamp_returns_false(self):
        """Empty timestamp should return False."""
        assert verify_mailgun_signature(
            signing_key="test-key",
            timestamp="",
            token="token",
            signature="sig",
        ) is False

    def test_empty_token_returns_false(self):
        """Empty token should return False."""
        assert verify_mailgun_signature(
            signing_key="test-key",
            timestamp=str(int(time.time())),
            token="",
            signature="sig",
        ) is False

    def test_empty_signature_returns_false(self):
        """Empty signature should return False."""
        assert verify_mailgun_signature(
            signing_key="test-key",
            timestamp=str(int(time.time())),
            token="token",
            signature="",
        ) is False

    def test_non_numeric_timestamp_returns_false(self):
        """Non-numeric timestamp should return False."""
        assert verify_mailgun_signature(
            signing_key="test-key",
            timestamp="not-a-number",
            token="token",
            signature="sig",
        ) is False

    def test_custom_max_age_respected(self):
        """Custom max_age_seconds should be respected."""
        signing_key = "test-key"
        # 2 minutes ago
        timestamp = str(int(time.time()) - 120)
        token = "token"
        signature = _generate_signature(signing_key, timestamp, token)

        # Should fail with 60 second max age
        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=timestamp,
            token=token,
            signature=signature,
            max_age_seconds=60,
        ) is False

        # Should pass with 180 second max age
        assert verify_mailgun_signature(
            signing_key=signing_key,
            timestamp=timestamp,
            token=token,
            signature=signature,
            max_age_seconds=180,
        ) is True


class TestIsSignatureVerificationEnabled:
    """Tests for is_signature_verification_enabled function."""

    def test_with_valid_key_returns_true(self):
        """Non-empty signing key should return True."""
        assert is_signature_verification_enabled("my-signing-key") is True

    def test_with_empty_string_returns_false(self):
        """Empty string should return False."""
        assert is_signature_verification_enabled("") is False

    def test_with_none_returns_false(self):
        """None should return False."""
        assert is_signature_verification_enabled(None) is False

    def test_with_whitespace_only_returns_false(self):
        """Whitespace-only string should return False."""
        assert is_signature_verification_enabled("   ") is False
        assert is_signature_verification_enabled("\t\n") is False
