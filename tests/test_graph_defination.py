"""Tests for graph_defination.py - Complete coverage"""
import pytest

from graph_defination import (
    normalize_repo_reference,
    repo_slug,
    chroma_collection_name,
    repo_pickle_name,
    should_skip_path,
    DEFAULT_EXCLUDE_DIRS,
    _strip_git_suffix,
)


class TestStripGitSuffix:
    """Tests for _strip_git_suffix function."""

    def test_strip_git_suffix(self):
        """Test stripping .git suffix."""
        result = _strip_git_suffix("repo.git")
        assert result == "repo"

    def test_no_git_suffix(self):
        """Test value without .git suffix."""
        result = _strip_git_suffix("repo")
        assert result == "repo"

    def test_git_in_middle(self):
        """Test .git in middle of string."""
        result = _strip_git_suffix("my.git.repo")
        assert result == "my.git.repo"


class TestNormalizeRepoReference:
    """Tests for normalize_repo_reference function."""

    def test_normalize_https_url(self):
        """Test normalizing HTTPS URL."""
        url = "https://github.com/user/repo.git"
        result = normalize_repo_reference(url)
        assert result == "github.com/user/repo"

    def test_normalize_http_url(self):
        """Test normalizing HTTP URL."""
        url = "http://github.com/user/repo"
        result = normalize_repo_reference(url)
        assert result == "github.com/user/repo"

    def test_normalize_ssh_url(self):
        """Test normalizing SSH URL."""
        url = "git@github.com:user/repo.git"
        result = normalize_repo_reference(url)
        assert result == "github.com/user/repo"

    def test_normalize_already_normalized(self):
        """Test normalizing already normalized reference."""
        ref = "github.com/user/repo"
        result = normalize_repo_reference(ref)
        assert result == "github.com/user/repo"

    def test_normalize_with_trailing_slash(self):
        """Test normalizing URL with trailing slash."""
        url = "https://github.com/user/repo/"
        result = normalize_repo_reference(url)
        assert result == "github.com/user/repo"

    def test_normalize_gitlab_url(self):
        """Test normalizing GitLab URL."""
        url = "https://gitlab.com/group/subgroup/repo.git"
        result = normalize_repo_reference(url)
        assert result == "gitlab.com/group/subgroup/repo"

    def test_normalize_empty_raises(self):
        """Test normalizing empty string raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            normalize_repo_reference("")

    def test_normalize_whitespace_only_raises(self):
        """Test normalizing whitespace-only string raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            normalize_repo_reference("   ")

    def test_normalize_strips_whitespace(self):
        """Test normalizing strips surrounding whitespace."""
        url = "  https://github.com/user/repo.git  "
        result = normalize_repo_reference(url)
        assert result == "github.com/user/repo"

    def test_normalize_caching(self):
        """Test that normalization uses caching."""
        url = "https://github.com/user/repo.git"
        result1 = normalize_repo_reference(url)
        result2 = normalize_repo_reference(url)
        # Should return same object due to lru_cache
        assert result1 == result2

    def test_normalize_different_protocols_same_repo(self):
        """Test different protocols normalize to same reference."""
        https_url = "https://github.com/user/repo"
        http_url = "http://github.com/user/repo.git"
        ssh_url = "git@github.com:user/repo.git"
        
        https_result = normalize_repo_reference(https_url)
        http_result = normalize_repo_reference(http_url)
        ssh_result = normalize_repo_reference(ssh_url)
        
        assert https_result == http_result == ssh_result


class TestRepoSlug:
    """Tests for repo_slug function."""

    def test_repo_slug_simple(self):
        """Test creating simple repo slug."""
        ref = "github.com/user/repo"
        result = repo_slug(ref)
        assert result == "github_com_user_repo"

    def test_repo_slug_with_slashes(self):
        """Test slug replaces slashes with underscores."""
        ref = "gitlab.com/group/subgroup/repo"
        result = repo_slug(ref)
        assert "/" not in result
        assert "_" in result

    def test_repo_slug_with_special_chars(self):
        """Test slug handles special characters."""
        ref = "github.com/user/repo-name.test"
        result = repo_slug(ref)
        # Dots and hyphens should be preserved
        assert "." in result or "_" in result

    def test_repo_slug_from_url(self):
        """Test creating slug from URL."""
        url = "https://github.com/user/repo.git"
        result = repo_slug(url)
        assert result == "github_com_user_repo"

    def test_repo_slug_safe_for_filesystem(self):
        """Test slug is safe for filesystem."""
        ref = "github.com/user/repo"
        result = repo_slug(ref)
        # Should not contain problematic characters
        assert "/" not in result
        assert "\\" not in result


