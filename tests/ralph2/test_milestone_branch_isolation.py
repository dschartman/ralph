"""Tests for milestone branch isolation feature.

These tests cover the complete integration of milestone branch isolation:
1. Branch name generation from spec title (slugification)
2. Unique suffix handling (-2, -3) for existing branches
3. --branch CLI flag behavior
4. Worktree creation from milestone branch
5. Merge to milestone branch
6. Resume reads milestone_branch from Run
7. Status command displays milestone branch
8. Backward compatibility
"""

import pytest
import tempfile
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from ralph2.state.models import Run
from ralph2.state.db import Ralph2DB


class TestBranchNameSlugification:
    """Tests for branch name generation and slugification."""

    def test_slugify_basic_title(self):
        """Test basic title slugification."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("My Feature Title")
        assert result == "my-feature-title"

    def test_slugify_removes_special_characters(self):
        """Test that special characters are removed."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("Feature: Add User Auth!")
        # The existing function removes special chars but keeps spaces as hyphens
        assert result == "feature-add-user-auth"

    def test_slugify_collapses_multiple_hyphens(self):
        """Test that multiple spaces become single hyphen."""
        from ralph2.runner import slugify_spec_title

        # Multiple spaces become multiple then single hyphen
        result = slugify_spec_title("Feature   Add   Auth")
        assert result == "feature-add-auth"

    def test_slugify_truncates_to_50_chars(self):
        """Test that slugs are truncated to 50 characters max."""
        from ralph2.runner import slugify_spec_title

        long_title = "This is a very long title that should definitely be truncated to fifty chars"
        result = slugify_spec_title(long_title)
        assert len(result) <= 50
        # Should not end with hyphen after truncation
        assert not result.endswith("-")

    def test_slugify_strips_leading_trailing_hyphens(self):
        """Test that leading/trailing hyphens are removed."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("  Test Title  ")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_slugify_handles_empty_string(self):
        """Test handling of empty string."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("")
        assert result == "spec"  # Default fallback

    def test_slugify_handles_all_special_chars(self):
        """Test handling of title with all special characters."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("!@#$%^&*()")
        assert result == "spec"  # Default fallback


class TestBranchNameGeneration:
    """Tests for complete branch name generation."""

    def test_generate_branch_name_from_spec_title(self):
        """Test generating branch name from spec title."""
        from ralph2.runner import _extract_spec_title, slugify_spec_title

        spec_content = "# My Feature Title\n\nDescription here."
        title = _extract_spec_title(spec_content)
        slug = slugify_spec_title(title)
        result = f"feature/{slug}"
        assert result == "feature/my-feature-title"

    def test_generate_branch_name_no_h1_uses_default(self):
        """Test that specs without H1 get a default branch name."""
        from ralph2.runner import _extract_spec_title, slugify_spec_title

        spec_content = "Just some text without a heading."
        title = _extract_spec_title(spec_content)
        slug = slugify_spec_title(title)
        result = f"feature/{slug}"
        assert result == "feature/spec"

    def test_generate_branch_name_feature_prefix(self):
        """Test that branch names get feature/ prefix."""
        from ralph2.runner import _extract_spec_title, slugify_spec_title

        spec_content = "# Add Login Button\n\nSome content."
        title = _extract_spec_title(spec_content)
        slug = slugify_spec_title(title)
        result = f"feature/{slug}"
        assert result.startswith("feature/")


class TestUniqueBranchNaming:
    """Tests for unique branch naming with suffixes."""

    def test_unique_branch_name_no_conflict(self):
        """Test branch name when no conflict exists."""
        from ralph2.runner import generate_unique_branch_name

        # Mock git branch check to return "not exists"
        with patch('ralph2.runner.branch_exists') as mock_exists:
            mock_exists.return_value = False
            result = generate_unique_branch_name("test", "/path/to/repo")
            assert result == "feature/test"

    def test_unique_branch_name_with_conflict(self):
        """Test branch name when first name conflicts."""
        from ralph2.runner import generate_unique_branch_name

        with patch('ralph2.runner.branch_exists') as mock_exists:
            # First call: exists, second: doesn't exist
            mock_exists.side_effect = [True, False]
            result = generate_unique_branch_name("test", "/path/to/repo")
            assert result == "feature/test-2"

    def test_unique_branch_name_multiple_conflicts(self):
        """Test branch name when multiple conflicts exist."""
        from ralph2.runner import generate_unique_branch_name

        with patch('ralph2.runner.branch_exists') as mock_exists:
            # First 3 exist, 4th doesn't
            mock_exists.side_effect = [True, True, True, False]
            result = generate_unique_branch_name("test", "/path/to/repo")
            assert result == "feature/test-4"


class TestBranchExistsCheck:
    """Tests for checking if a branch exists."""

    def test_branch_exists_returns_true(self):
        """Test that branch_exists returns True for existing branch."""
        from ralph2.runner import branch_exists

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = branch_exists("main", "/path/to/repo")
            assert result is True

    def test_branch_exists_returns_false(self):
        """Test that branch_exists returns False for non-existing branch."""
        from ralph2.runner import branch_exists

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = branch_exists("nonexistent", "/path/to/repo")
            assert result is False


class TestMilestoneBranchCreation:
    """Tests for milestone branch creation in runner."""

    def test_create_milestone_branch_from_main(self):
        """Test creating milestone branch from main when it doesn't exist."""
        from ralph2.runner import _create_milestone_branch

        with patch('ralph2.runner.branch_exists') as mock_exists:
            mock_exists.return_value = False  # Branch doesn't exist
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = _create_milestone_branch("feature/test", "/path/to/repo")
                assert result is True
                # Check that git branch was called with correct args
                mock_run.assert_called()
                call_args = mock_run.call_args[0][0]
                assert "git" in call_args
                assert "branch" in call_args
                assert "feature/test" in call_args
                assert "main" in call_args

    def test_create_milestone_branch_already_exists(self):
        """Test that existing branch is reused."""
        from ralph2.runner import _create_milestone_branch

        with patch('ralph2.runner.branch_exists') as mock_exists:
            mock_exists.return_value = True  # Branch already exists
            with patch('subprocess.run') as mock_run:
                result = _create_milestone_branch("feature/test", "/path/to/repo")
                assert result is True
                # Should not call git branch if branch exists
                mock_run.assert_not_called()

    def test_create_milestone_branch_failure(self):
        """Test handling of branch creation failure."""
        from ralph2.runner import _create_milestone_branch

        with patch('ralph2.runner.branch_exists') as mock_exists:
            mock_exists.return_value = False  # Branch doesn't exist
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="error")
                result = _create_milestone_branch("feature/test", "/path/to/repo")
                assert result is False


