"""Tests for GitBranchManager class with run_id support for parallel execution."""

import pytest
from unittest.mock import MagicMock, patch
import subprocess


class TestGitBranchManager:
    """Test the GitBranchManager context manager class."""

    def test_git_branch_manager_is_context_manager(self):
        """Test that GitBranchManager can be used as a context manager."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")

        # Verify it has context manager methods
        assert hasattr(manager, '__enter__'), "GitBranchManager must have __enter__ method"
        assert hasattr(manager, '__exit__'), "GitBranchManager must have __exit__ method"

    def test_worktree_path_includes_run_id(self):
        """Test that worktree path includes run_id to prevent conflicts between parallel runs."""
        from ralph2.git import GitBranchManager

        with patch('os.getcwd', return_value='/mock/repo'):
            manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
            worktree_path = manager.get_worktree_path()

        # Verify run_id is in the path
        assert "run-abc123" in worktree_path, f"Worktree path should include run_id: {worktree_path}"
        assert "ralph-test1" in worktree_path, f"Worktree path should include work_item_id: {worktree_path}"

    def test_different_run_ids_produce_different_paths(self):
        """Test that different run_ids produce different worktree paths."""
        from ralph2.git import GitBranchManager

        with patch('os.getcwd', return_value='/mock/repo'):
            manager1 = GitBranchManager(work_item_id="ralph-test1", run_id="run-111")
            manager2 = GitBranchManager(work_item_id="ralph-test1", run_id="run-222")

            path1 = manager1.get_worktree_path()
            path2 = manager2.get_worktree_path()

        # Paths should be different
        assert path1 != path2, "Different run_ids should produce different worktree paths"

    def test_enter_creates_branch_and_worktree(self):
        """Test that __enter__ creates the git branch and worktree."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager.__enter__()

        # Verify branch creation
        branch_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and 'ralph2/ralph-test1' in ' '.join(cmd)]
        assert len(branch_cmds) > 0, f"Should create branch, commands: {git_commands}"

        # Verify worktree creation
        worktree_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd)]
        assert len(worktree_cmds) > 0, f"Should create worktree, commands: {git_commands}"

    def test_exit_cleans_up_worktree_and_branch(self):
        """Test that __exit__ always cleans up worktree and branch."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True  # Simulate successful creation
                manager._worktree_path = "/mock/worktree"
                manager.__exit__(None, None, None)

        # Verify worktree removal
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_remove_cmds) > 0, "Should remove worktree on exit"

        # Verify branch deletion
        branch_delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(branch_delete_cmds) > 0, "Should delete branch on exit"

    def test_exit_cleans_up_on_exception(self):
        """Test that __exit__ cleans up even when an exception occurred."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True
                manager._worktree_path = "/mock/worktree"
                # Simulate exception context
                manager.__exit__(ValueError, ValueError("test error"), None)

        # Cleanup should still happen
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_remove_cmds) > 0, "Should remove worktree even on exception"

    def test_cleanup_when_branch_exists_but_worktree_fails(self):
        """Test guaranteed cleanup when branch creation succeeds but worktree fails."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()

            # Branch creation succeeds
            if 'branch' in ' '.join(cmd) and '-D' not in cmd:
                result.returncode = 0
            # Worktree creation fails
            elif 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "fatal: worktree failed"
            else:
                result.returncode = 0

            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")

                # Enter should fail due to worktree creation failure
                with pytest.raises(RuntimeError):
                    manager.__enter__()

        # Verify branch was cleaned up after worktree failure
        branch_delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(branch_delete_cmds) > 0, "Should delete branch when worktree creation fails"

    def test_merge_to_main_method(self):
        """Test that GitBranchManager has a merge_to_main method."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                success, error = manager.merge_to_main()

        # Verify checkout main and merge commands
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in ' '.join(cmd) and 'main' in ' '.join(cmd)]
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]

        assert len(checkout_cmds) > 0, "Should checkout main"
        assert len(merge_cmds) > 0, "Should merge feature branch"
        assert success is True, "Merge should succeed"

    def test_merge_conflict_returns_false(self):
        """Test that merge_to_main returns False on merge conflict."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()

            if 'merge' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "CONFLICT: merge conflict"
            else:
                result.returncode = 0

            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                success, error = manager.merge_to_main()

        assert success is False, "Merge should fail on conflict"
        assert "conflict" in error.lower(), f"Error should mention conflict: {error}"


class TestCheckMergeConflicts:
    """Tests for check_merge_conflicts method - all branch coverage."""

    def test_check_merge_conflicts_no_conflicts(self):
        """Test check_merge_conflicts returns False when no conflicts."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "M  modified_file.py\n?? untracked.txt\n"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is False
        assert info == ""

    def test_check_merge_conflicts_with_uu_marker(self):
        """Test check_merge_conflicts detects UU (both modified) conflicts."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "UU conflicting_file.py\nM  other_file.py\n"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "conflicting_file.py" in info

    def test_check_merge_conflicts_with_aa_marker(self):
        """Test check_merge_conflicts detects AA (both added) conflicts."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "AA both_added.py\n"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "both_added.py" in info

    def test_check_merge_conflicts_with_dd_marker(self):
        """Test check_merge_conflicts detects DD (both deleted) conflicts."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "DD both_deleted.py\n"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "both_deleted.py" in info

    def test_check_merge_conflicts_multiple_conflicts(self):
        """Test check_merge_conflicts lists all conflicting files."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "UU file1.py\nAA file2.py\nDD file3.py\nM  normal.py\n"
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "file1.py" in info
        assert "file2.py" in info
        assert "file3.py" in info

    def test_check_merge_conflicts_git_status_fails(self):
        """Test check_merge_conflicts handles git status failure."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "fatal: not a git repository"
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is True
        assert "Failed to check git status" in info

    def test_check_merge_conflicts_empty_output(self):
        """Test check_merge_conflicts handles empty git status output."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""  # Empty output = clean working directory
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                has_conflicts, info = manager.check_merge_conflicts()

        assert has_conflicts is False
        assert info == ""


