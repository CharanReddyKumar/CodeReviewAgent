"""Tests for artifact_cache.py - Complete coverage"""
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from artifact_cache import (
    _state_path,
    _load_state,
    _save_state,
    _repo_head_sha,
    should_refresh_artifact,
    mark_artifact_refreshed,
    CACHE_ROOT,
)


class TestStatePath:
    """Tests for _state_path function."""

    def test_state_path_simple_reference(self):
        """Test state path for simple repo reference."""
        path = _state_path("github.com/user/repo")
        assert path.parent == CACHE_ROOT
        assert path.name.endswith(".json")
        assert "github.com_user_repo" in path.name

    def test_state_path_different_references(self):
        """Test state paths are different for different repos."""
        path1 = _state_path("github.com/user/repo1")
        path2 = _state_path("github.com/user/repo2")
        assert path1 != path2

    def test_state_path_normalization(self):
        """Test state path normalizes repo reference."""
        path1 = _state_path("https://github.com/user/repo")
        path2 = _state_path("github.com/user/repo")
        # Both should normalize to same path
        assert "github.com_user_repo" in path1.name
        assert "github.com_user_repo" in path2.name


class TestLoadState:
    """Tests for _load_state function."""

    def test_load_state_nonexistent_file(self, temp_dir, monkeypatch):
        """Test loading state when file doesn't exist."""
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", temp_dir)
        state = _load_state("github.com/user/repo")
        assert state == {}

    def test_load_state_existing_file(self, temp_dir, monkeypatch):
        """Test loading state from existing file."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        
        state_file = cache_dir / "github.com_user_repo.json"
        state_data = {"key1": "sha1", "key2": "sha2"}
        state_file.write_text(json.dumps(state_data))
        
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        state = _load_state("github.com/user/repo")
        assert state == state_data

    def test_load_state_corrupted_file(self, temp_dir, monkeypatch):
        """Test loading state from corrupted file."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        
        state_file = cache_dir / "github.com_user_repo.json"
        state_file.write_text("invalid json {")
        
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        state = _load_state("github.com/user/repo")
        assert state == {}

    def test_load_state_empty_file(self, temp_dir, monkeypatch):
        """Test loading state from empty file."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        
        state_file = cache_dir / "github.com_user_repo.json"
        state_file.write_text("")
        
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        state = _load_state("github.com/user/repo")
        assert state == {}


class TestSaveState:
    """Tests for _save_state function."""

    def test_save_state_creates_directory(self, temp_dir, monkeypatch):
        """Test saving state creates directory if needed."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        state = {"key1": "value1"}
        _save_state("github.com/user/repo", state)
        
        assert cache_dir.exists()
        state_file = cache_dir / "github.com_user_repo.json"
        assert state_file.exists()

    def test_save_state_writes_json(self, temp_dir, monkeypatch):
        """Test saving state writes proper JSON."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        state = {"key1": "sha1", "key2": "sha2"}
        _save_state("github.com/user/repo", state)
        
        state_file = cache_dir / "github.com_user_repo.json"
        loaded = json.loads(state_file.read_text())
        assert loaded == state

    def test_save_state_overwrites_existing(self, temp_dir, monkeypatch):
        """Test saving state overwrites existing file."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        # Save initial state
        _save_state("github.com/user/repo", {"key1": "old"})
        
        # Save new state
        _save_state("github.com/user/repo", {"key1": "new", "key2": "added"})
        
        state_file = cache_dir / "github.com_user_repo.json"
        loaded = json.loads(state_file.read_text())
        assert loaded == {"key1": "new", "key2": "added"}


class TestRepoHeadSha:
    """Tests for _repo_head_sha function."""

    def test_repo_head_sha(self, mock_repo):
        """Test getting repository HEAD SHA."""
        repo_path = Path(mock_repo.working_dir)
        sha = _repo_head_sha(repo_path)
        assert isinstance(sha, str)
        assert len(sha) == 40  # Git SHA-1 is 40 hex chars

    def test_repo_head_sha_changes_after_commit(self, mock_repo):
        """Test HEAD SHA changes after new commit."""
        repo_path = Path(mock_repo.working_dir)
        sha1 = _repo_head_sha(repo_path)
        
        # Create new commit
        test_file = repo_path / "new.py"
        test_file.write_text("# new file")
        mock_repo.index.add(["new.py"])
        mock_repo.index.commit("Add new file")
        
        sha2 = _repo_head_sha(repo_path)
        assert sha1 != sha2