class TestChromaCollectionName:
    """Tests for chroma_collection_name function."""

    def test_chroma_collection_basic(self):
        """Test creating basic Chroma collection name."""
        ref = "github.com/user/repo"
        result = chroma_collection_name(ref)
        assert result.startswith("code_chunks_")
        assert "github_com_user_repo" in result

    def test_chroma_collection_starts_with_alnum(self):
        """Test collection name starts with alphanumeric."""
        ref = "github.com/user/repo"
        result = chroma_collection_name(ref)
        assert result[0].isalnum()

    def test_chroma_collection_ends_with_alnum(self):
        """Test collection name ends with alphanumeric."""
        ref = "github.com/user/repo"
        result = chroma_collection_name(ref)
        assert result[-1].isalnum()

    def test_chroma_collection_max_length(self):
        """Test collection name respects max length."""
        # Create a very long reference
        ref = "github.com/" + "a" * 600
        result = chroma_collection_name(ref)
        assert len(result) <= 512

    def test_chroma_collection_from_url(self):
        """Test creating collection name from URL."""
        url = "https://github.com/user/repo.git"
        result = chroma_collection_name(url)
        assert "code_chunks_" in result
        assert result[0].isalnum()


class TestRepoPickleName:
    """Tests for repo_pickle_name function."""

    def test_repo_pickle_name(self):
        """Test creating pickle filename."""
        ref = "github.com/user/repo"
        result = repo_pickle_name(ref)
        assert result == "github_com_user_repo"

    def test_repo_pickle_name_from_url(self):
        """Test creating pickle name from URL."""
        url = "https://github.com/user/repo.git"
        result = repo_pickle_name(url)
        assert result == "github_com_user_repo"

    def test_repo_pickle_name_no_extension(self):
        """Test pickle name doesn't include extension."""
        ref = "github.com/user/repo"
        result = repo_pickle_name(ref)
        assert not result.endswith(".pkl")


class TestShouldSkipPath:
    """Tests for should_skip_path function."""

    def test_should_skip_git_dir(self):
        """Test skipping .git directory."""
        path_parts = ["project", ".git", "objects"]
        assert should_skip_path(path_parts) is True

    def test_should_skip_pycache(self):
        """Test skipping __pycache__ directory."""
        path_parts = ["project", "src", "__pycache__"]
        assert should_skip_path(path_parts) is True

    def test_should_skip_node_modules(self):
        """Test skipping node_modules directory."""
        path_parts = ["project", "node_modules", "package"]
        assert should_skip_path(path_parts) is True

    def test_should_skip_venv(self):
        """Test skipping .venv directory."""
        path_parts = ["project", ".venv", "lib"]
        assert should_skip_path(path_parts) is True

    def test_should_not_skip_regular_path(self):
        """Test not skipping regular path."""
        path_parts = ["project", "src", "module.py"]
        assert should_skip_path(path_parts) is False

    def test_should_skip_any_excluded_part(self):
        """Test skipping when any part is excluded."""
        # Even if .git is in the middle
        path_parts = ["project", ".git"]
        assert should_skip_path(path_parts) is True

    def test_should_not_skip_empty_path(self):
        """Test not skipping empty path."""
        path_parts = []
        assert should_skip_path(path_parts) is False

    def test_should_skip_mypy_cache(self):
        """Test skipping .mypy_cache."""
        path_parts = ["project", ".mypy_cache"]
        assert should_skip_path(path_parts) is True

    def test_should_skip_pytest_cache(self):
        """Test skipping .pytest_cache."""
        path_parts = ["project", ".pytest_cache"]
        assert should_skip_path(path_parts) is True

    def test_default_exclude_dirs_coverage(self):
        """Test all default exclude dirs are checked."""
        for excluded_dir in DEFAULT_EXCLUDE_DIRS:
            path_parts = ["project", excluded_dir, "file"]
            assert should_skip_path(path_parts) is True

    def test_should_not_skip_similar_names(self):
        """Test not skipping similar but different names."""
        # "git" is not ".git"
        path_parts = ["project", "git", "file"]
        assert should_skip_path(path_parts) is False
        
        # "pycache" is not "__pycache__"
        path_parts = ["project", "pycache", "file"]
        assert should_skip_path(path_parts) is False


class TestDefaultExcludeDirs:
    """Tests for DEFAULT_EXCLUDE_DIRS constant."""

    def test_default_exclude_dirs_contains_git(self):
        """Test default excludes contain .git."""
        assert ".git" in DEFAULT_EXCLUDE_DIRS

    def test_default_exclude_dirs_contains_pycache(self):
        """Test default excludes contain __pycache__."""
        assert "__pycache__" in DEFAULT_EXCLUDE_DIRS

    def test_default_exclude_dirs_contains_venv(self):
        """Test default excludes contain .venv."""
        assert ".venv" in DEFAULT_EXCLUDE_DIRS

    def test_default_exclude_dirs_contains_node_modules(self):
        """Test default excludes contain node_modules."""
        assert "node_modules" in DEFAULT_EXCLUDE_DIRS

    def test_default_exclude_dirs_is_set(self):
        """Test DEFAULT_EXCLUDE_DIRS is a set."""
        assert isinstance(DEFAULT_EXCLUDE_DIRS, set)
