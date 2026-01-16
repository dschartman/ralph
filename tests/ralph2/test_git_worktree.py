"""Unit tests for git worktree, merge, and conflict resolution.

This module tests:
- git.py: GitBranchManager context manager
- git_manager.py: GitBranchManager class for worktree operations
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from ralph2.git import GitBranchManager as GitBranchManagerContextManager
from ralph2.git_manager import GitBranchManager


class TestGitBranchManagerContextManagerInit:
    """Tests for git.py GitBranchManager initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc"
        )
        assert manager.work_item_id == "ralph-123"
        assert manager.run_id == "run-abc"
        assert manager._worktree_created is False
        assert manager._worktree_path is None

    def test_init_with_custom_cwd(self):
        """Test initialization with custom working directory."""
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-456",
            run_id="run-xyz",
            cwd="/custom/path"
        )
        assert manager._cwd == "/custom/path"

    def test_branch_name_format(self):
        """Test branch name is constructed correctly."""
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-task-123",
            run_id="run-abc"
        )
        assert manager._branch_name == "ralph2/ralph-task-123"


class TestGitBranchManagerContextManagerWorktreePath:
    """Tests for worktree path calculation."""

    def test_get_worktree_path_includes_run_id(self):
        """Test worktree path includes run_id for parallel execution isolation."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/projects/myapp"
        )
        path = manager.get_worktree_path()

        # Should be in /projects/, not /projects/myapp/
        assert path.startswith("/projects/")
        assert "/myapp/" not in path


class TestGitBranchManagerContextManagerEnter:
    """Tests for GitBranchManager.__enter__ (context manager entry)."""

    def test_enter_creates_branch_and_worktree(self):
        """Test __enter__ creates branch and worktree."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stderr="branch exists")

            with pytest.raises(RuntimeError, match="Failed to create branch"):
                manager.__enter__()


class TestGitBranchManagerContextManagerExit:
    """Tests for GitBranchManager.__exit__ (context manager exit)."""

    def test_exit_cleans_up_worktree_and_branch(self):
        """Test __exit__ removes worktree and deletes branch."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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


class TestGitBranchManagerContextManagerCleanup:
    """Tests for GitBranchManager._cleanup method."""

    def test_cleanup_removes_worktree_and_branch(self):
        """Test _cleanup removes both worktree and branch."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )
        manager._worktree_path = "/test/worktree"

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1)

            result = manager._cleanup()

        assert result is False


class TestGitBranchManagerContextManagerMerge:
    """Tests for merge_to_main method."""

    def test_merge_to_main_success(self):
        """Test successful merge to main branch."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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


class TestGitBranchManagerContextManagerConflictCheck:
    """Tests for check_merge_conflicts method."""

    def test_check_merge_conflicts_no_conflicts(self):
        """Test no conflicts detected."""
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
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
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_run_git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stdout="")

            has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is False
        assert info == ""


class TestGitBranchManagerContextManagerManualCleanup:
    """Tests for manual cleanup method."""

    def test_cleanup_method_calls_internal_cleanup(self):
        """Test cleanup() method calls _cleanup()."""
        manager = GitBranchManagerContextManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        with patch.object(manager, "_cleanup", return_value=True) as mock_cleanup:
            result = manager.cleanup()

        assert result is True
        mock_cleanup.assert_called_once()


# Tests for git_manager.py GitBranchManager

class TestGitManagerInit:
    """Tests for git_manager.py GitBranchManager initialization."""

    def test_init(self):
        """Test initialization."""
        manager = GitBranchManager(
            project_root="/path/to/project",
            run_id="ralph2-abc123"
        )

        assert manager.project_root == Path("/path/to/project")
        assert manager.run_id == "ralph2-abc123"
        assert manager._active_worktrees == {}


class TestGitManagerBranchName:
    """Tests for branch name generation."""

    def test_get_branch_name(self):
        """Test branch name includes run_id and work_item_id."""
        manager = GitBranchManager(
            project_root="/path/to/project",
            run_id="run-xyz"
        )

        branch = manager.get_branch_name("task-123")

        assert branch == "ralph2/run-xyz/task-123"


class TestGitManagerWorktreePath:
    """Tests for worktree path generation."""

    def test_get_worktree_path(self):
        """Test worktree path includes run_id."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        path = manager.get_worktree_path("task-456")

        assert "run-abc" in path
        assert "task-456" in path
        assert "ralph2-executor" in path

    def test_get_worktree_path_sibling_to_project(self):
        """Test worktree is created as sibling to project root."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        path = manager.get_worktree_path("task-456")

        # Should be in /projects/, not /projects/myapp/
        assert path.startswith("/projects/")
        assert "/myapp/" not in path


class TestGitManagerCreateWorktree:
    """Tests for worktree creation."""

    def test_create_worktree_success(self):
        """Test successful worktree creation."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            path = manager.create_worktree("task-123")

        assert path == manager.get_worktree_path("task-123")
        assert "task-123" in manager._active_worktrees

    def test_create_worktree_branch_exists(self):
        """Test handles pre-existing branch gracefully."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="branch already exists"),  # branch
                MagicMock(returncode=0, stderr=""),  # worktree
            ]

            path = manager.create_worktree("task-123")

        assert path is not None

    def test_create_worktree_cleans_up_on_failure(self):
        """Test cleanup when worktree creation fails after branch created."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stderr=""),  # branch created
                MagicMock(returncode=1, stderr="worktree failed"),  # worktree fails
                MagicMock(returncode=0, stderr=""),  # branch deleted
            ]

            with pytest.raises(RuntimeError, match="Failed to create worktree"):
                manager.create_worktree("task-123")

    def test_create_worktree_branch_failure_not_exists(self):
        """Test raises error when branch creation fails (not exists error)."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="fatal: invalid reference"
            )

            with pytest.raises(RuntimeError, match="Failed to create branch"):
                manager.create_worktree("task-123")


class TestGitManagerCleanup:
    """Tests for worktree cleanup."""

    def test_cleanup_success(self):
        """Test successful cleanup of worktree and branch."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )
        manager._active_worktrees["task-123"] = "/some/path"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = manager.cleanup("task-123")

        assert result is True
        assert "task-123" not in manager._active_worktrees

    def test_cleanup_removes_from_tracking(self):
        """Test cleanup removes work item from tracking dict."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )
        manager._active_worktrees = {"task-1": "/path1", "task-2": "/path2"}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            manager.cleanup("task-1")

        assert "task-1" not in manager._active_worktrees
        assert "task-2" in manager._active_worktrees

    def test_cleanup_handles_not_a_worktree(self):
        """Test cleanup handles 'not a working tree' error gracefully."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="is not a working tree"),
                MagicMock(returncode=0, stderr=""),  # branch deletion
            ]

            result = manager.cleanup("task-123")

        # Should still succeed (worktree removal is considered done)
        assert result is True


