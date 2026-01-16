"""Unit tests for git worktree, merge, and conflict resolution.

This module tests git.py: GitBranchManager context manager.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from ralph2.git import GitBranchManager


class TestGitBranchManagerInit:
    """Tests for git.py GitBranchManager initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc"
        )
        assert manager.work_item_id == "ralph-123"
        assert manager.run_id == "run-abc"
        assert manager._worktree_created is False
        assert manager._worktree_path is None

    def test_init_with_custom_cwd(self):
        """Test initialization with custom working directory."""
        manager = GitBranchManager(
            work_item_id="ralph-456",
            run_id="run-xyz",
            cwd="/custom/path"
        )
        assert manager._cwd == "/custom/path"

    def test_branch_name_format(self):
        """Test branch name is constructed correctly."""
        manager = GitBranchManager(
            work_item_id="ralph-task-123",
            run_id="run-abc"
        )
        assert manager._branch_name == "ralph2/ralph-task-123"


class TestGitBranchManagerWorktreePath:
    """Tests for worktree path calculation."""

    def test_get_worktree_path_includes_run_id(self):
        """Test worktree path includes run_id for parallel execution isolation."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/projects/myapp"
        )
        path = manager.get_worktree_path()

        assert "run-abc" in path
        assert "ralph-123" in path
        assert "ralph2-executor" in path

    def test_get_worktree_path_sibling_directory(self):
        """Test worktree is created in sibling directory."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/projects/myapp"
        )
        path = manager.get_worktree_path()

        # Should be in /projects/, not /projects/myapp/
        assert path.startswith("/projects/")
        assert "/myapp/" not in path


class TestGitBranchManagerEnter:
    """Tests for GitBranchManager.__enter__ (context manager entry)."""

    def test_enter_creates_branch_and_worktree(self):
        """Test __enter__ creates branch and worktree."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stderr="")

            result = manager.__enter__()

        assert result is manager
        assert manager._worktree_created is True
        assert manager._worktree_path is not None

        # Verify git commands were called
        calls = mock_git.call_args_list
        assert len(calls) == 2

        # First call: create branch
        assert "branch" in calls[0][0][0]

        # Second call: create worktree
        assert "worktree" in calls[1][0][0]
        assert "add" in calls[1][0][0]

    def test_enter_cleans_up_branch_on_worktree_failure(self):
        """Test __enter__ cleans up branch if worktree creation fails."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            # Branch succeeds, worktree fails
            mock_git.side_effect = [
                MagicMock(returncode=0, stderr=""),  # branch creation
                MagicMock(returncode=1, stderr="worktree error"),  # worktree fails
                MagicMock(returncode=0, stderr=""),  # branch deletion
            ]

            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                manager.__enter__()

        # Verify cleanup was called
        calls = mock_git.call_args_list
        assert len(calls) == 3
        # Third call should be branch deletion
        assert "branch" in calls[2][0][0]
        assert "-D" in calls[2][0][0]

    def test_enter_raises_on_branch_failure(self):
        """Test __enter__ raises error if branch creation fails."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stderr="branch exists")

            with pytest.raises(RuntimeError, match="Failed to create branch"):
                manager.__enter__()


class TestGitBranchManagerExit:
    """Tests for GitBranchManager.__exit__ (context manager exit)."""

    def test_exit_cleans_up_worktree_and_branch(self):
        """Test __exit__ removes worktree and deletes branch."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_created = True
        manager._worktree_path = "/test/ralph2-executor-run-abc-ralph-123"

        with patch.object(manager, "_cleanup") as mock_cleanup:
            mock_cleanup.return_value = True

            result = manager.__exit__(None, None, None)

        assert result is False  # Don't suppress exceptions
        mock_cleanup.assert_called_once()

    def test_exit_skips_cleanup_if_not_created(self):
        """Test __exit__ skips cleanup if worktree wasn't created."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_created = False

        with patch.object(manager, "_cleanup") as mock_cleanup:
            manager.__exit__(None, None, None)

        mock_cleanup.assert_not_called()

    def test_exit_cleans_up_on_exception(self):
        """Test __exit__ cleans up even when exception occurred."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_created = True
        manager._worktree_path = "/test/worktree"

        with patch.object(manager, "_cleanup") as mock_cleanup:
            mock_cleanup.return_value = True

            # Simulate exception context
            manager.__exit__(ValueError, ValueError("test"), None)

        mock_cleanup.assert_called_once()


