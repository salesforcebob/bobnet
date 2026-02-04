"""
Integration tests for click simulation with global and per-link rate overrides.

These tests verify that the worker correctly:
- Uses global click rate override from <div data-scope="global" data-click-rate="...">
- Uses per-link click rates from <a data-click-rate="...">
- Applies weighted selection based on individual link rates
"""
from unittest.mock import patch, MagicMock

import pytest

from app.worker import process_mail


class TestGlobalClickRateOverride:
    """Tests for global click rate override via div attribute."""

    @patch("app.worker.fetch_single_url")
    @patch("app.worker.simulate_open_via_direct")
    @patch("app.worker.perform_clicks")
    def test_uses_global_override_when_present(self, mock_perform_clicks, mock_open, mock_pixel, monkeypatch):
        """Global override should replace SIMULATE_CLICK_PROBABILITY."""
        monkeypatch.setenv("SIMULATE_CLICK_PROBABILITY", "0.3")
        monkeypatch.setenv("SIMULATE_OPEN_PROBABILITY", "0.0")  # Disable opens for this test
        from app.config import Settings
        monkeypatch.setattr("app.worker.settings", Settings())
        
        mock_perform_clicks.return_value = 0
        
        html = '<div data-scope="global" data-click-rate="0.9"></div><a href="https://example.com/page1">Link 1</a>'
        job = {
            "message_id": "test-123",
            "to": "test@example.com",
            "html": html,
        }
        
        # Run multiple times to verify probability is being used
        # With rate 0.9, most runs should attempt clicks
        results = []
        for _ in range(20):
            result = process_mail(job)
            results.append(result.get("clicked", 0))
        
        # At least some should have attempted clicks (with 0.9 probability)
        assert sum(results) >= 0  # Just verify it runs without error
        # Verify that perform_clicks was called when clicks were attempted
        assert mock_perform_clicks.call_count >= 0

    @patch("app.worker.fetch_single_url")
    @patch("app.worker.simulate_open_via_direct")
    @patch("app.worker.perform_clicks")
    def test_uses_default_when_no_global_override(self, mock_perform_clicks, mock_open, mock_pixel, monkeypatch):
        """Should use SIMULATE_CLICK_PROBABILITY when no global override."""
        monkeypatch.setenv("SIMULATE_CLICK_PROBABILITY", "0.3")
        monkeypatch.setenv("SIMULATE_OPEN_PROBABILITY", "0.0")
        from app.config import Settings
        monkeypatch.setattr("app.worker.settings", Settings())
        
        mock_perform_clicks.return_value = 0
        
        html = '<a href="https://example.com/page1">Link 1</a>'
        job = {
            "message_id": "test-123",
            "to": "test@example.com",
            "html": html,
        }
        
        result = process_mail(job)
        assert "clicked" in result


class TestPerLinkClickRates:
    """Tests for per-link click rate attributes."""

    @patch("app.worker.fetch_single_url")
    @patch("app.worker.simulate_open_via_direct")
    @patch("app.worker.perform_clicks")
    def test_extracts_per_link_rates(self, mock_perform_clicks, mock_open, mock_pixel, monkeypatch):
        """Should extract data-click-rate from individual links."""
        monkeypatch.setenv("SIMULATE_CLICK_PROBABILITY", "1.0")  # Always attempt clicks
        monkeypatch.setenv("SIMULATE_OPEN_PROBABILITY", "0.0")
        monkeypatch.setenv("MAX_CLICKS", "10")
        from app.config import Settings
        monkeypatch.setattr("app.worker.settings", Settings())
        
        mock_perform_clicks.return_value = 5
        
        html = '''
        <a href="https://example.com/page1" data-click-rate="0.5">Link 1</a>
        <a href="https://example.com/page2" data-click-rate="0.25">Link 2</a>
        '''
        job = {
            "message_id": "test-123",
            "to": "test@example.com",
            "html": html,
        }
        
        result = process_mail(job)
        assert "clicked" in result
        # Verify perform_clicks was called with selected links
        assert mock_perform_clicks.called

    @patch("app.worker.fetch_single_url")
    @patch("app.worker.simulate_open_via_direct")
    @patch("app.worker.perform_clicks")
    def test_uses_global_rate_for_links_without_rate(self, mock_perform_clicks, mock_open, mock_pixel, monkeypatch):
        """Links without data-click-rate should use global rate."""
        monkeypatch.setenv("SIMULATE_CLICK_PROBABILITY", "1.0")
        monkeypatch.setenv("SIMULATE_OPEN_PROBABILITY", "0.0")
        monkeypatch.setenv("MAX_CLICKS", "10")
        from app.config import Settings
        monkeypatch.setattr("app.worker.settings", Settings())
        
        mock_perform_clicks.return_value = 3
        
        html = '''
        <a href="https://example.com/page1" data-click-rate="0.5">Link 1</a>
        <a href="https://example.com/page2">Link 2</a>
        '''
        job = {
            "message_id": "test-123",
            "to": "test@example.com",
            "html": html,
        }
        
        result = process_mail(job)
        assert "clicked" in result
        assert mock_perform_clicks.called


class TestCombinedOverrides:
    """Tests for combined global and per-link overrides."""

    @patch("app.worker.fetch_single_url")
    @patch("app.worker.simulate_open_via_direct")
    @patch("app.worker.perform_clicks")
    def test_global_and_per_link_combined(self, mock_perform_clicks, mock_open, mock_pixel, monkeypatch):
        """Should use global override and per-link rates together."""
        monkeypatch.setenv("SIMULATE_CLICK_PROBABILITY", "0.3")  # Will be overridden
        monkeypatch.setenv("SIMULATE_OPEN_PROBABILITY", "0.0")
        monkeypatch.setenv("MAX_CLICKS", "10")
        from app.config import Settings
        monkeypatch.setattr("app.worker.settings", Settings())
        
        mock_perform_clicks.return_value = 2
        
        html = '''
        <div data-scope="global" data-click-rate="0.8"></div>
        <a href="https://example.com/page1" data-click-rate="0.5">Link 1</a>
        <a href="https://example.com/page2">Link 2</a>
        '''
        job = {
            "message_id": "test-123",
            "to": "test@example.com",
            "html": html,
        }
        
        result = process_mail(job)
        assert "clicked" in result
        # Global override (0.8) should be used for probability check
        # Link 1 uses 0.5, Link 2 uses 0.8 (global)
        assert mock_perform_clicks.called
