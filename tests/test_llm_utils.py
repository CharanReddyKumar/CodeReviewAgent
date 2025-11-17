"""Tests for llm_utils.py - Complete coverage"""
import os
from unittest.mock import Mock, patch, MagicMock

import pytest

from llm_utils import (
    pick_model,
    build_chat_model,
    extract_json_response,
    _normalize_model_name,
    _azure_deployment,
    _request_timeout,
    DEFAULT_MODEL,
    MODEL_ALIASES,
    TASK_ENV_MAP,
)


class TestPickModel:
    """Tests for pick_model function."""

    def test_pick_model_default(self, monkeypatch):
        """Test default model selection."""
        monkeypatch.delenv("LLM_MODEL", raising=False)
        model = pick_model("general")
        assert model == DEFAULT_MODEL

    def test_pick_model_with_env_override(self, monkeypatch):
        """Test model selection with environment override."""
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        model = pick_model("general")
        assert model == "custom-model"

    def test_pick_model_task_specific_planner(self, monkeypatch):
        """Test planner task-specific model selection."""
        monkeypatch.setenv("PLANNER_MODEL", "planner-model")
        model = pick_model("planner")
        assert model == "planner-model"

    def test_pick_model_task_specific_critic(self, monkeypatch):
        """Test critic task-specific model selection."""
        monkeypatch.setenv("CRITIC_MODEL", "critic-model")
        model = pick_model("critic_draft")
        assert model == "critic-model"

    def test_pick_model_task_specific_verifier(self, monkeypatch):
        """Test verifier task-specific model selection."""
        monkeypatch.setenv("VERIFIER_MODEL", "verifier-model")
        model = pick_model("verifier")
        assert model == "verifier-model"

    def test_pick_model_critical_severity_blocker(self, monkeypatch):
        """Test critical severity model override with blocker."""
        monkeypatch.setenv("CRITICAL_MODEL", "critical-model")
        model = pick_model("general", severity="blocker")
        assert model == "critical-model"

    def test_pick_model_critical_severity_high(self, monkeypatch):
        """Test critical severity model override with high."""
        monkeypatch.setenv("CRITICAL_MODEL", "critical-model")
        model = pick_model("general", severity="high")
        assert model == "critical-model"

    def test_pick_model_non_critical_severity(self, monkeypatch):
        """Test non-critical severity doesn't trigger override."""
        monkeypatch.setenv("CRITICAL_MODEL", "critical-model")
        monkeypatch.setenv("LLM_MODEL", "default-model")
        model = pick_model("general", severity="medium")
        assert model == "default-model"

    def test_normalize_model_name_with_alias(self):
        """Test model name normalization with alias."""
        normalized = _normalize_model_name("llama3.1:8b-instruct")
        assert normalized == "llama3.1:8b"

    def test_normalize_model_name_no_alias(self):
        """Test model name with no alias."""
        normalized = _normalize_model_name("custom-model")
        assert normalized == "custom-model"


class TestAzureDeployment:
    """Tests for _azure_deployment function."""

    def test_azure_deployment_task_specific(self, monkeypatch):
        """Test Azure deployment selection for specific task."""
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_PLANNER", "planner-deployment")
        deployment = _azure_deployment("planner")
        assert deployment == "planner-deployment"

    def test_azure_deployment_default(self, monkeypatch):
        """Test default Azure deployment."""
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_PLANNER", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "default-deployment")
        deployment = _azure_deployment("planner")
        assert deployment == "default-deployment"

    def test_azure_deployment_name_fallback(self, monkeypatch):
        """Test Azure deployment name fallback."""
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "name-deployment")
        deployment = _azure_deployment("general")
        assert deployment == "name-deployment"

    def test_azure_deployment_none(self, monkeypatch):
        """Test Azure deployment returns None when not set."""
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_GENERAL", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
        deployment = _azure_deployment("general")
        assert deployment is None


class TestRequestTimeout:
    """Tests for _request_timeout function."""

    def test_request_timeout_default(self, monkeypatch):
        """Test default request timeout."""
        monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
        timeout = _request_timeout()
        assert timeout == 120.0

    def test_request_timeout_custom(self, monkeypatch):
        """Test custom request timeout."""
        monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "300")
        timeout = _request_timeout()
        assert timeout == 300.0

    def test_request_timeout_invalid(self, monkeypatch):
        """Test invalid request timeout falls back to default."""
        monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "invalid")
        timeout = _request_timeout()
        assert timeout == 120.0


