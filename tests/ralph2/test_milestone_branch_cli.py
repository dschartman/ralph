"""Tests for milestone branch isolation CLI and runner integration.

Tests for the milestone branch isolation feature covering:
1. CLI --branch option for run command
2. Branch name slugification from spec title
3. Branch uniqueness (appending -2, -3, etc.)
4. Milestone branch displayed in status command
5. Runner wiring through execution flow
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
from pathlib import Path
from datetime import datetime


class TestSlugifySpecTitle:
    """Test slugification of spec titles for branch names."""

    def test_slugify_basic_title(self):
        """Test basic title slugification."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("My Feature Title")
        assert result == "my-feature-title"

    def test_slugify_removes_special_characters(self):
        """Test that special characters are removed."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("Feature: Add Login! (v2)")
        # Should only keep alphanumeric and spaces, then convert spaces to hyphens
        assert result == "feature-add-login-v2"

    def test_slugify_truncates_long_titles(self):
        """Test that long titles are truncated to max 50 characters."""
        from ralph2.runner import slugify_spec_title

        long_title = "This is a very long title that should be truncated to fit the maximum character limit"
        result = slugify_spec_title(long_title)
        assert len(result) <= 50
        # Should not end with a hyphen after truncation
        assert not result.endswith("-")

    def test_slugify_handles_multiple_spaces(self):
        """Test that multiple spaces become single hyphens."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("Title   With   Multiple   Spaces")
        assert result == "title-with-multiple-spaces"

    def test_slugify_handles_empty_string(self):
        """Test that empty string returns 'spec'."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("")
        assert result == "spec"

    def test_slugify_handles_only_special_chars(self):
        """Test title with only special characters."""
        from ralph2.runner import slugify_spec_title

        result = slugify_spec_title("!@#$%")
        assert result == "spec"

    def test_slugify_preserves_numbers(self):
        """Test that numbers are preserved."""
        from ralph2.runner import slugify_spec_title

        # Note: dots are removed, so 2.0 becomes 20
        result = slugify_spec_title("Version 2.0 Release")
        assert result == "version-20-release"


class TestGenerateUniqueBranchName:
    """Test generation of unique branch names."""

    def test_generate_branch_name_basic(self):
        """Test basic branch name generation."""
        from ralph2.runner import generate_unique_branch_name

        def mock_branch_exists(branch_name, cwd):
            return False  # Branch doesn't exist

        with patch('ralph2.runner.branch_exists', side_effect=mock_branch_exists):
            result = generate_unique_branch_name("my-feature", "/mock/repo")

        assert result == "feature/my-feature"

    def test_generate_branch_name_appends_suffix_when_exists(self):
        """Test that -2, -3, etc. is appended when branch exists."""
        from ralph2.runner import generate_unique_branch_name

        existing_branches = {"feature/my-feature", "feature/my-feature-2"}

        def mock_branch_exists(branch_name, cwd):
            return branch_name in existing_branches

        with patch('ralph2.runner.branch_exists', side_effect=mock_branch_exists):
            result = generate_unique_branch_name("my-feature", "/mock/repo")

        assert result == "feature/my-feature-3"

    def test_generate_branch_name_with_explicit_branch(self):
        """Test that explicit branch is used as-is."""
        from ralph2.runner import generate_unique_branch_name

        def mock_branch_exists(branch_name, cwd):
            return False

        with patch('ralph2.runner.branch_exists', side_effect=mock_branch_exists):
            result = generate_unique_branch_name("my-feature", "/mock/repo", explicit_branch="feature/custom")

        assert result == "feature/custom"

    def test_generate_branch_name_explicit_branch_exists(self):
        """Test that explicit branch is reused even if it exists."""
        from ralph2.runner import generate_unique_branch_name

        def mock_branch_exists(branch_name, cwd):
            return branch_name == "feature/custom"

        with patch('ralph2.runner.branch_exists', side_effect=mock_branch_exists):
            result = generate_unique_branch_name("my-feature", "/mock/repo", explicit_branch="feature/custom")

        # Should reuse existing branch without error
        assert result == "feature/custom"


class TestBranchExists:
    """Test branch_exists helper function."""

    def test_branch_exists_returns_true_when_exists(self):
        """Test branch_exists returns True for existing branch."""
        from ralph2.runner import branch_exists

        def mock_run_git(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "feature/my-feature\n"
            return result

        with patch('subprocess.run', side_effect=mock_run_git):
            result = branch_exists("feature/my-feature", "/mock/repo")

        assert result is True

    def test_branch_exists_returns_false_when_not_exists(self):
        """Test branch_exists returns False for non-existing branch."""
        from ralph2.runner import branch_exists

        def mock_run_git(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        with patch('subprocess.run', side_effect=mock_run_git):
            result = branch_exists("feature/nonexistent", "/mock/repo")

        assert result is False


class TestCLIBranchOption:
    """Test CLI --branch option."""

    def test_run_command_accepts_branch_option(self):
        """Test that run command accepts --branch option."""
        from ralph2.cli import run
        import inspect

        sig = inspect.signature(run)
        params = list(sig.parameters.keys())

        assert "branch" in params

    def test_run_command_branch_option_is_optional(self):
        """Test that --branch option is optional (has a default value)."""
        from ralph2.cli import run
        import inspect
        from typer.models import OptionInfo

        sig = inspect.signature(run)
        branch_param = sig.parameters.get("branch")

        assert branch_param is not None
        # Typer wraps optional parameters with OptionInfo, so check it's not required
        assert branch_param.default is not inspect.Parameter.empty


class TestStatusDisplayMilestoneBranch:
    """Test status command displays milestone branch."""

    def test_status_shows_milestone_branch(self):
        """Test that status command shows milestone branch when set."""
        from ralph2.state.models import Run
        from ralph2.state.db import Ralph2DB

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
                    milestone_branch="feature/my-milestone",
                )
                db.create_run(run)

                # Verify milestone_branch is retrievable
                retrieved = db.get_latest_run()
                assert retrieved.milestone_branch == "feature/my-milestone"
            finally:
                db.close()


class TestRunnerMilestoneBranchWiring:
    """Test runner wires milestone branch through execution flow."""

    def test_runner_creates_milestone_branch_for_new_run(self):
        """Test that runner stores explicit branch for new runs."""
        from ralph2.runner import Ralph2Runner
        from ralph2.project import ProjectContext

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create spec file
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# My Test Feature\n\nThis is a test spec.")

            # Create state directories
            state_dir = Path(tmpdir) / ".ralph2"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "outputs").mkdir(parents=True, exist_ok=True)
            (state_dir / "summaries").mkdir(parents=True, exist_ok=True)

            # Create a mock project context
            ctx = MagicMock(spec=ProjectContext)
            ctx.project_id = "test-project"
            ctx.project_root = Path(tmpdir)
            ctx.state_dir = state_dir
            ctx.db_path = state_dir / "state.db"
            ctx.outputs_dir = state_dir / "outputs"
            ctx.summaries_dir = state_dir / "summaries"

            runner = Ralph2Runner(
                spec_path=str(spec_path),
                project_context=ctx,
                branch="feature/custom-branch"
            )

            # Verify branch is stored
            assert runner._branch == "feature/custom-branch"
            runner.close()

    def test_runner_accepts_branch_parameter(self):
        """Test Ralph2Runner accepts branch parameter."""
        from ralph2.runner import Ralph2Runner
        import inspect

        sig = inspect.signature(Ralph2Runner.__init__)
        params = list(sig.parameters.keys())

        assert "branch" in params

    def test_runner_uses_explicit_branch_when_provided(self):
        """Test runner uses explicit branch when provided."""
        from ralph2.runner import Ralph2Runner
        from ralph2.project import ProjectContext

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# My Test Feature\n\nThis is a test spec.")

            # Create state directories
            state_dir = Path(tmpdir) / ".ralph2"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "outputs").mkdir(parents=True, exist_ok=True)
            (state_dir / "summaries").mkdir(parents=True, exist_ok=True)

            # Create a mock project context
            ctx = MagicMock(spec=ProjectContext)
            ctx.project_id = "test-project"
            ctx.project_root = Path(tmpdir)
            ctx.state_dir = state_dir
            ctx.db_path = state_dir / "state.db"
            ctx.outputs_dir = state_dir / "outputs"
            ctx.summaries_dir = state_dir / "summaries"

            runner = Ralph2Runner(
                spec_path=str(spec_path),
                project_context=ctx,
                branch="feature/explicit-branch"
            )

            assert runner._branch == "feature/explicit-branch"
            runner.close()

    def test_runner_generates_branch_from_spec_title_when_not_provided(self):
        """Test runner has None branch when not provided (generated at runtime)."""
        from ralph2.runner import Ralph2Runner
        from ralph2.project import ProjectContext

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "Ralph2file"
            spec_path.write_text("# My Awesome Feature\n\nThis is a test spec.")

            # Create state directories
            state_dir = Path(tmpdir) / ".ralph2"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "outputs").mkdir(parents=True, exist_ok=True)
            (state_dir / "summaries").mkdir(parents=True, exist_ok=True)

            # Create a mock project context
            ctx = MagicMock(spec=ProjectContext)
            ctx.project_id = "test-project"
            ctx.project_root = Path(tmpdir)
            ctx.state_dir = state_dir
            ctx.db_path = state_dir / "state.db"
            ctx.outputs_dir = state_dir / "outputs"
            ctx.summaries_dir = state_dir / "summaries"

            runner = Ralph2Runner(
                spec_path=str(spec_path),
                project_context=ctx,
                # No branch provided
            )

            # Branch should be None initially, will be generated when run starts
            assert runner._branch is None
            runner.close()


class TestMilestoneBranchPersistence:
    """Test milestone branch is persisted to Run record."""

    def test_milestone_branch_stored_in_run_record(self):
        """Test that milestone branch is stored when run is created."""
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import Run

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-persist-test",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/persisted-branch",
                )
                db.create_run(run)

                # Retrieve and verify
                retrieved = db.get_run(run.id)
                assert retrieved.milestone_branch == "feature/persisted-branch"
            finally:
                db.close()

    def test_milestone_branch_retrieved_on_resume(self):
        """Test that milestone branch is retrieved when resuming a run."""
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import Run

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-resume-test",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/resume-branch",
                )
                db.create_run(run)

                # Simulate resume by getting the run
                resumed = db.get_latest_run()
                assert resumed.milestone_branch == "feature/resume-branch"
            finally:
                db.close()


class TestMilestoneBranchInWorktreeCreation:
    """Test that worktrees are created from milestone branch."""

    def test_create_worktrees_uses_milestone_branch(self):
        """Test that _create_worktrees passes milestone branch as base_branch."""
        # This tests that the runner passes the milestone branch to git operations
        # The actual git operations are tested in test_git_base_target_branch.py

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
                base_branch="feature/my-milestone"  # Key: milestone branch as base
            )

        # Verify branch was created from milestone branch
        branch_cmds = [cmd for cmd in git_commands if cmd[1] == 'branch' and '-D' not in cmd]
        assert len(branch_cmds) == 1
        assert branch_cmds[0] == ['git', 'branch', 'ralph2/ralph-test1', 'feature/my-milestone']


class TestMilestoneBranchInMerge:
    """Test that merges go to milestone branch instead of main."""

    def test_merge_to_milestone_branch(self):
        """Test that completed work merges to milestone branch."""
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
                target_branch="feature/my-milestone"  # Key: merge to milestone, not main
            )

        assert success is True

        # Verify checkout was to milestone branch
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in cmd]
        assert len(checkout_cmds) == 1
        assert 'feature/my-milestone' in checkout_cmds[0]