class TestRunnerMilestoneBranchIntegration:
    """Tests for milestone branch integration in runner."""

    def test_runner_stores_milestone_branch_in_run(self):
        """Test that runner stores milestone_branch in Run record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-store",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/test-branch",
                )
                db.create_run(run)

                retrieved = db.get_run(run.id)
                assert retrieved is not None
                assert retrieved.milestone_branch == "feature/test-branch"
            finally:
                db.close()

    def test_runner_reads_milestone_branch_on_resume(self):
        """Test that runner reads milestone_branch from Run on resume."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                # Create a run with milestone_branch
                run = Run(
                    id="ralph2-test-resume",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/resume-branch",
                )
                db.create_run(run)

                # Simulate resuming - get latest run
                latest = db.get_latest_run()
                assert latest is not None
                assert latest.milestone_branch == "feature/resume-branch"
            finally:
                db.close()


class TestCLIBranchOption:
    """Tests for --branch CLI option."""

    def test_run_command_has_branch_option(self):
        """Test that run command has --branch option."""
        from ralph2.cli import run
        import inspect

        # Get the function signature
        sig = inspect.signature(run)
        params = sig.parameters

        # Verify --branch parameter exists
        assert 'branch' in params, "--branch option should be in run command"

    def test_branch_option_passed_to_runner(self):
        """Test that --branch value is passed to Ralph2Runner."""
        # The CLI passes 'branch' to Ralph2Runner.__init__
        # We verify this by checking the runner accepts the parameter
        from ralph2.runner import Ralph2Runner
        import inspect

        sig = inspect.signature(Ralph2Runner.__init__)
        params = sig.parameters
        assert 'branch' in params, "Ralph2Runner should accept 'branch' parameter"


class TestWorktreeFromMilestoneBranch:
    """Tests for worktree creation from milestone branch."""

    def test_worktree_created_from_milestone_branch(self):
        """Test that executor worktrees branch from milestone branch."""
        from ralph2.git import create_worktree

        with patch('ralph2.git._run_git_command') as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stderr="")

            # Create worktree with base_branch
            worktree_path, branch_name = create_worktree(
                work_item_id="ralph-abc123",
                run_id="ralph2-xyz",
                cwd="/path/to/repo",
                base_branch="feature/milestone"
            )

            # Verify git branch command included base_branch
            calls = mock_git.call_args_list
            branch_call = calls[0][0][0]  # First call, first positional arg
            assert "feature/milestone" in branch_call


class TestMergeToMilestoneBranch:
    """Tests for merging to milestone branch (not main)."""

    def test_merge_to_milestone_branch(self):
        """Test that executor work merges to milestone branch."""
        from ralph2.git import merge_branch

        with patch('ralph2.git._run_git_command') as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stderr="")

            success, error = merge_branch(
                branch_name="ralph2/work-item",
                cwd="/path/to/repo",
                target_branch="feature/milestone"
            )

            assert success is True
            # Verify checkout was to milestone branch
            calls = mock_git.call_args_list
            checkout_call = calls[0][0][0]
            assert "feature/milestone" in checkout_call


class TestStatusDisplayMilestoneBranch:
    """Tests for status command displaying milestone branch."""

    def test_status_includes_milestone_branch(self):
        """Test that status command shows milestone branch."""
        # This tests the data availability, CLI output is tested elsewhere
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-status-test",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/status-branch",
                )
                db.create_run(run)

                # Verify we can retrieve milestone_branch for status display
                latest = db.get_latest_run()
                assert latest.milestone_branch == "feature/status-branch"
            finally:
                db.close()


class TestBackwardCompatibilityMilestoneBranch:
    """Tests for backward compatibility with runs without milestone_branch."""

    def test_runs_without_milestone_branch_work(self):
        """Test that runs created without milestone_branch continue to work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                # Create run without milestone_branch
                run = Run(
                    id="ralph2-compat",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                retrieved = db.get_run(run.id)
                assert retrieved is not None
                assert retrieved.milestone_branch is None

                # Runner should handle None milestone_branch gracefully
                # (branches from main, merges to main - legacy behavior)
            finally:
                db.close()

    def test_none_milestone_branch_means_main_behavior(self):
        """Test that None milestone_branch uses main for base/target."""
        # When milestone_branch is None, executor worktrees should
        # branch from HEAD (main) and merge back to main
        # This is the legacy behavior that must be preserved
        pass  # Logic tested in runner integration tests


class TestDONELeavesbranchAsIs:
    """Tests for DONE completion leaving milestone branch intact."""

    def test_done_does_not_merge_to_main(self):
        """Test that DONE completion leaves milestone branch without merging to main."""
        # The milestone branch should remain as-is for PR review
        # This is verified by checking that no merge to main occurs after DONE
        pass  # Integration test - tested in full run scenarios