class TestBuildChatModel:
    """Tests for build_chat_model function."""

    @patch("langchain_openai.AzureChatOpenAI")
    def test_build_azure_chat_model(self, mock_azure, monkeypatch):
        """Test Azure OpenAI model creation."""
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
        
        build_chat_model("general")
        
        mock_azure.assert_called_once()
        call_kwargs = mock_azure.call_args[1]
        assert call_kwargs["azure_endpoint"] == "https://test.openai.azure.com"
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["azure_deployment"] == "gpt-4"

    @patch("langchain_openai.AzureChatOpenAI")
    def test_build_azure_with_api_version(self, mock_azure, monkeypatch):
        """Test Azure with custom API version."""
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01")
        
        build_chat_model("general")
        
        call_kwargs = mock_azure.call_args[1]
        assert call_kwargs["api_version"] == "2025-01-01"

    @patch("langchain_openai.ChatOpenAI")
    def test_build_openai_chat_model(self, mock_openai, monkeypatch):
        """Test OpenAI model creation."""
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
        
        build_chat_model("general")
        
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model_name"] == "gpt-4"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["base_url"] == "http://localhost:11434/v1"

    @patch("langchain_openai.ChatOpenAI")
    def test_build_openai_with_custom_temperature(self, mock_openai, monkeypatch):
        """Test OpenAI with custom temperature parameter."""
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
        
        build_chat_model("general", temperature=0.2)
        
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["temperature"] == 0.2

    @patch("langchain_community.chat_models.ChatOllama")
    @patch("langchain_openai.ChatOpenAI", side_effect=Exception("No OpenAI"))
    def test_build_ollama_chat_model_fallback(self, mock_openai, mock_ollama, monkeypatch):
        """Test Ollama model fallback."""
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
        monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
        monkeypatch.setenv("LLM_NUM_CTX", "16384")
        
        build_chat_model("general")
        
        mock_ollama.assert_called_once()
        call_kwargs = mock_ollama.call_args[1]
        assert call_kwargs["model"] == "llama3.1:8b"
        assert call_kwargs["num_ctx"] == 16384


class TestExtractJsonResponse:
    """Tests for extract_json_response function."""

    def test_extract_json_plain(self):
        """Test extracting plain JSON."""
        text = '{"status": "ok", "value": 123}'
        result = extract_json_response(text)
        assert result == {"status": "ok", "value": 123}

    def test_extract_json_with_whitespace(self):
        """Test extracting JSON with whitespace."""
        text = '  \n  {"status": "ok"}  \n  '
        result = extract_json_response(text)
        assert result == {"status": "ok"}

    def test_extract_json_in_code_fence(self):
        """Test extracting JSON from code fence."""
        text = '```json\n{"status": "ok"}\n```'
        result = extract_json_response(text)
        assert result == {"status": "ok"}

    def test_extract_json_in_code_fence_no_lang(self):
        """Test extracting JSON from code fence without language."""
        text = '```\n{"status": "ok"}\n```'
        result = extract_json_response(text)
        assert result == {"status": "ok"}

    def test_extract_json_with_prose(self):
        """Test extracting JSON mixed with prose."""
        text = 'Here is the result: {"status": "ok"} as requested.'
        result = extract_json_response(text)
        assert result == {"status": "ok"}

    def test_extract_json_array(self):
        """Test extracting JSON array."""
        text = 'The values are: [1, 2, 3, 4]'
        result = extract_json_response(text)
        assert result == [1, 2, 3, 4]

    def test_extract_json_nested(self):
        """Test extracting nested JSON."""
        text = '{"outer": {"inner": {"value": 42}}}'
        result = extract_json_response(text)
        assert result == {"outer": {"inner": {"value": 42}}}

    def test_extract_json_invalid(self):
        """Test extracting invalid JSON."""
        text = 'This is not JSON at all'
        result = extract_json_response(text)
        assert result is None

    def test_extract_json_empty(self):
        """Test extracting from empty string."""
        result = extract_json_response("")
        assert result is None

    def test_extract_json_multiple_objects(self):
        """Test extracting first valid JSON object."""
        text = '{"status": "ok"} more text {"another": "value"}'
        result = extract_json_response(text)
        # Should extract first complete JSON
        assert result is not None
        assert isinstance(result, dict)

    def test_extract_json_with_code_markers(self):
        """Test extracting JSON with code markers."""
        text = '''Here's the response:
        ```json
        {
            "items": [1, 2, 3],
            "total": 3
        }
        ```
        '''
        result = extract_json_response(text)
        assert result == {"items": [1, 2, 3], "total": 3}