class TestGitBranchManagerCleanup:
    """Tests for GitBranchManager._cleanup method."""

    def test_cleanup_removes_worktree_and_branch(self):
        """Test _cleanup removes both worktree and branch."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_path = "/test/worktree"

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0)

            result = manager._cleanup()

        assert result is True
        assert manager._worktree_created is False

        # Verify both commands were called
        calls = mock_git.call_args_list
        assert len(calls) == 2

        # First: remove worktree
        assert "worktree" in calls[0][0][0]
        assert "remove" in calls[0][0][0]

        # Second: delete branch
        assert "branch" in calls[1][0][0]
        assert "-D" in calls[1][0][0]

    def test_cleanup_returns_false_on_failure(self):
        """Test _cleanup returns False if operations fail."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_path = "/test/worktree"

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stderr="error")
            with patch('ralph2.git._warn'):  # Suppress warning output
                result = manager._cleanup()

        assert result is False


class TestGitBranchManagerMerge:
    """Tests for merge_to_main method."""

    def test_merge_to_main_success(self):
        """Test successful merge to main branch."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stderr="")

            success, error = manager.merge_to_main()

        assert success is True
        assert error == ""

        # Verify checkout main was called first
        calls = mock_git.call_args_list
        assert "checkout" in calls[0][0][0]
        assert "main" in calls[0][0][0]

    def test_merge_to_main_checkout_failure(self):
        """Test merge fails when checkout main fails."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=1,
                stderr="cannot checkout main"
            )

            success, error = manager.merge_to_main()

        assert success is False
        assert "Failed to checkout main" in error

    def test_merge_to_main_merge_conflict(self):
        """Test merge fails on conflict."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.side_effect = [
                MagicMock(returncode=0, stderr=""),  # checkout succeeds
                MagicMock(returncode=1, stderr="CONFLICT in file.py"),  # merge fails
            ]

            success, error = manager.merge_to_main()

        assert success is False
        assert "Merge conflict" in error


class TestGitBranchManagerConflictCheck:
    """Tests for check_merge_conflicts method."""

    def test_check_merge_conflicts_no_conflicts(self):
        """Test no conflicts detected."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="M  modified.py\nA  new_file.py"
            )

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is False
        assert info == ""

    def test_check_merge_conflicts_detects_UU(self):
        """Test detects UU (both modified) conflicts."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="UU conflict_file.py\nM  modified.py"
            )

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "conflict_file.py" in info

    def test_check_merge_conflicts_detects_AA(self):
        """Test detects AA (both added) conflicts."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="AA new_conflict.py"
            )

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "new_conflict.py" in info

    def test_check_merge_conflicts_detects_DD(self):
        """Test detects DD (both deleted) conflicts."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0,
                stdout="DD deleted_conflict.py"
            )

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "deleted_conflict.py" in info

    def test_check_merge_conflicts_git_status_fails(self):
        """Test handles git status failure."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stdout="")

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "Failed to check git status" in info

    def test_check_merge_conflicts_empty_status(self):
        """Test handles empty git status output."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stdout="")

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is False
        assert info == ""


class TestGitBranchManagerManualCleanup:
    """Tests for manual cleanup method."""

    def test_cleanup_method_calls_internal_cleanup(self):
        """Test cleanup() method calls _cleanup()."""
        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_cleanup", return_value=True) as mock_cleanup:
            result = manager.cleanup()

        assert result is True
        mock_cleanup.assert_called_once()