class TestGitManagerCleanupAll:
    """Tests for cleanup_all method."""

    def test_cleanup_all(self):
        """Test cleanup_all removes all active worktrees."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )
        manager._active_worktrees = {
            "task-1": "/path1",
            "task-2": "/path2",
            "task-3": "/path3",
        }

        with patch.object(manager, "cleanup") as mock_cleanup:
            mock_cleanup.return_value = True

            manager.cleanup_all()

        assert mock_cleanup.call_count == 3


class TestGitManagerMerge:
    """Tests for merge_changes method."""

    def test_merge_changes_success(self):
        """Test successful merge."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = manager.merge_changes("task-123")

        assert result is True

    def test_merge_changes_failure(self):
        """Test merge failure (conflict)."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="CONFLICT"
            )

            result = manager.merge_changes("task-123")

        assert result is False

    def test_merge_changes_exception_returns_false(self):
        """Test merge returns False on exception."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("unexpected error")

            result = manager.merge_changes("task-123")

        assert result is False


class TestGitManagerCleanupAbandoned:
    """Tests for cleanup_abandoned_worktrees class method."""

    def test_cleanup_abandoned_worktrees_success(self):
        """Test cleanup of abandoned worktrees."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # git worktree list
                MagicMock(
                    returncode=0,
                    stdout="worktree /projects/myapp\nworktree /projects/ralph2-executor-ralph2-abc-task1\n"
                ),
                # git worktree remove
                MagicMock(returncode=0),
                # git branch list
                MagicMock(returncode=0, stdout=""),
            ]

            cleaned = GitBranchManager.cleanup_abandoned_worktrees(
                "/projects/myapp",
                run_id_prefix="ralph2-"
            )

        assert cleaned >= 0

    def test_cleanup_abandoned_handles_failure(self):
        """Test cleanup handles git failure gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            cleaned = GitBranchManager.cleanup_abandoned_worktrees(
                "/projects/myapp"
            )

        assert cleaned == 0

    def test_cleanup_abandoned_handles_exception(self):
        """Test cleanup handles exceptions gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("git not found")

            cleaned = GitBranchManager.cleanup_abandoned_worktrees(
                "/projects/myapp"
            )

        assert cleaned == 0


class TestGitManagerDeleteBranch:
    """Tests for _delete_branch method."""

    def test_delete_branch_success(self):
        """Test successful branch deletion."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = manager._delete_branch("ralph2/run-abc/task-123")

        assert result is True

    def test_delete_branch_failure(self):
        """Test branch deletion failure."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = manager._delete_branch("nonexistent-branch")

        assert result is False

    def test_delete_branch_exception(self):
        """Test branch deletion handles exception."""
        manager = GitBranchManager(
            project_root="/projects/myapp",
            run_id="run-abc"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("unexpected")

            result = manager._delete_branch("some-branch")

        assert result is False
