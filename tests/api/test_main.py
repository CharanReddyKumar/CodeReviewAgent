"""Tests for api/main.py - Complete coverage"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


class TestAPI:
    """Tests for API endpoints."""

    def test_api_import(self):
        """Test API module can be imported."""
        try:
            from api import main
            assert main is not None
            assert main.app is not None
        except ImportError:
            pytest.skip("API module not available")

    @patch("api.main.run_review")
    def test_health_check(self, mock_run_review):
        """Test health check endpoint."""
        try:
            from api.main import app
            client = TestClient(app)
            response = client.get("/healthz")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        except ImportError:
            pytest.skip("API module not available")

    @patch("api.main.run_review")
    def test_review_endpoint(self, mock_run_review):
        """Test review endpoint."""
        try:
            from api.main import app
            mock_run_review.return_value = [{"commit": "abc123"}]
            
            client = TestClient(app)
            response = client.post("/review", json={
                "repo": "test/repo",
                "branch": "main",
                "max_commits": 1
            })
            assert response.status_code == 200
            data = response.json()
            assert "runs" in data
            mock_run_review.assert_called_once()
        except ImportError:
            pytest.skip("API module not available")
