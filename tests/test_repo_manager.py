"""Tests for repo_manager.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from git.exc import GitCommandError

from repo_manager import _slug_from_url, get_or_clone_repo, BASE_REPO_DIR


class TestSlugFromUrl:
    """Tests for _slug_from_url function."""

    def test_slug_from_https_url(self):
        """Test slug generation from HTTPS URL."""
        url = "https://github.com/user/repo.git"
        slug = _slug_from_url(url)
        assert slug == "github.com_user_repo"

    def test_slug_from_url_no_git_extension(self):
        """Test slug generation from URL without .git."""
        url = "https://github.com/user/repo"
        slug = _slug_from_url(url)
        assert slug == "github.com_user_repo"

    def test_slug_from_ssh_url(self):
        """Test slug generation from SSH URL."""
        url = "git@github.com:user/repo.git"
        slug = _slug_from_url(url)
        # SSH URLs parsed by urlparse may have different structure
        assert "user" in slug and "repo" in slug

    def test_slug_with_trailing_slash(self):
        """Test slug generation with trailing slash."""
        url = "https://github.com/user/repo/"
        slug = _slug_from_url(url)
        assert slug == "github.com_user_repo"

    def test_slug_with_subgroups(self):
        """Test slug generation with subgroups."""
        url = "https://gitlab.com/group/subgroup/repo.git"
        slug = _slug_from_url(url)
        assert slug == "gitlab.com_group_subgroup_repo"

    def test_slug_http_url(self):
        """Test slug generation from HTTP URL."""
        url = "http://git.example.com/user/repo.git"
        slug = _slug_from_url(url)
        assert slug == "git.example.com_user_repo"


class TestGetOrCloneRepo:
    """Tests for get_or_clone_repo function."""

    @patch("repo_manager.git.Repo")
    def test_clone_new_repo(self, mock_repo_class, temp_dir):
        """Test cloning a new repository."""
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_repo_class.clone_from.return_value = mock_repo
        
        with patch("repo_manager.BASE_REPO_DIR", temp_dir):
            url = "https://github.com/user/repo.git"
            result = get_or_clone_repo(url, branch="main")
            
            mock_repo_class.clone_from.assert_called_once()
            mock_remote.fetch.assert_called_with("main")
            mock_repo.git.checkout.assert_called_once_with("-B", "main", "origin/main")
            assert result == temp_dir / "github.com_user_repo"

    @patch("repo_manager.git.Repo")
    def test_use_existing_repo(self, mock_repo_class, temp_dir):
        """Test using existing repository."""
        # Create repo directory
        repo_dir = temp_dir / "github.com_user_repo"
        repo_dir.mkdir(parents=True)
        
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_repo_class.return_value = mock_repo
        
        with patch("repo_manager.BASE_REPO_DIR", temp_dir):
            url = "https://github.com/user/repo.git"
            result = get_or_clone_repo(url, branch="develop")
            
            mock_repo_class.assert_called_once_with(repo_dir)
            assert mock_remote.fetch.call_args_list == [call(), call("develop")]
            mock_repo.git.checkout.assert_called_once_with("-B", "develop", "origin/develop")

    @patch("repo_manager.git.Repo")
    def test_checkout_branch_failure(self, mock_repo_class, temp_dir):
        """Test handling checkout failure gracefully."""
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_remote.fetch.side_effect = [GitCommandError("origin fetch nonexistent", 1, "error"), None]
        mock_repo_class.clone_from.return_value = mock_repo
        
        with patch("repo_manager.BASE_REPO_DIR", temp_dir):
            url = "https://github.com/user/repo.git"
            with pytest.raises(RuntimeError) as exc:
                get_or_clone_repo(url, branch="nonexistent")
            assert "Branch 'nonexistent'" in str(exc.value)

    @patch("repo_manager.git.Repo")
    def test_get_or_clone_default_branch(self, mock_repo_class, temp_dir):
        """Test cloning with default branch."""
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_repo_class.clone_from.return_value = mock_repo
        
        with patch("repo_manager.BASE_REPO_DIR", temp_dir):
            url = "https://github.com/user/repo.git"
            result = get_or_clone_repo(url)  # Default branch is "main"
            
            mock_repo.git.checkout.assert_called_once_with("-B", "main", "origin/main")

    @patch("repo_manager.git.Repo")
    def test_get_or_clone_repo_prints_messages(self, mock_repo_class, temp_dir, capsys):
        """Test that appropriate messages are printed."""
        mock_repo = MagicMock()
        mock_remote = MagicMock()
        mock_repo.remotes.origin = mock_remote
        mock_repo_class.clone_from.return_value = mock_repo
        
        with patch("repo_manager.BASE_REPO_DIR", temp_dir):
            url = "https://github.com/user/repo.git"
            get_or_clone_repo(url)
            
            captured = capsys.readouterr()
            assert "Cloning" in captured.out or "already exists" in captured.out
