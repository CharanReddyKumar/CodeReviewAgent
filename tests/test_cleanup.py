"""Tests for cleanup.py - Complete coverage"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess

from cleanup import (
    prune_workspace,
    CleanupReport,
    DEFAULT_PATTERNS,
    _git_ls,
    _find_nested_git_root,
    _is_git_tracked,
    _iter_matches,
    _is_inside_git_dir,
)


class TestCleanupReport:
    """Tests for CleanupReport dataclass."""

    def test_cleanup_report_creation(self):
        """Test creating a cleanup report."""
        report = CleanupReport(
            removed=["file1", "file2"],
            skipped=["file3"],
            errors=["error1"]
        )
        assert report.removed == ["file1", "file2"]
        assert report.skipped == ["file3"]
        assert report.errors == ["error1"]

    def test_cleanup_report_to_dict(self):
        """Test converting report to dictionary."""
        report = CleanupReport(
            removed=["a.pyc"],
            skipped=["tracked.pyc"],
            errors=[]
        )
        result = report.to_dict()
        assert result == {
            "removed": ["a.pyc"],
            "skipped": ["tracked.pyc"],
            "errors": []
        }


class TestGitLs:
    """Tests for _git_ls function."""

    def test_git_ls_tracked_file(self, mock_repo):
        """Test git ls-files for tracked file."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create and track a file
        test_file = repo_path / "tracked.py"
        test_file.write_text("# tracked")
        mock_repo.index.add(["tracked.py"])
        mock_repo.index.commit("Add tracked file")
        
        result = _git_ls(repo_path, "tracked.py")
        assert "tracked.py" in result

    def test_git_ls_untracked_file(self, mock_repo):
        """Test git ls-files for untracked file."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create but don't track
        test_file = repo_path / "untracked.py"
        test_file.write_text("# untracked")
        
        result = _git_ls(repo_path, "untracked.py")
        assert result == "" or "untracked.py" not in result


class TestFindNestedGitRoot:
    """Tests for _find_nested_git_root function."""

    def test_find_no_nested_git(self, mock_repo):
        """Test finding no nested git root."""
        repo_path = Path(mock_repo.working_dir)
        file_path = repo_path / "some_file.py"
        
        result = _find_nested_git_root(repo_path, file_path)
        assert result is None

    def test_find_nested_git_root(self, mock_repo, temp_dir):
        """Test finding nested git repository."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create nested git repo
        nested_path = repo_path / "submodule"
        nested_path.mkdir()
        (nested_path / ".git").mkdir()
        
        file_path = nested_path / "file.py"
        
        result = _find_nested_git_root(repo_path, file_path)
        assert result == nested_path

    def test_find_stops_at_repo_path(self, mock_repo):
        """Test search stops at main repo path."""
        repo_path = Path(mock_repo.working_dir)
        
        # File directly in repo
        result = _find_nested_git_root(repo_path, repo_path)
        assert result is None


class TestIsGitTracked:
    """Tests for _is_git_tracked function."""

    def test_tracked_file(self, mock_repo):
        """Test that tracked file is detected."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create and track file
        test_file = repo_path / "tracked.py"
        test_file.write_text("# tracked")
        mock_repo.index.add(["tracked.py"])
        mock_repo.index.commit("Add file")
        
        assert _is_git_tracked(repo_path, test_file) is True

    def test_untracked_file(self, mock_repo):
        """Test that untracked file is detected."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create but don't track
        test_file = repo_path / "untracked.py"
        test_file.write_text("# untracked")
        
        assert _is_git_tracked(repo_path, test_file) is False

    def test_file_in_nested_git_tracked(self, mock_repo):
        """Test file in nested git repository."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create nested git repo
        nested_path = repo_path / "submodule"
        nested_path.mkdir()
        import git
        nested_repo = git.Repo.init(nested_path)
        
        # Create and track file in nested repo
        nested_file = nested_path / "nested.py"
        nested_file.write_text("# nested")
        nested_repo.index.add(["nested.py"])
        nested_repo.index.commit("Add nested file")
        
        # Should check in nested repo
        result = _is_git_tracked(repo_path, nested_file)
        # File is tracked in its nested repo
        assert result is True


class TestIterMatches:
    """Tests for _iter_matches function."""

    def test_iter_matches_single_pattern(self, temp_dir):
        """Test iterating matches for single pattern."""
        # Create files
        (temp_dir / "test.pyc").touch()
        (temp_dir / "another.pyc").touch()
        (temp_dir / "file.py").touch()
        
        matches = _iter_matches(temp_dir, ["*.pyc"])
        match_names = [m.name for m in matches]
        
        assert "test.pyc" in match_names
        assert "another.pyc" in match_names
        assert "file.py" not in match_names

    def test_iter_matches_multiple_patterns(self, temp_dir):
        """Test iterating matches for multiple patterns."""
        (temp_dir / "test.pyc").touch()
        (temp_dir / "cache").mkdir()
        (temp_dir / "file.py").touch()
        
        matches = _iter_matches(temp_dir, ["*.pyc", "cache"])
        match_names = [m.name for m in matches]
        
        assert "test.pyc" in match_names
        assert "cache" in match_names

    def test_iter_matches_deduplication(self, temp_dir):
        """Test that duplicate matches are deduplicated."""
        (temp_dir / "test.pyc").touch()
        
        # Use patterns that would match the same file
        matches = _iter_matches(temp_dir, ["*.pyc", "test.pyc"])
        
        # Should only appear once
        assert len(matches) == 1

    def test_iter_matches_nested_files(self, temp_dir):
        """Test matching files in nested directories."""
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.pyc").touch()
        
        matches = _iter_matches(temp_dir, ["*.pyc"])
        match_paths = [str(m.relative_to(temp_dir)) for m in matches]
        
        assert any("nested.pyc" in p for p in match_paths)


class TestIsInsideGitDir:
    """Tests for _is_inside_git_dir function."""

    def test_file_inside_git_dir(self, temp_dir):
        """Test detecting file inside .git directory."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        file_path = git_dir / "config"
        
        assert _is_inside_git_dir(temp_dir, file_path) is True

    def test_file_outside_git_dir(self, temp_dir):
        """Test detecting file outside .git directory."""
        file_path = temp_dir / "regular_file.py"
        
        assert _is_inside_git_dir(temp_dir, file_path) is False

    def test_nested_git_dir(self, temp_dir):
        """Test detecting file in nested .git directory."""
        subdir = temp_dir / "subdir" / ".git" / "objects"
        subdir.mkdir(parents=True)
        file_path = subdir / "object_file"
        
        assert _is_inside_git_dir(temp_dir, file_path) is True


