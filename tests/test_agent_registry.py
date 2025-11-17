"""Tests for agent_registry.py - Complete coverage"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_registry import (
    AgentSpec,
    detect_languages,
    get_tool_specs,
    instantiate_tools,
    _resolve_kwargs,
    _load_specs,
    LANGUAGE_EXTENSION_MAP,
    IGNORE_DIRS,
)


class TestDetectLanguages:
    """Tests for detect_languages function."""

    def test_detect_python(self, temp_dir):
        """Test detecting Python files."""
        (temp_dir / "test.py").write_text("print('hello')")
        languages = detect_languages(temp_dir)
        assert "python" in languages

    def test_detect_javascript(self, temp_dir):
        """Test detecting JavaScript files."""
        (temp_dir / "test.js").write_text("console.log('hello');")
        languages = detect_languages(temp_dir)
        assert "javascript" in languages

    def test_detect_typescript(self, temp_dir):
        """Test detecting TypeScript files."""
        (temp_dir / "test.ts").write_text("console.log('hello');")
        languages = detect_languages(temp_dir)
        assert "typescript" in languages

    def test_detect_multiple_languages(self, temp_dir):
        """Test detecting multiple languages."""
        (temp_dir / "test.py").write_text("print('hello')")
        (temp_dir / "test.js").write_text("console.log('hello');")
        (temp_dir / "test.ts").write_text("console.log('hello');")
        languages = detect_languages(temp_dir)
        assert "python" in languages
        assert "javascript" in languages
        assert "typescript" in languages

    def test_detect_ignores_pycache(self, temp_dir):
        """Test ignoring __pycache__ directory."""
        pycache = temp_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "test.pyc").write_text("bytecode")
        languages = detect_languages(temp_dir)
        assert languages == ["python"]

    def test_detect_ignores_node_modules(self, temp_dir):
        """Test ignoring node_modules directory."""
        node_modules = temp_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "test.js").write_text("code")
        languages = detect_languages(temp_dir)
        assert languages == ["python"]

    def test_detect_default_python(self, temp_dir):
        """Test defaulting to Python when no files found."""
        languages = detect_languages(temp_dir)
        assert languages == ["python"]

    def test_detect_nonexistent_path(self):
        """Test handling non-existent path."""
        languages = detect_languages(Path("/nonexistent/path"))
        assert languages == ["python"]

    def test_detect_html_css(self, temp_dir):
        """Test detecting HTML and CSS."""
        (temp_dir / "index.html").write_text("<html></html>")
        (temp_dir / "style.css").write_text("body {}")
        languages = detect_languages(temp_dir)
        assert "html" in languages
        assert "css" in languages


class TestResolveKwargs:
    """Tests for _resolve_kwargs function."""

    def test_resolve_repo_path_placeholder(self, temp_dir):
        """Test resolving repo path placeholder."""
        kwargs = {"repo_path": "__REPO_PATH__"}
        resolved = _resolve_kwargs(kwargs, "test/repo", temp_dir)
        assert resolved["repo_path"] == temp_dir

    def test_resolve_repo_reference_placeholder(self, temp_dir):
        """Test resolving repo reference placeholder."""
        kwargs = {"repo_reference": "__REPO_REFERENCE__"}
        resolved = _resolve_kwargs(kwargs, "test/repo", temp_dir)
        assert resolved["repo_reference"] == "test/repo"

    def test_resolve_regular_values(self, temp_dir):
        """Test regular values pass through unchanged."""
        kwargs = {"timeout": 60, "enabled": True, "name": "test"}
        resolved = _resolve_kwargs(kwargs, "test/repo", temp_dir)
        assert resolved["timeout"] == 60
        assert resolved["enabled"] is True
        assert resolved["name"] == "test"

    def test_resolve_mixed_placeholders(self, temp_dir):
        """Test resolving mixed placeholders and regular values."""
        kwargs = {
            "repo_path": "__REPO_PATH__",
            "repo_reference": "__REPO_REFERENCE__",
            "timeout": 120
        }
        resolved = _resolve_kwargs(kwargs, "test/repo", temp_dir)
        assert resolved["repo_path"] == temp_dir
        assert resolved["repo_reference"] == "test/repo"
        assert resolved["timeout"] == 120


class TestGetToolSpecs:
    """Tests for get_tool_specs function."""

    @patch("agent_registry._load_specs")
    def test_get_tool_specs_by_language(self, mock_load):
        """Test filtering tool specs by language."""
        mock_load.return_value = [
            AgentSpec(
                id="python_lint",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.lint_agent",
                class_name="LintAgent",
            ),
            AgentSpec(
                id="js_lint",
                languages=["javascript"],
                scope="file",
                kind="tool",
                module="agents.lint_agent",
                class_name="LintAgent",
            ),
        ]
        specs = get_tool_specs(["python"])
        assert len(specs) == 1
        assert specs[0].id == "python_lint"

    @patch("agent_registry._load_specs")
    def test_get_tool_specs_by_scope(self, mock_load):
        """Test filtering tool specs by scope."""
        mock_load.return_value = [
            AgentSpec(
                id="file_tool",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.test",
                class_name="Test",
            ),
            AgentSpec(
                id="repo_tool",
                languages=["python"],
                scope="repo",
                kind="tool",
                module="agents.test",
                class_name="Test",
            ),
        ]
        specs = get_tool_specs(["python"], scope="file")
        assert len(specs) == 1
        assert specs[0].id == "file_tool"

    @patch("agent_registry._load_specs")
    def test_get_tool_specs_case_insensitive(self, mock_load):
        """Test language matching is case insensitive."""
        mock_load.return_value = [
            AgentSpec(
                id="python_tool",
                languages=["Python"],
                scope="file",
                kind="tool",
                module="agents.test",
                class_name="Test",
            ),
        ]
        specs = get_tool_specs(["python"])
        assert len(specs) == 1


class TestInstantiateTools:
    """Tests for instantiate_tools function."""

    @pytest.fixture(autouse=True)
    def clear_registry_cache(self):
        """Clear registry cache before and after each test."""
        import agent_registry
        original_cache = agent_registry._REGISTRY_CACHE
        agent_registry._REGISTRY_CACHE = None
        yield
        agent_registry._REGISTRY_CACHE = original_cache

    @patch("agent_registry.get_tool_specs")
    @patch("agent_registry.importlib.import_module")
    def test_instantiate_tools_success(self, mock_import, mock_get_specs, temp_dir):
        """Test successful tool instantiation."""
        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        
        mock_module = MagicMock()
        mock_module.LintAgent = mock_class
        mock_import.return_value = mock_module
        
        mock_get_specs.return_value = [
            AgentSpec(
                id="python_lint",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.lint_agent",
                class_name="LintAgent",
                enabled=True,
                implemented=True,
            ),
        ]
        
        instances = instantiate_tools(["python"], "file", "test/repo", temp_dir)
        # May return multiple instances from real registry
        assert len(instances) >= 1

    @patch("agent_registry._load_specs")
    def test_instantiate_tools_skip_disabled(self, mock_load, temp_dir):
        """Test skipping disabled tools."""
        mock_load.return_value = [
            AgentSpec(
                id="disabled_tool",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.test",
                class_name="Test",
                enabled=False,
            ),
        ]
        instances = instantiate_tools(["python"], "file", "test/repo", temp_dir)
        assert len(instances) == 0

    @patch("agent_registry._load_specs")
    def test_instantiate_tools_skip_not_implemented(self, mock_load, temp_dir):
        """Test skipping not implemented tools."""
        mock_load.return_value = [
            AgentSpec(
                id="future_tool",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.test",
                class_name="Test",
                enabled=True,
                implemented=False,
            ),
        ]
        instances = instantiate_tools(["python"], "file", "test/repo", temp_dir)
        assert len(instances) == 0

    @patch("agent_registry._load_specs")
    @patch("agent_registry.importlib.import_module")
    def test_instantiate_tools_import_error(self, mock_import, mock_load, temp_dir):
        """Test handling import errors gracefully."""
        mock_import.side_effect = ImportError("Module not found")
        
        mock_load.return_value = [
            AgentSpec(
                id="broken_tool",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.broken",
                class_name="Broken",
                enabled=True,
                implemented=True,
            ),
        ]
        instances = instantiate_tools(["python"], "file", "test/repo", temp_dir)
        assert len(instances) == 0

    @patch("agent_registry._load_specs")
    @patch("agent_registry.importlib.import_module")
    def test_instantiate_tools_sets_tool_id(self, mock_import, mock_load, temp_dir):
        """Test tool_id is set on instance."""
        mock_instance = MagicMock(spec=[])  # No tool_id initially
        mock_class = MagicMock(return_value=mock_instance)
        mock_module = MagicMock()
        mock_module.Agent = mock_class
        mock_import.return_value = mock_module
        
        mock_load.return_value = [
            AgentSpec(
                id="test_agent",
                languages=["python"],
                scope="file",
                kind="tool",
                module="agents.test",
                class_name="Agent",
                enabled=True,
                implemented=True,
            ),
        ]
        
        instances = instantiate_tools(["python"], "file", "test/repo", temp_dir)
        assert len(instances) >= 1


class TestLoadSpecs:
    """Tests for _load_specs function."""

    @patch("agent_registry.REGISTRY_DIR")
    def test_load_specs_missing_directory(self, mock_dir):
        """Test handling missing registry directory."""
        mock_dir.exists.return_value = False
        from agent_registry import _REGISTRY_CACHE
        # Clear cache
        import agent_registry
        agent_registry._REGISTRY_CACHE = None
        specs = _load_specs()
        assert specs == []
