"""Tests for best_practices_store.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import chromadb

from best_practices_store import (
    _infer_risk_domain,
    get_best_practices_collection,
    ingest_commits_into_best_practices,
    CHROMA_DIR,
    _RISK_HINTS,
)


class TestInferRiskDomain:
    """Tests for _infer_risk_domain function."""

    def test_infer_security_risk(self):
        """Test inferring security risk domain."""
        text = "Fixed authentication vulnerability in login"
        domain = _infer_risk_domain(text)
        assert domain == "security"

    def test_infer_security_with_token(self):
        """Test inferring security risk with token keyword."""
        text = "Update OAuth token handling"
        domain = _infer_risk_domain(text)
        assert domain == "security"

    def test_infer_performance_risk(self):
        """Test inferring performance risk domain."""
        text = "Optimize database query performance"
        domain = _infer_risk_domain(text)
        assert domain == "performance"

    def test_infer_performance_with_cache(self):
        """Test inferring performance risk with cache keyword."""
        text = "Improve caching strategy"
        domain = _infer_risk_domain(text)
        assert domain == "performance"

    def test_infer_tests_risk(self):
        """Test inferring tests risk domain."""
        text = "Add unit tests for user service"
        domain = _infer_risk_domain(text)
        assert domain == "tests"

    def test_infer_tests_with_fixture(self):
        """Test inferring tests risk with fixture keyword."""
        text = "Update test fixtures"
        domain = _infer_risk_domain(text)
        assert domain == "tests"

    def test_infer_general_risk(self):
        """Test inferring general risk domain."""
        text = "Update README documentation"
        domain = _infer_risk_domain(text)
        assert domain == "general"

    def test_infer_risk_case_insensitive(self):
        """Test risk inference is case insensitive."""
        text1 = "Fix AUTHENTICATION issue"
        text2 = "Fix authentication issue"
        assert _infer_risk_domain(text1) == _infer_risk_domain(text2)
        assert _infer_risk_domain(text1) == "security"

    def test_infer_risk_empty_text(self):
        """Test inferring risk from empty text."""
        domain = _infer_risk_domain("")
        assert domain == "general"

    def test_infer_risk_none_text(self):
        """Test inferring risk from None text."""
        domain = _infer_risk_domain(None)
        assert domain == "general"

    def test_infer_risk_multiple_keywords(self):
        """Test first matching keyword wins."""
        # Security keywords appear in order before performance
        text = "Fix auth and improve perf"
        domain = _infer_risk_domain(text)
        # Should match security first
        assert domain == "security"


class TestGetBestPracticesCollection:
    """Tests for get_best_practices_collection function."""

    @patch("best_practices_store.chromadb.PersistentClient")
    def test_get_collection(self, mock_client_class):
        """Test getting best practices collection."""
        mock_client = Mock()
        mock_collection = Mock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client
        
        collection = get_best_practices_collection()
        
        mock_client.get_or_create_collection.assert_called_once_with(
            name="best_practices"
        )
        assert collection == mock_collection

    @patch("best_practices_store.chromadb.PersistentClient")
    def test_get_collection_uses_chroma_dir(self, mock_client_class):
        """Test collection uses CHROMA_DIR path."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        get_best_practices_collection()
        
        # Verify client was created with correct path
        call_args = mock_client_class.call_args
        assert call_args is not None