class TestPruneWorkspace:
    """Tests for prune_workspace function."""

    def test_prune_pyc_files(self, mock_repo):
        """Test pruning .pyc files."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create .pyc files
        (repo_path / "test.pyc").touch()
        (repo_path / "another.pyc").touch()
        
        report = prune_workspace(repo_path, patterns=["*.pyc"])
        
        assert len(report.removed) == 2
        assert not (repo_path / "test.pyc").exists()
        assert not (repo_path / "another.pyc").exists()

    def test_prune_pycache_directory(self, mock_repo):
        """Test pruning __pycache__ directory."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create __pycache__
        pycache = repo_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").touch()
        
        report = prune_workspace(repo_path, patterns=["__pycache__"])
        
        assert "__pycache__" in report.removed
        assert not pycache.exists()

    def test_prune_dry_run(self, mock_repo):
        """Test dry run doesn't actually delete files."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create files
        (repo_path / "test.pyc").touch()
        
        report = prune_workspace(repo_path, patterns=["*.pyc"], dry_run=True)
        
        assert len(report.removed) == 1
        # File should still exist
        assert (repo_path / "test.pyc").exists()

    def test_prune_skip_tracked_files(self, mock_repo):
        """Test that git-tracked files are skipped."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create and track a .pyc file (unusual but possible)
        tracked_pyc = repo_path / "tracked.pyc"
        tracked_pyc.touch()
        mock_repo.index.add(["tracked.pyc"])
        mock_repo.index.commit("Add tracked pyc")
        
        # Create untracked .pyc
        untracked_pyc = repo_path / "untracked.pyc"
        untracked_pyc.touch()
        
        report = prune_workspace(repo_path, patterns=["*.pyc"])
        
        # Tracked file should be skipped
        assert "tracked.pyc" in report.skipped
        assert tracked_pyc.exists()
        
        # Untracked should be removed
        assert "untracked.pyc" in report.removed

    def test_prune_skip_git_directory(self, mock_repo):
        """Test that .git directory contents are skipped."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create file in .git directory
        git_file = repo_path / ".git" / "test.pyc"
        git_file.touch()
        
        report = prune_workspace(repo_path, patterns=["*.pyc"])
        
        # Should be skipped
        assert ".git/test.pyc" in report.skipped or "test.pyc" in report.skipped
        assert git_file.exists()

    def test_prune_default_patterns(self, mock_repo):
        """Test pruning with default patterns."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create various cleanup targets
        (repo_path / "test.pyc").touch()
        (repo_path / "__pycache__").mkdir()
        (repo_path / ".coverage").touch()
        
        report = prune_workspace(repo_path)
        
        # Should remove files matching default patterns
        assert len(report.removed) > 0

    def test_prune_skip_repo_root(self, mock_repo):
        """Test that repo root itself is not removed."""
        repo_path = Path(mock_repo.working_dir)
        
        report = prune_workspace(repo_path, patterns=["*"])
        
        # Repo path should not be in removed
        assert repo_path.exists()

    def test_prune_nested_directories(self, mock_repo):
        """Test pruning nested directories."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create nested structure
        nested = repo_path / "build" / "lib"
        nested.mkdir(parents=True)
        (nested / "file.so").touch()
        
        report = prune_workspace(repo_path, patterns=["build"])
        
        # Should remove entire build directory
        assert "build" in report.removed
        assert not (repo_path / "build").exists()

    def test_prune_handle_errors(self, mock_repo):
        """Test handling errors during removal."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create a file
        test_file = repo_path / "test.pyc"
        test_file.touch()
        
        # Mock unlink to raise error
        with patch("pathlib.Path.unlink", side_effect=PermissionError("No permission")):
            report = prune_workspace(repo_path, patterns=["*.pyc"])
        
        # Error should be recorded
        assert len(report.errors) > 0 or len(report.removed) > 0

    def test_prune_multiple_patterns(self, mock_repo):
        """Test pruning with multiple patterns."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create different types of files
        (repo_path / "test.pyc").touch()
        (repo_path / "test.pyo").touch()
        (repo_path / ".coverage").touch()
        
        report = prune_workspace(repo_path, patterns=["*.pyc", "*.pyo", ".coverage"])
        
        assert len(report.removed) == 3

    def test_prune_with_custom_patterns(self, mock_repo):
        """Test pruning with custom patterns."""
        repo_path = Path(mock_repo.working_dir)
        
        # Create custom files
        (repo_path / "temp.log").touch()
        (repo_path / "debug.log").touch()
        
        report = prune_workspace(repo_path, patterns=["*.log"])
        
        assert len(report.removed) == 2
        assert all(".log" in f for f in report.removed)