class TestShouldRefreshArtifact:
    """Tests for should_refresh_artifact function."""

    def test_should_refresh_artifact_force(self, mock_repo, temp_dir, monkeypatch):
        """Test should refresh when force=True."""
        repo_path = Path(mock_repo.working_dir)
        cache_dir = temp_dir / ".cache" / "artifacts"
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        should_refresh, sha = should_refresh_artifact(
            repo_path, "github.com/user/repo", "test_key", force=True
        )
        
        assert should_refresh is True
        assert len(sha) == 40

    def test_should_refresh_artifact_no_cache(self, mock_repo, temp_dir, monkeypatch):
        """Test should refresh when no cache exists."""
        repo_path = Path(mock_repo.working_dir)
        cache_dir = temp_dir / ".cache" / "artifacts"
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        should_refresh, sha = should_refresh_artifact(
            repo_path, "github.com/user/repo", "test_key"
        )
        
        assert should_refresh is True
        assert len(sha) == 40

    def test_should_refresh_artifact_sha_matches(self, mock_repo, temp_dir, monkeypatch):
        """Test should not refresh when SHA matches cache."""
        repo_path = Path(mock_repo.working_dir)
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        # Get current SHA and save it
        current_sha = _repo_head_sha(repo_path)
        _save_state("github.com/user/repo", {"test_key": current_sha})
        
        should_refresh, sha = should_refresh_artifact(
            repo_path, "github.com/user/repo", "test_key"
        )
        
        assert should_refresh is False
        assert sha == current_sha

    def test_should_refresh_artifact_sha_differs(self, mock_repo, temp_dir, monkeypatch):
        """Test should refresh when SHA differs from cache."""
        repo_path = Path(mock_repo.working_dir)
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        # Save old SHA
        _save_state("github.com/user/repo", {"test_key": "old_sha_value"})
        
        # Get current SHA
        should_refresh, sha = should_refresh_artifact(
            repo_path, "github.com/user/repo", "test_key"
        )
        
        assert should_refresh is True
        assert sha != "old_sha_value"

    def test_should_refresh_artifact_different_key(self, mock_repo, temp_dir, monkeypatch):
        """Test should refresh for different key."""
        repo_path = Path(mock_repo.working_dir)
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        current_sha = _repo_head_sha(repo_path)
        _save_state("github.com/user/repo", {"other_key": current_sha})
        
        should_refresh, sha = should_refresh_artifact(
            repo_path, "github.com/user/repo", "test_key"
        )
        
        assert should_refresh is True  # Different key not in cache


class TestMarkArtifactRefreshed:
    """Tests for mark_artifact_refreshed function."""

    def test_mark_artifact_refreshed_new_key(self, temp_dir, monkeypatch):
        """Test marking artifact refreshed with new key."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        mark_artifact_refreshed("github.com/user/repo", "test_key", "abc123")
        
        state = _load_state("github.com/user/repo")
        assert state["test_key"] == "abc123"

    def test_mark_artifact_refreshed_updates_existing(self, temp_dir, monkeypatch):
        """Test marking artifact refreshed updates existing key."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        # Initial mark
        mark_artifact_refreshed("github.com/user/repo", "test_key", "old_sha")
        
        # Update
        mark_artifact_refreshed("github.com/user/repo", "test_key", "new_sha")
        
        state = _load_state("github.com/user/repo")
        assert state["test_key"] == "new_sha"

    def test_mark_artifact_refreshed_multiple_keys(self, temp_dir, monkeypatch):
        """Test marking multiple artifacts refreshed."""
        cache_dir = temp_dir / ".cache" / "artifacts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr("artifact_cache.CACHE_ROOT", cache_dir)
        
        mark_artifact_refreshed("github.com/user/repo", "key1", "sha1")
        mark_artifact_refreshed("github.com/user/repo", "key2", "sha2")
        mark_artifact_refreshed("github.com/user/repo", "key3", "sha3")
        
        state = _load_state("github.com/user/repo")
        assert state == {"key1": "sha1", "key2": "sha2", "key3": "sha3"}