class TestMergeToMainBranches:
    """Additional branch coverage tests for merge_to_main."""

    def test_merge_to_main_checkout_fails(self):
        """Test merge_to_main handles checkout failure."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if 'checkout' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "error: pathspec 'main' did not match any file(s) known to git"
            else:
                result.returncode = 0
            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                success, error = manager.merge_to_main()

        assert success is False
        assert "Failed to checkout main" in error

    def test_branch_creation_fails(self):
        """Test __enter__ handles branch creation failure."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            if 'branch' in ' '.join(cmd) and '-D' not in cmd:
                result.returncode = 1
                result.stderr = "fatal: A branch named 'ralph2/ralph-test1' already exists."
            else:
                result.returncode = 0
            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")

                with pytest.raises(RuntimeError) as exc_info:
                    manager.__enter__()

        assert "Failed to create branch" in str(exc_info.value)


class TestCleanupLoggingOnFailure:
    """Tests for error logging when cleanup operations fail."""

    def test_cleanup_logs_error_when_worktree_removal_fails(self):
        """Test that errors are logged when worktree removal fails during cleanup."""
        from ralph2.git import GitBranchManager
        import logging

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            # Worktree removal fails
            if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "fatal: worktree removal failed"
            else:
                result.returncode = 0
            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True
                manager._worktree_path = "/mock/worktree"

                # Should log error but not raise
                with patch('ralph2.git.logger') as mock_logger:
                    result = manager._cleanup()

                    # Cleanup should return False on failure
                    assert result is False

                    # Error should be logged for worktree removal failure
                    mock_logger.warning.assert_called()
                    logged_message = mock_logger.warning.call_args[0][0]
                    assert "worktree" in logged_message.lower()

    def test_cleanup_logs_error_when_branch_deletion_fails(self):
        """Test that errors are logged when branch deletion fails during cleanup."""
        from ralph2.git import GitBranchManager
        import logging

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            # Worktree removal succeeds
            if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd):
                result.returncode = 0
            # Branch deletion fails
            elif 'branch' in ' '.join(cmd) and '-D' in cmd:
                result.returncode = 1
                result.stderr = "error: branch deletion failed"
            else:
                result.returncode = 0
            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True
                manager._worktree_path = "/mock/worktree"

                with patch('ralph2.git.logger') as mock_logger:
                    result = manager._cleanup()

                    # Cleanup should return False on failure
                    assert result is False

                    # Error should be logged for branch deletion failure
                    mock_logger.warning.assert_called()
                    logged_message = mock_logger.warning.call_args[0][0]
                    assert "branch" in logged_message.lower()

    def test_enter_logs_error_when_branch_cleanup_fails_after_worktree_failure(self):
        """Test error logging when cleanup fails during partial worktree creation failure."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()

            # Branch creation succeeds
            if 'branch' in ' '.join(cmd) and '-D' not in cmd:
                result.returncode = 0
            # Worktree creation fails
            elif 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "fatal: worktree failed"
            # Branch cleanup ALSO fails (this is the edge case)
            elif 'branch' in ' '.join(cmd) and '-D' in cmd:
                result.returncode = 1
                result.stderr = "error: Cannot delete branch"
            else:
                result.returncode = 0

            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.git.logger') as mock_logger:
                    manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")

                    # Enter should fail due to worktree creation failure
                    with pytest.raises(RuntimeError) as exc_info:
                        manager.__enter__()

                    # The original error should be raised
                    assert "Failed to create worktree" in str(exc_info.value)

                    # But cleanup failure should ALSO be logged
                    mock_logger.warning.assert_called()
                    logged_message = mock_logger.warning.call_args[0][0]
                    assert "cleanup" in logged_message.lower() or "branch" in logged_message.lower()


class TestCleanupMethod:
    """Tests for public cleanup() method."""

    def test_cleanup_method_calls_internal_cleanup(self):
        """Test cleanup() method calls _cleanup internally."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_path = "/mock/worktree/path"

                result = manager.cleanup()

        # Cleanup should have been called
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        branch_delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]

        assert len(worktree_remove_cmds) > 0, "Should remove worktree"
        assert len(branch_delete_cmds) > 0, "Should delete branch"
        assert result is True, "Cleanup should return True on success"

    def test_cleanup_returns_false_on_failure(self):
        """Test cleanup() returns False when removal fails."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            # All commands fail
            result.returncode = 1
            result.stdout = ""
            result.stderr = "error"
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_path = "/mock/worktree/path"

                result = manager.cleanup()

        assert result is False, "Cleanup should return False on failure"


class TestExitWithNoWorktree:
    """Test __exit__ when worktree was not created."""

    def test_exit_without_worktree_creation(self):
        """Test __exit__ does nothing if worktree wasn't created."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                # _worktree_created defaults to False
                assert manager._worktree_created is False

                # Call __exit__ without having entered context
                result = manager.__exit__(None, None, None)

        # No cleanup commands should have been issued
        worktree_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd)]
        assert len(worktree_cmds) == 0, "Should not call cleanup when worktree not created"
        assert result is False, "__exit__ should return False (not suppress exceptions)"


