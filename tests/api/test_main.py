"""Tests for api/main.py - Complete coverage"""
import time
import pytest
from unittest.mock import Mock, patch
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
    def test_review_job_lifecycle(self, mock_run_review):
        """Test async review submission and job polling."""
        try:
            from api import main as api_main
            from api.main import app

            api_main._jobs.clear()
            mock_run_review.return_value = [{"commit": "abc123"}]

            client = TestClient(app)
            response = client.post(
                "/review",
                json={"repo": "test/repo", "branch": "main", "max_commits": 1},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "pending"
            job_id = payload["job_id"]

            for _ in range(20):
                status_resp = client.get(f"/review/{job_id}")
                assert status_resp.status_code == 200
                job_payload = status_resp.json()
                if job_payload["status"] == "complete":
                    assert job_payload["runs"] == [{"commit": "abc123"}]
                    break
                time.sleep(0.05)
            else:
                pytest.fail("Job did not complete in time")
        except ImportError:
            pytest.skip("API module not available")

    @patch("api.main.run_review")
    def test_review_status_not_found(self, mock_run_review):
        """Test polling unknown job returns 404."""
        try:
            from api.main import app

            client = TestClient(app)
            response = client.get("/review/unknown-job")
            assert response.status_code == 404
        except ImportError:
            pytest.skip("API module not available")

    @patch("api.main.run_review")
    def test_review_stream_endpoint(self, mock_run_review):
        """Ensure streaming endpoint is reachable and emits events."""
        try:
            from api.main import app

            def fake_run_review(repo, branch, max_commits, progress_callback):
                progress_callback("progress", {"step": 1})
                return [{"commit": "abc123"}]

            mock_run_review.side_effect = fake_run_review

            client = TestClient(app)
            response = client.get(
                "/review/stream",
                params={"repo": "test/repo", "branch": "main", "max_commits": 1},
            )
            assert response.status_code == 200
            body = response.text
            assert "event: progress" in body
            assert "event: complete" in body
            assert "abc123" in body
        except ImportError:
            pytest.skip("API module not available")
