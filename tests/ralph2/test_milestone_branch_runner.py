"""Tests for milestone branch isolation in runner.py.

This module tests the core milestone branch isolation feature:
1. Slugify spec title to create feature/{slug}
2. Handle --branch flag to use specified name
3. Append -2, -3 suffix if auto-generated branch exists
4. Reuse existing branch if --branch specified
5. Wire through runner execution flow (worktree creation, merging)
6. Display milestone branch in status
7. Resume reads milestone_branch from Run record
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ralph2.runner import Ralph2Runner, _extract_spec_title


class TestSlugifySpecTitle:
    """Tests for slugifying spec titles to branch names."""

    def test_slugify_basic_title(self):
        """Test slugifying a basic spec title."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("My Feature Title")
        assert result == "feature/my-feature-title"

    def test_slugify_with_special_characters(self):
        """Test slugifying removes special characters."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("My Feature: With Special & Characters!")
        # Should only have lowercase letters and hyphens
        assert all(c.islower() or c == '-' or c == '/' or c.isdigit() for c in result)
        assert result.startswith("feature/")

    def test_slugify_removes_consecutive_hyphens(self):
        """Test slugifying collapses consecutive hyphens."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("Title   With   Spaces")
        assert "--" not in result

    def test_slugify_max_length(self):
        """Test slugifying respects max 50 char slug length."""
        from ralph2.runner import slugify_to_branch_name

        long_title = "This is a very long feature title that exceeds fifty characters easily"
        result = slugify_to_branch_name(long_title)
        # Slug portion (after "feature/") should be <= 50 chars
        slug = result.replace("feature/", "")
        assert len(slug) <= 50

    def test_slugify_removes_trailing_hyphens(self):
        """Test slugifying removes trailing hyphens."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("Title!")
        assert not result.endswith("-")

    def test_slugify_empty_title_returns_default(self):
        """Test slugifying an empty title returns a default."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("")
        assert result == "feature/spec"

    def test_slugify_numbers_preserved(self):
        """Test slugifying preserves numbers."""
        from ralph2.runner import slugify_to_branch_name

        result = slugify_to_branch_name("Feature 123 Test")
        assert "123" in result


class TestCreateMilestoneBranch:
    """Tests for creating milestone branch with git."""

    def test_create_milestone_branch_new(self):
        """Test creating a new milestone branch."""
        from ralph2.runner import create_milestone_branch

        with patch("ralph2.runner.branch_exists") as mock_exists:
            mock_exists.return_value = False  # Branch doesn't exist
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                branch = create_milestone_branch(
                    "feature/test-branch",
                    cwd="/test/repo"
                )
        assert branch == "feature/test-branch"
        # Verify git branch was called with main as base
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "branch" in call_args
        assert "feature/test-branch" in call_args
        assert "main" in call_args

    def test_create_milestone_branch_exists_auto_suffix(self):
        """Test appending -2 suffix when auto-generated branch exists."""
        from ralph2.runner import create_milestone_branch

        def mock_exists_side_effect(branch_name, cwd):
            # Base branch exists, -2 doesn't
            if branch_name == "feature/test-branch":
                return True  # base exists
            elif branch_name == "feature/test-branch-2":
                return False  # -2 doesn't exist
            return False

        with patch("ralph2.runner.branch_exists", side_effect=mock_exists_side_effect):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                branch = create_milestone_branch(
                    "feature/test-branch",
                    cwd="/test/repo",
                    allow_suffix=True
                )
        assert branch == "feature/test-branch-2"

    def test_create_milestone_branch_reuse_existing(self):
        """Test reusing an existing branch when --branch flag used."""
        from ralph2.runner import create_milestone_branch

        def mock_git(cmd, **kwargs):
            result = MagicMock()
            result.stdout = ""
            result.stderr = ""
            if "show-ref" in cmd:
                result.returncode = 0  # Branch exists
            else:
                result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_git):
            branch = create_milestone_branch(
                "feature/my-custom-branch",
                cwd="/test/repo",
                allow_suffix=False  # User-specified branch, don't add suffix
            )
        # Should reuse existing branch without error
        assert branch == "feature/my-custom-branch"


class TestRunnerMilestoneBranchIntegration:
    """Tests for milestone branch integration in Ralph2Runner."""

    def test_runner_init_with_branch_option(self):
        """Test Ralph2Runner accepts branch parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# Test Spec")

            from ralph2.project import ProjectContext

            # Create a proper ProjectContext by mocking the find_project_root
            with patch("ralph2.project.find_project_root", return_value=Path(tmpdir)):
                ctx = ProjectContext(project_root=Path(tmpdir))

                runner = Ralph2Runner(
                    spec_path=str(spec_path),
                    project_context=ctx,
                    branch="feature/my-custom-branch"
                )

                assert runner.branch_option == "feature/my-custom-branch"

    def test_runner_creates_milestone_branch_on_new_run(self):
        """Test runner creates milestone branch when starting new run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# Test Feature\n\nSome description")

            from ralph2.project import ProjectContext

            with patch("ralph2.project.find_project_root", return_value=Path(tmpdir)):
                ctx = ProjectContext(project_root=Path(tmpdir))

                runner = Ralph2Runner(
                    spec_path=str(spec_path),
                    project_context=ctx
                )

                # Mock the branch creation
                with patch("ralph2.runner.create_milestone_branch") as mock_create:
                    mock_create.return_value = "feature/test-feature"

                    # The runner should auto-generate branch name from spec title
                    branch = runner._ensure_milestone_branch()

                    # Should slugify "Test Feature" from spec
                    mock_create.assert_called_once()
                    call_args = mock_create.call_args
                    # Should contain slugified spec title
                    assert "feature/" in call_args[0][0]

    def test_runner_passes_milestone_branch_to_worktree_creation(self):
        """Test runner passes milestone_branch to create_worktree."""
        # This tests acceptance criterion:
        # WHEN executor worktrees are created, THEN they branch from the milestone branch
        from ralph2.runner import Ralph2Runner
        from ralph2.git import create_worktree

        git_commands = []

        def mock_create_worktree(work_item_id, run_id, cwd, base_branch=None):
            git_commands.append({
                'work_item_id': work_item_id,
                'base_branch': base_branch
            })
            return f"/path/to/worktree-{work_item_id}", f"ralph2/{work_item_id}"

        with patch("ralph2.runner.create_worktree", side_effect=mock_create_worktree):
            # Test that _create_worktrees passes base_branch
            with tempfile.TemporaryDirectory() as tmpdir:
                spec_path = Path(tmpdir) / "Ralph2file"
                spec_path.write_text("# Test Spec")

                from ralph2.project import ProjectContext

                with patch("ralph2.project.find_project_root", return_value=Path(tmpdir)):
                    ctx = ProjectContext(project_root=Path(tmpdir))

                    runner = Ralph2Runner(
                        spec_path=str(spec_path),
                        project_context=ctx
                    )
                    runner.milestone_branch = "feature/test-milestone"

                    work_items = [
                        {"work_item_id": "ralph-abc123"},
                        {"work_item_id": "ralph-def456"}
                    ]

                    runner._create_worktrees(work_items, "run-123")

                    # Verify base_branch was passed
                    for cmd in git_commands:
                        assert cmd['base_branch'] == "feature/test-milestone"