class TestGitBranchManagerIntegration:
    """Integration tests for GitBranchManager context manager pattern."""

    def test_context_manager_full_lifecycle(self):
        """Test full lifecycle: enter -> work -> exit with cleanup."""
        from ralph2.git import GitBranchManager

        git_commands = []

        def mock_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123") as manager:
                    # Verify worktree was created and path is accessible
                    assert manager.worktree_path is not None

                # After context exits, cleanup should have happened
                worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
                assert len(worktree_remove_cmds) > 0, "Should clean up worktree after context exit"


class TestWorktreePathProperty:
    """Tests for the worktree_path property."""

    def test_worktree_path_is_none_before_enter(self):
        """Test that worktree_path is None before __enter__ is called."""
        from ralph2.git import GitBranchManager

        with patch('os.getcwd', return_value='/mock/repo'):
            manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")

        assert manager.worktree_path is None

    def test_worktree_path_set_after_enter(self):
        """Test that worktree_path is set after __enter__ is called."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager.__enter__()

                assert manager.worktree_path is not None
                assert "ralph-test1" in manager.worktree_path
                assert "run-abc123" in manager.worktree_path


class TestCustomCwd:
    """Tests for custom working directory support."""

    def test_custom_cwd_is_used(self):
        """Test that custom cwd is used for git commands."""
        from ralph2.git import GitBranchManager

        captured_cwd = []

        def mock_run(cmd, *args, **kwargs):
            captured_cwd.append(kwargs.get('cwd'))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        custom_path = "/custom/project/path"
        with patch('subprocess.run', side_effect=mock_run):
            manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123", cwd=custom_path)
            manager.__enter__()

        # All git commands should use the custom cwd
        assert all(cwd == custom_path for cwd in captured_cwd)

    def test_worktree_path_relative_to_custom_cwd(self):
        """Test worktree path is relative to custom cwd."""
        from ralph2.git import GitBranchManager

        custom_path = "/custom/project/path"
        manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123", cwd=custom_path)

        worktree_path = manager.get_worktree_path()

        # Should be sibling directory
        assert worktree_path.startswith("/custom/project/")
        assert "ralph-test1" in worktree_path


class TestExitReturnValue:
    """Tests for __exit__ return value behavior."""

    def test_exit_returns_false_no_exception(self):
        """Test __exit__ returns False when called without exception."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True
                manager._worktree_path = "/mock/worktree"

                result = manager.__exit__(None, None, None)

        assert result is False, "__exit__ should return False (does not suppress exceptions)"

    def test_exit_returns_false_with_exception(self):
        """Test __exit__ returns False when called with exception (doesn't suppress it)."""
        from ralph2.git import GitBranchManager

        def mock_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                manager = GitBranchManager(work_item_id="ralph-test1", run_id="run-abc123")
                manager._worktree_created = True
                manager._worktree_path = "/mock/worktree"

                result = manager.__exit__(ValueError, ValueError("test"), None)

        assert result is False, "__exit__ should return False to propagate exception"