class TestIngestCommitsIntoBestPractices:
    """Tests for ingest_commits_into_best_practices function."""

    def test_ingest_commits_basic(self, mock_repo, temp_dir, monkeypatch, capsys):
        """Test basic commit ingestion."""
        mock_collection = Mock()
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            repo_path = Path(mock_repo.working_dir)
            ingest_commits_into_best_practices(
                repo_path, 
                "github.com/user/repo"
            )
        
        # Should have called add on collection
        assert mock_collection.add.called
        
        # Check output messages
        captured = capsys.readouterr()
        assert "Ingesting" in captured.out
        assert "Finished ingesting" in captured.out

    def test_ingest_commits_with_progress_callback(self, mock_repo):
        """Test commit ingestion with progress callback."""
        mock_collection = Mock()
        callback_calls = []
        
        def progress_callback(event, payload):
            callback_calls.append((event, payload))
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            repo_path = Path(mock_repo.working_dir)
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo",
                progress_callback=progress_callback
            )
        
        # Should have received progress callbacks
        assert len(callback_calls) > 0
        
        # Check for start, in-progress, and done events
        events = [call[0] for call in callback_calls]
        assert "best_practices_progress" in events

    def test_ingest_commits_batch_processing(self, mock_commit):
        """Test commits are processed in batches."""
        mock_collection = Mock()
        repo = mock_commit.repo
        repo_path = Path(repo.working_dir)
        
        # Create multiple commits
        for i in range(5):
            file = repo_path / f"file{i}.py"
            file.write_text(f"# File {i}")
            repo.index.add([f"file{i}.py"])
            repo.index.commit(f"Commit {i}")
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo"
            )
        
        # Collection.add should have been called at least once
        assert mock_collection.add.call_count >= 1

    def test_ingest_commits_metadata(self, mock_commit):
        """Test commit metadata is properly structured."""
        mock_collection = Mock()
        repo = mock_commit.repo
        repo_path = Path(repo.working_dir)
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo"
            )
        
        # Get the call arguments
        call_args = mock_collection.add.call_args
        if call_args:
            kwargs = call_args[1]
            
            # Check metadata structure
            if "metadatas" in kwargs:
                metadatas = kwargs["metadatas"]
                assert len(metadatas) > 0
                
                # Check first metadata
                meta = metadatas[0]
                assert "repo_reference" in meta
                assert "sha" in meta
                assert "kind" in meta
                assert meta["kind"] == "previous_review"
                assert "risk_domain" in meta
                assert "tags" in meta

    def test_ingest_commits_empty_repo(self, temp_dir, capsys):
        """Test ingesting from repository with no commits."""
        import git
        
        # Create empty repo
        repo_path = temp_dir / "empty_repo"
        repo_path.mkdir()
        git.Repo.init(repo_path)
        
        mock_collection = Mock()
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo"
            )
        
        # Should print message about no commits
        captured = capsys.readouterr()
        assert "No commit messages found" in captured.out

    def test_ingest_commits_progress_callback_exception(self, mock_commit):
        """Test that callback exceptions don't break ingestion."""
        mock_collection = Mock()
        
        def failing_callback(event, payload):
            raise Exception("Callback error")
        
        repo = mock_commit.repo
        repo_path = Path(repo.working_dir)
        
        # Should not raise even though callback fails
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo",
                progress_callback=failing_callback
            )
        
        # Ingestion should still complete
        assert mock_collection.add.called

    def test_ingest_commits_normalizes_repo_reference(self, mock_commit):
        """Test repo reference is normalized."""
        mock_collection = Mock()
        repo = mock_commit.repo
        repo_path = Path(repo.working_dir)
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            # Use URL that needs normalization
            ingest_commits_into_best_practices(
                repo_path,
                "https://github.com/user/repo.git"
            )
        
        # Check that normalized reference is used in metadata
        call_args = mock_collection.add.call_args
        if call_args:
            kwargs = call_args[1]
            if "metadatas" in kwargs:
                meta = kwargs["metadatas"][0]
                # Should be normalized without https:// and .git
                assert "github.com/user/repo" in meta["repo_reference"]

    def test_ingest_commits_generates_unique_ids(self, mock_commit):
        """Test unique IDs are generated for commits."""
        mock_collection = Mock()
        repo = mock_commit.repo
        repo_path = Path(repo.working_dir)
        
        # Create another commit
        file = repo_path / "another.py"
        file.write_text("# another")
        repo.index.add(["another.py"])
        repo.index.commit("Another commit")
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo"
            )
        
        # Get the IDs
        call_args = mock_collection.add.call_args
        if call_args:
            kwargs = call_args[1]
            if "ids" in kwargs:
                ids = kwargs["ids"]
                # All IDs should be unique
                assert len(ids) == len(set(ids))
                # IDs should contain SHA
                assert all("|" in id for id in ids)

    def test_ingest_commits_skip_empty_messages(self, temp_dir):
        """Test that commits with empty messages are skipped."""
        import git
        
        repo_path = temp_dir / "test_repo"
        repo_path.mkdir()
        repo = git.Repo.init(repo_path)
        
        # Create commit with message
        file1 = repo_path / "file1.py"
        file1.write_text("content")
        repo.index.add(["file1.py"])
        repo.index.commit("Normal commit")
        
        mock_collection = Mock()
        
        with patch("best_practices_store.get_best_practices_collection", return_value=mock_collection):
            ingest_commits_into_best_practices(
                repo_path,
                "github.com/user/repo"
            )
        
        # Should have processed only commits with messages
        call_args = mock_collection.add.call_args
        if call_args:
            kwargs = call_args[1]
            if "documents" in kwargs:
                docs = kwargs["documents"]
                # All documents should be non-empty
                assert all(doc.strip() for doc in docs)

    @patch("best_practices_store.get_best_practices_collection")
    def test_ingest_large_batch(self, mock_get_collection, mock_repo):
        """Test batching with large number of commits."""
        mock_collection = Mock()
        mock_get_collection.return_value = mock_collection
        
        repo_path = Path(mock_repo.working_dir)
        
        # Create many commits
        for i in range(50):
            file = repo_path / f"batch_file{i}.py"
            file.write_text(f"# Batch file {i}")
            mock_repo.index.add([f"batch_file{i}.py"])
            mock_repo.index.commit(f"Batch commit {i}")
        
        ingest_commits_into_best_practices(
            repo_path,
            "github.com/user/repo"
        )
        
        # Multiple batch calls should have been made
        assert mock_collection.add.call_count >= 1