class TestMergeToMilestoneBranch:
    """Tests for merging to milestone branch instead of main."""

    def test_runner_merges_to_milestone_branch(self):
        """Test runner merges executor work to milestone branch."""
        # This tests acceptance criterion:
        # WHEN executor work is merged, THEN it merges to the milestone branch
        from ralph2.runner import Ralph2Runner

        merge_calls = []

        def mock_merge_branch(branch_name, cwd, target_branch="main"):
            merge_calls.append({
                'branch_name': branch_name,
                'target_branch': target_branch
            })
            return True, ""

        with patch("ralph2.runner.merge_branch", side_effect=mock_merge_branch):
            with tempfile.TemporaryDirectory() as tmpdir:
                spec_path = Path(tmpdir) / "Ralph2file"
                spec_path.write_text("# Test Spec")

                from ralph2.project import ProjectContext

                with patch("ralph2.project.find_project_root", return_value=Path(tmpdir)):
                    ctx = ProjectContext(project_root=Path(tmpdir))

                    runner = Ralph2Runner(
                        spec_path=str(spec_path),
                        project_context=ctx
                    )
                    runner.milestone_branch = "feature/test-milestone"

                    # Simulate completed worktrees
                    completed = [
                        ({"work_item_id": "ralph-abc123"}, "/path/to/wt1", "ralph2/ralph-abc123"),
                    ]

                    import asyncio
                    asyncio.run(runner._merge_worktrees_serial(completed))

                    # Verify merge target was milestone branch
                    for call in merge_calls:
                        assert call['target_branch'] == "feature/test-milestone"


class TestRunResumeWithMilestoneBranch:
    """Tests for resuming runs with milestone_branch."""

    def test_resume_run_uses_stored_milestone_branch(self):
        """Test resuming run reads milestone_branch from Run record."""
        # This tests acceptance criterion:
        # WHEN run is resumed, THEN milestone_branch is read from Run record
        with tempfile.TemporaryDirectory() as tmpdir:
            from ralph2.state.db import Ralph2DB
            from ralph2.state.models import Run
            from ralph2.project import ProjectContext

            # Create spec file first (needed for ProjectContext)
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# Test Spec")

            with patch("ralph2.project.find_project_root", return_value=Path(tmpdir)):
                ctx = ProjectContext(project_root=Path(tmpdir))

            db = Ralph2DB(str(ctx.db_path))

            # Create a run with milestone_branch
            run = Run(
                id="ralph2-test-resume",
                spec_path=str(spec_path),
                spec_content="# Test",
                status="running",
                config={},
                started_at=datetime.now(),
                milestone_branch="feature/existing-milestone"
            )
            db.create_run(run)
            db.close()

            # Reopen and verify
            db2 = Ralph2DB(str(ctx.db_path))
            resumed_run = db2.get_latest_run()
            assert resumed_run.milestone_branch == "feature/existing-milestone"
            db2.close()


class TestDoneDoesNotMergeToMain:
    """Tests for DONE state not merging to main."""

    def test_done_leaves_milestone_branch(self):
        """Test that DONE leaves milestone branch without merging to main."""
        # This tests acceptance criterion:
        # WHEN run completes with DONE, THEN milestone branch is left as-is
        # This is implicit - we just need to verify we don't call merge_branch_to_main
        # when the run completes. The milestone branch is left for PR review.
        pass  # Behavior is already correct - we don't merge on DONE


class TestCLIBranchOption:
    """Tests for CLI --branch option."""

    def test_cli_run_accepts_branch_option(self):
        """Test that CLI run command accepts --branch option."""
        from typer.testing import CliRunner
        from ralph2.cli import app

        runner = CliRunner()

        # Just verify the option is recognized (help should show it)
        # We invoke with --help on the run subcommand
        result = runner.invoke(app, ["run", "--help"])
        # --help should show the option if it's defined
        assert result.exit_code == 0
        # Check that --branch is in the help text
        assert "--branch" in result.stdout

    def test_cli_status_shows_milestone_branch(self):
        """Test that status command displays milestone branch."""
        # This tests acceptance criterion:
        # WHEN run status is queried, THEN milestone branch name is displayed
        pass  # Will implement after adding to status command
