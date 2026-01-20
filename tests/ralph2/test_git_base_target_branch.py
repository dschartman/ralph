"""Tests for git.py base_branch and target_branch parameters.

This module tests the milestone branch isolation feature where:
- Executors branch FROM the milestone branch (not main)
- Executors merge TO the milestone branch (not main)
"""

import pytest
from unittest.mock import MagicMock, patch


class TestCreateWorktreeBaseBranch:
    """Test create_worktree with base_branch parameter."""

    def test_create_worktree_defaults_to_current_head(self):
        """Test create_worktree branches from current HEAD by default."""
        from ralph2.git import create_worktree

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            worktree_path, branch_name = create_worktree(
                work_item_id="ralph-test1",
                run_id="run-abc123",
                cwd="/mock/repo"
            )

        # Default behavior: create branch from current HEAD (no start-point arg)
        branch_cmds = [cmd for cmd in git_commands if cmd[1] == 'branch' and '-D' not in cmd]
        assert len(branch_cmds) == 1
        # Should be: git branch <branch_name> (no start-point)
        assert branch_cmds[0] == ['git', 'branch', 'ralph2/ralph-test1']

    def test_create_worktree_with_base_branch(self):
        """Test create_worktree branches from specified base_branch."""
        from ralph2.git import create_worktree

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            worktree_path, branch_name = create_worktree(
                work_item_id="ralph-test1",
                run_id="run-abc123",
                cwd="/mock/repo",
                base_branch="feature/milestone-xyz"
            )

        # Should create branch FROM the specified base_branch
        branch_cmds = [cmd for cmd in git_commands if cmd[1] == 'branch' and '-D' not in cmd]
        assert len(branch_cmds) == 1
        # Should be: git branch <branch_name> <start-point>
        assert branch_cmds[0] == ['git', 'branch', 'ralph2/ralph-test1', 'feature/milestone-xyz']

    def test_create_worktree_with_main_as_base_branch(self):
        """Test create_worktree with explicit main as base_branch."""
        from ralph2.git import create_worktree

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            worktree_path, branch_name = create_worktree(
                work_item_id="ralph-test1",
                run_id="run-abc123",
                cwd="/mock/repo",
                base_branch="main"
            )

        # Should create branch FROM main
        branch_cmds = [cmd for cmd in git_commands if cmd[1] == 'branch' and '-D' not in cmd]
        assert len(branch_cmds) == 1
        assert branch_cmds[0] == ['git', 'branch', 'ralph2/ralph-test1', 'main']


class TestMergeBranchTargetBranch:
    """Test merge_branch with target_branch parameter (replaces merge_branch_to_main)."""

    def test_merge_branch_defaults_to_main(self):
        """Test merge_branch merges to main by default."""
        from ralph2.git import merge_branch

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            success, error = merge_branch(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo"
            )

        assert success is True
        assert error == ""

        # Verify checkout main was called
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in cmd]
        assert len(checkout_cmds) == 1
        assert 'main' in checkout_cmds[0]

    def test_merge_branch_with_target_branch(self):
        """Test merge_branch merges to specified target_branch."""
        from ralph2.git import merge_branch

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            success, error = merge_branch(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo",
                target_branch="feature/milestone-xyz"
            )

        assert success is True
        assert error == ""

        # Verify checkout of milestone branch was called
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in cmd]
        assert len(checkout_cmds) == 1
        assert 'feature/milestone-xyz' in checkout_cmds[0]

    def test_merge_branch_handles_conflict(self):
        """Test merge_branch handles merge conflict."""
        from ralph2.git import merge_branch

        def mock_run_git(cmd, cwd):
            result = MagicMock()
            if 'checkout' in cmd:
                result.returncode = 0
            elif 'merge' in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT in file.py"
            elif 'status' in cmd:
                result.returncode = 0
                result.stdout = "UU file.py"
            else:
                result.returncode = 0
            result.stdout = getattr(result, 'stdout', "")
            result.stderr = getattr(result, 'stderr', "")
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            success, error = merge_branch(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo",
                target_branch="feature/milestone-xyz"
            )

        assert success is False
        assert "conflict" in error.lower() or "file.py" in error.lower()

    def test_merge_branch_checkout_failure(self):
        """Test merge_branch handles checkout failure."""
        from ralph2.git import merge_branch

        def mock_run_git(cmd, cwd):
            result = MagicMock()
            if 'checkout' in cmd:
                result.returncode = 1
                result.stderr = "branch not found"
            else:
                result.returncode = 0
            result.stdout = ""
            result.stderr = getattr(result, 'stderr', "")
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            success, error = merge_branch(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo",
                target_branch="feature/milestone-xyz"
            )

        assert success is False
        assert "checkout" in error.lower() or "feature/milestone-xyz" in error


class TestMergeBranchToMainBackwardCompatibility:
    """Test that merge_branch_to_main still works for backward compatibility."""

    def test_merge_branch_to_main_still_works(self):
        """Test merge_branch_to_main is still available and works."""
        from ralph2.git import merge_branch_to_main

        git_commands = []

        def mock_run_git(cmd, cwd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_run_git):
            success, error = merge_branch_to_main(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo"
            )

        assert success is True
        assert error == ""

        # Should still merge to main
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in cmd]
        assert len(checkout_cmds) == 1
        assert 'main' in checkout_cmds[0]


class TestGitBranchManagerBaseBranch:
    """Test GitBranchManager with base_branch parameter."""

    def test_init_with_base_branch(self):
        """Test GitBranchManager can accept base_branch parameter."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            base_branch="feature/milestone-xyz"
        )
        assert manager._base_branch == "feature/milestone-xyz"

    def test_init_default_base_branch(self):
        """Test GitBranchManager defaults to None base_branch (current HEAD)."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc"
        )
        assert manager._base_branch is None

    def test_enter_creates_branch_from_base_branch(self):
        """Test __enter__ creates branch from specified base_branch."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project",
            base_branch="feature/milestone-xyz"
        )

        git_commands = []

        def mock_run_git(cmd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch.object(manager, "_run_git", side_effect=mock_run_git):
            manager.__enter__()

        # First command should create branch from base_branch
        branch_cmd = git_commands[0]
        assert 'branch' in branch_cmd
        assert 'ralph2/ralph-123' in branch_cmd
        assert 'feature/milestone-xyz' in branch_cmd


class TestGitBranchManagerMergeToTarget:
    """Test GitBranchManager merge_to_target method."""

    def test_merge_to_target_with_target_branch(self):
        """Test merge_to_target merges to specified target branch."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        git_commands = []

        def mock_run_git(cmd):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch.object(manager, "_run_git", side_effect=mock_run_git):
            success, error = manager.merge_to_target(target_branch="feature/milestone-xyz")

        assert success is True
        assert error == ""

        # Should checkout target branch
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in cmd]
        assert 'feature/milestone-xyz' in checkout_cmds[0]

    def test_merge_to_main_calls_merge_to_target(self):
        """Test merge_to_main is equivalent to merge_to_target(target_branch='main')."""
        from ralph2.git import GitBranchManager

        manager = GitBranchManager(
            work_item_id="ralph-123",
            run_id="run-abc",
            cwd="/test/project"
        )

        git_commands_main = []
        git_commands_target = []

        def mock_run_git(cmd):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with patch.object(manager, "_run_git", side_effect=mock_run_git) as mock_git:
            success1, error1 = manager.merge_to_main()

        with patch.object(manager, "_run_git", side_effect=mock_run_git) as mock_git:
            success2, error2 = manager.merge_to_target(target_branch="main")

        # Both should succeed
        assert success1 == success2
        assert error1 == error2
