"""Tests for SODA Runner data structures and orchestration functions."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from soda.runner import (
    BootstrapError,
    BootstrapResult,
    IterationResult,
    MilestoneContext,
    MilestoneError,
    RunContext,
    RunResult,
    bootstrap,
    complete_run,
    extract_spec_title,
    run_iteration,
    run_loop,
    setup_milestone,
    _build_iteration_history,
    _build_done_summary,
    _build_run_summary,
    _build_stuck_summary,
    _build_max_iterations_summary,
    _detect_kickstart,
    _ensure_git_has_commits,
    _generate_milestone_branch_name,
    _print_completion_message,
)
from soda.decide import Decision, DecisionOutcome
from soda.orient import (
    Confidence,
    Gap,
    GapSeverity,
    IterationPlan,
    OrientOutput,
    PlannedTask,
    SpecSatisfied,
)
from soda.act import ActOutput, BlockedTask
from soda.state.models import IterationOutcome
from soda.state.git import GitClient, GitError


# =============================================================================
# Bootstrap Tests
# =============================================================================


class TestBootstrapResult:
    """Tests for BootstrapResult model."""

    def test_bootstrap_result_creation(self):
        """BootstrapResult can be created with all fields."""
        result = BootstrapResult(
            project_id="abc-123",
            spec_content="# My Spec",
            is_new_project=True,
            is_kickstart=False,
        )
        assert result.project_id == "abc-123"
        assert result.spec_content == "# My Spec"
        assert result.is_new_project is True
        assert result.is_kickstart is False

    def test_bootstrap_result_json_serializable(self):
        """BootstrapResult can be serialized to JSON."""
        result = BootstrapResult(
            project_id="test-id",
            spec_content="spec",
            is_new_project=False,
            is_kickstart=True,
        )
        data = result.model_dump(mode="json")
        assert data["project_id"] == "test-id"
        assert data["is_kickstart"] is True


class TestDetectKickstart:
    """Tests for _detect_kickstart function."""

    def test_kickstart_empty_directory(self):
        """Empty directory is detected as kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _detect_kickstart(Path(tmpdir))
            assert result is True

    def test_not_kickstart_with_pyproject(self):
        """Directory with pyproject.toml is not kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pyproject.toml").write_text("[project]")
            result = _detect_kickstart(Path(tmpdir))
            assert result is False

    def test_not_kickstart_with_package_json(self):
        """Directory with package.json is not kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").write_text("{}")
            result = _detect_kickstart(Path(tmpdir))
            assert result is False

    def test_not_kickstart_with_cargo_toml(self):
        """Directory with Cargo.toml is not kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Cargo.toml").write_text("[package]")
            result = _detect_kickstart(Path(tmpdir))
            assert result is False

    def test_not_kickstart_with_src_dir(self):
        """Directory with src/ is not kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir()
            result = _detect_kickstart(Path(tmpdir))
            assert result is False

    def test_kickstart_with_readme_only(self):
        """Directory with only README is still kickstart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "README.md").write_text("# Hello")
            result = _detect_kickstart(Path(tmpdir))
            assert result is True


class TestEnsureGitHasCommits:
    """Tests for _ensure_git_has_commits function."""

    def test_creates_commit_when_no_commits(self):
        """Creates initial commit when repo has no commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo without any commits
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])

            # Should create initial commit
            created = _ensure_git_has_commits(git, Path(tmpdir))
            assert created is True

            # Verify commit exists now
            result = git._run_git(["rev-parse", "HEAD"], check=False)
            assert result.returncode == 0

    def test_does_nothing_when_commits_exist(self):
        """Does nothing when repo already has commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo with a commit
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Existing commit"])

            # Should not create new commit
            created = _ensure_git_has_commits(git, Path(tmpdir))
            assert created is False


class TestBootstrap:
    """Tests for bootstrap function."""

    @pytest.mark.asyncio
    async def test_bootstrap_success(self):
        """bootstrap succeeds with valid git repo and spec file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo with initial commit
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# My Spec\n\n- [ ] Criterion 1")

            result = await bootstrap(tmpdir, str(spec_path))

            assert result.project_id is not None
            assert result.spec_content == "# My Spec\n\n- [ ] Criterion 1"
            assert result.is_new_project is True  # First time
            assert result.is_kickstart is True  # No code structure

            # Verify .soda-id was created
            assert (project_root / ".soda-id").exists()

    @pytest.mark.asyncio
    async def test_bootstrap_not_new_project_on_second_run(self):
        """bootstrap returns is_new_project=False on subsequent runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# Spec")

            # First run
            result1 = await bootstrap(tmpdir, str(spec_path))
            assert result1.is_new_project is True

            # Second run
            result2 = await bootstrap(tmpdir, str(spec_path))
            assert result2.is_new_project is False
            assert result1.project_id == result2.project_id

    @pytest.mark.asyncio
    async def test_bootstrap_fails_no_git_repo(self):
        """bootstrap raises error when not a git repo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "Sodafile"
            spec_path.write_text("# Spec")

            with pytest.raises(BootstrapError) as exc_info:
                await bootstrap(tmpdir, str(spec_path))

            assert "Not a git repository" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bootstrap_fails_no_spec_file(self):
        """bootstrap raises error when spec file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            with pytest.raises(BootstrapError) as exc_info:
                await bootstrap(tmpdir, "Sodafile")

            assert "Spec file not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bootstrap_fails_empty_spec(self):
        """bootstrap raises error when spec file is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create empty Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("")

            with pytest.raises(BootstrapError) as exc_info:
                await bootstrap(tmpdir, str(spec_path))

            assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_bootstrap_adds_soda_id_to_gitignore(self):
        """bootstrap adds .soda-id to .gitignore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# Spec")

            await bootstrap(tmpdir, str(spec_path))

            # Verify .gitignore contains .soda-id
            gitignore = project_root / ".gitignore"
            assert gitignore.exists()
            assert ".soda-id" in gitignore.read_text()

    @pytest.mark.asyncio
    async def test_bootstrap_not_kickstart_with_code_structure(self):
        """bootstrap returns is_kickstart=False when project has structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create project structure
            (project_root / "pyproject.toml").write_text("[project]")
            (project_root / "src").mkdir()

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# Spec")

            result = await bootstrap(tmpdir, str(spec_path))

            assert result.is_kickstart is False

    @pytest.mark.asyncio
    async def test_bootstrap_creates_initial_commit_if_needed(self):
        """bootstrap creates initial commit when repo has none."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo WITHOUT any commits
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# Spec")

            await bootstrap(tmpdir, str(spec_path))

            # Verify a commit now exists
            result = git._run_git(["rev-parse", "HEAD"])
            assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_bootstrap_relative_spec_path(self):
        """bootstrap handles relative spec path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create git repo
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Create Sodafile
            spec_path = project_root / "Sodafile"
            spec_path.write_text("# Spec")

            # Use relative path
            result = await bootstrap(tmpdir, "Sodafile")

            assert result.spec_content == "# Spec"


# =============================================================================
# Milestone Phase Tests
# =============================================================================


class TestMilestoneContext:
    """Tests for MilestoneContext model."""

    def test_milestone_context_creation(self):
        """MilestoneContext can be created with all fields."""
        ctx = MilestoneContext(
            milestone_branch="soda/milestone-abc123",
            root_work_item_id="ralph-xyz789",
            is_resumed=False,
        )
        assert ctx.milestone_branch == "soda/milestone-abc123"
        assert ctx.root_work_item_id == "ralph-xyz789"
        assert ctx.is_resumed is False

    def test_milestone_context_resumed(self):
        """MilestoneContext can indicate resumed state."""
        ctx = MilestoneContext(
            milestone_branch="soda/milestone-abc123",
            root_work_item_id="ralph-xyz789",
            is_resumed=True,
        )
        assert ctx.is_resumed is True

    def test_milestone_context_json_serializable(self):
        """MilestoneContext can be serialized to JSON."""
        ctx = MilestoneContext(
            milestone_branch="soda/milestone-test",
            root_work_item_id="ralph-test",
        )
        data = ctx.model_dump(mode="json")
        assert data["milestone_branch"] == "soda/milestone-test"
        assert data["root_work_item_id"] == "ralph-test"


class TestExtractSpecTitle:
    """Tests for extract_spec_title function."""

    def test_extracts_first_h1(self):
        """Extracts title from first H1 heading."""
        spec = "# My Great Project\n\nSome description"
        assert extract_spec_title(spec) == "My Great Project"

    def test_extracts_first_h1_with_multiple_headings(self):
        """Extracts first H1 even when multiple headings exist."""
        spec = "# First Title\n\n## Section\n\n# Second Title"
        assert extract_spec_title(spec) == "First Title"

    def test_falls_back_to_default(self):
        """Returns default when no H1 found."""
        spec = "No headings here\n\nJust text"
        assert extract_spec_title(spec) == "SODA Work Item"

    def test_handles_empty_spec(self):
        """Returns default for empty spec."""
        assert extract_spec_title("") == "SODA Work Item"

    def test_handles_h2_only(self):
        """Returns default when only H2 headings exist."""
        spec = "## Not H1\n\nContent"
        assert extract_spec_title(spec) == "SODA Work Item"

    def test_strips_whitespace(self):
        """Strips whitespace from extracted title."""
        spec = "#   Spaced Title   \n\nContent"
        assert extract_spec_title(spec) == "Spaced Title"


class TestGenerateMilestoneBranchName:
    """Tests for _generate_milestone_branch_name function."""

    def test_generates_branch_name(self):
        """Generates a branch name with soda/milestone- prefix."""
        branch = _generate_milestone_branch_name("# Test Spec")
        assert branch.startswith("soda/milestone-")
        assert len(branch) == len("soda/milestone-") + 8  # 8 char hash

    def test_same_spec_same_branch(self):
        """Same spec content generates same branch name."""
        spec = "# My Spec\n\nContent"
        branch1 = _generate_milestone_branch_name(spec)
        branch2 = _generate_milestone_branch_name(spec)
        assert branch1 == branch2

    def test_different_spec_different_branch(self):
        """Different spec content generates different branch name."""
        branch1 = _generate_milestone_branch_name("# Spec A")
        branch2 = _generate_milestone_branch_name("# Spec B")
        assert branch1 != branch2


class TestSetupMilestone:
    """Tests for setup_milestone function."""

    @pytest.mark.asyncio
    async def test_setup_milestone_creates_branch_and_work_item(self):
        """setup_milestone creates new branch and work item."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create git repo with initial commit
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Mock trace client
            trace_client = MagicMock()
            trace_client.create_task.return_value = "ralph-abc123"

            # Mock db
            db = MagicMock()
            db.get_run.return_value = None

            spec_content = "# My Feature\n\n- [ ] Do something"

            result = await setup_milestone(
                project_id="test-project",
                spec_content=spec_content,
                git_client=git,
                trace_client=trace_client,
                db=db,
            )

            assert result.milestone_branch.startswith("soda/milestone-")
            assert result.root_work_item_id == "ralph-abc123"
            assert result.is_resumed is False

            # Verify trace was called with correct title
            trace_client.create_task.assert_called_once()
            call_args = trace_client.create_task.call_args
            assert call_args.kwargs["title"] == "My Feature"

    @pytest.mark.asyncio
    async def test_setup_milestone_reuses_existing_on_resume(self):
        """setup_milestone reuses existing branch and work item on resume."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create git repo with milestone branch already existing
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])
            git._run_git(["branch", "soda/milestone-existing"])

            # Mock trace client (should not be called on resume)
            trace_client = MagicMock()

            # Mock db with existing run
            db = MagicMock()
            existing_run = MagicMock()
            existing_run.milestone_branch = "soda/milestone-existing"
            existing_run.root_work_item_id = "ralph-existing"
            db.get_run.return_value = existing_run

            result = await setup_milestone(
                project_id="test-project",
                spec_content="# Spec",
                git_client=git,
                trace_client=trace_client,
                db=db,
                run_id="run-123",
            )

            assert result.milestone_branch == "soda/milestone-existing"
            assert result.root_work_item_id == "ralph-existing"
            assert result.is_resumed is True

            # Verify trace was NOT called (reusing existing)
            trace_client.create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_milestone_continues_without_trace(self):
        """setup_milestone continues if trace fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Mock trace client that fails
            trace_client = MagicMock()
            trace_client.create_task.side_effect = Exception("Trace unavailable")

            db = MagicMock()
            db.get_run.return_value = None

            result = await setup_milestone(
                project_id="test-project",
                spec_content="# Spec",
                git_client=git,
                trace_client=trace_client,
                db=db,
            )

            # Should still return valid result with empty work item
            assert result.milestone_branch.startswith("soda/milestone-")
            assert result.root_work_item_id == ""
            assert result.is_resumed is False

    @pytest.mark.asyncio
    async def test_setup_milestone_checks_out_branch(self):
        """setup_milestone checks out the milestone branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            trace_client = MagicMock()
            trace_client.create_task.return_value = "ralph-123"

            db = MagicMock()
            db.get_run.return_value = None

            result = await setup_milestone(
                project_id="test-project",
                spec_content="# Spec",
                git_client=git,
                trace_client=trace_client,
                db=db,
            )

            # Verify we're on the milestone branch
            current_branch = git.get_current_branch()
            assert current_branch == result.milestone_branch

    @pytest.mark.asyncio
    async def test_setup_milestone_handles_branch_conflict(self):
        """setup_milestone handles branch name conflicts with suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git = GitClient(cwd=tmpdir)
            git._run_git(["init"])
            git._run_git(["commit", "--allow-empty", "-m", "Initial"])

            # Pre-create a branch that would conflict
            spec_content = "# Spec"
            expected_branch = _generate_milestone_branch_name(spec_content)
            git._run_git(["branch", expected_branch])

            trace_client = MagicMock()
            trace_client.create_task.return_value = "ralph-123"

            db = MagicMock()
            db.get_run.return_value = None

            result = await setup_milestone(
                project_id="test-project",
                spec_content=spec_content,
                git_client=git,
                trace_client=trace_client,
                db=db,
            )

            # Should have created a branch with -2 suffix
            assert result.milestone_branch == f"{expected_branch}-2"


# =============================================================================
# RunContext Tests
# =============================================================================


class TestRunContext:
    """Tests for RunContext model."""

    def test_run_context_creation_minimal(self):
        """RunContext can be created with required fields."""
        ctx = RunContext(
            project_id="test-project-123",
            spec_content="# Test Spec\n\n- [ ] Criterion 1",
            milestone_branch="feature/test",
            run_id="run-abc123",
        )
        assert ctx.project_id == "test-project-123"
        assert ctx.spec_content == "# Test Spec\n\n- [ ] Criterion 1"
        assert ctx.milestone_branch == "feature/test"
        assert ctx.run_id == "run-abc123"
        assert ctx.max_iterations == 20  # Default
        assert ctx.root_work_item_id is None
        assert ctx.working_directory is None
        assert ctx.milestone_base is None

    def test_run_context_creation_full(self):
        """RunContext can be created with all fields."""
        ctx = RunContext(
            project_id="test-project-123",
            spec_content="# Test Spec",
            milestone_branch="feature/test",
            run_id="run-abc123",
            root_work_item_id="ralph-abc123",
            max_iterations=50,
            working_directory="/path/to/project",
            milestone_base="abc123def",
        )
        assert ctx.root_work_item_id == "ralph-abc123"
        assert ctx.max_iterations == 50
        assert ctx.working_directory == "/path/to/project"
        assert ctx.milestone_base == "abc123def"

    def test_run_context_max_iterations_minimum(self):
        """max_iterations must be at least 1."""
        with pytest.raises(ValidationError):
            RunContext(
                project_id="test",
                spec_content="spec",
                milestone_branch="branch",
                run_id="run",
                max_iterations=0,
            )

    def test_run_context_json_serializable(self):
        """RunContext can be serialized to JSON."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
        )
        data = ctx.model_dump(mode="json")
        assert data["project_id"] == "test-project"
        assert data["spec_content"] == "# Spec"
        assert data["max_iterations"] == 20


class TestIterationResult:
    """Tests for IterationResult model."""

    def test_iteration_result_done(self):
        """IterationResult for DONE outcome."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All criteria met",
        )
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="Spec satisfied",
        )
        result = IterationResult(
            iteration_num=3,
            outcome=DecisionOutcome.DONE,
            orient_output=orient_output,
            decision=decision,
            act_output=None,
        )
        assert result.iteration_num == 3
        assert result.outcome == DecisionOutcome.DONE
        assert result.act_output is None

    def test_iteration_result_continue_with_act(self):
        """IterationResult for CONTINUE outcome includes ACT output."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            iteration_plan=IterationPlan(
                intent="Implement feature",
                tasks=[
                    PlannedTask(
                        task_id="ralph-task1",
                        title="Task 1",
                        rationale="First task",
                    )
                ],
                approach="TDD approach",
            ),
        )
        decision = Decision(outcome=DecisionOutcome.CONTINUE)
        act_output = ActOutput(
            tasks_completed=["ralph-task1"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["abc123"],
        )
        result = IterationResult(
            iteration_num=1,
            outcome=DecisionOutcome.CONTINUE,
            orient_output=orient_output,
            decision=decision,
            act_output=act_output,
        )
        assert result.outcome == DecisionOutcome.CONTINUE
        assert result.act_output is not None
        assert len(result.act_output.tasks_completed) == 1

    def test_iteration_result_stuck(self):
        """IterationResult for STUCK outcome."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            gaps=[Gap(description="Blocked", severity=GapSeverity.CRITICAL)],
        )
        decision = Decision(
            outcome=DecisionOutcome.STUCK,
            reason="No actionable work",
        )
        result = IterationResult(
            iteration_num=5,
            outcome=DecisionOutcome.STUCK,
            orient_output=orient_output,
            decision=decision,
        )
        assert result.outcome == DecisionOutcome.STUCK
        assert result.act_output is None

    def test_iteration_result_json_serializable(self):
        """IterationResult can be serialized to JSON."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="Done",
        )
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="Complete",
        )
        result = IterationResult(
            iteration_num=1,
            outcome=DecisionOutcome.DONE,
            orient_output=orient_output,
            decision=decision,
        )
        data = result.model_dump(mode="json")
        assert data["iteration_num"] == 1
        assert data["outcome"] == "DONE"


class TestRunResult:
    """Tests for RunResult model."""

    def test_run_result_done(self):
        """RunResult for completed run."""
        result = RunResult(
            status="done",
            iterations_completed=5,
            final_outcome="All acceptance criteria met",
            summary="Spec satisfied after 5 iterations.",
        )
        assert result.status == "done"
        assert result.iterations_completed == 5
        assert "5 iterations" in result.summary

    def test_run_result_stuck(self):
        """RunResult for stuck run."""
        result = RunResult(
            status="stuck",
            iterations_completed=3,
            final_outcome="No actionable work exists",
            summary="Stuck after 3 iterations. Reason: No actionable work exists",
        )
        assert result.status == "stuck"
        assert "No actionable work" in result.final_outcome

    def test_run_result_max_iterations(self):
        """RunResult for max iterations reached."""
        result = RunResult(
            status="max_iterations",
            iterations_completed=20,
            final_outcome="Max iterations (20) reached",
            summary="Reached maximum iterations (20).",
        )
        assert result.status == "max_iterations"
        assert result.iterations_completed == 20

    def test_run_result_json_serializable(self):
        """RunResult can be serialized to JSON."""
        result = RunResult(
            status="done",
            iterations_completed=1,
            final_outcome="Complete",
            summary="Done",
        )
        data = result.model_dump(mode="json")
        assert data["status"] == "done"


class TestSummaryBuilders:
    """Tests for summary builder functions."""

    def test_build_done_summary(self):
        """Done summary includes iteration count and decision summary."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All tests pass",
        )
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="All acceptance criteria verified",
        )
        result = IterationResult(
            iteration_num=3,
            outcome=DecisionOutcome.DONE,
            orient_output=orient_output,
            decision=decision,
        )
        summary = _build_done_summary(result)
        assert "3" in summary
        assert "iteration" in summary.lower()
        assert "acceptance criteria" in summary.lower()

    def test_build_stuck_summary(self):
        """Stuck summary includes reason and gaps."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            gaps=[Gap(description="Missing API key", severity=GapSeverity.CRITICAL)],
        )
        decision = Decision(
            outcome=DecisionOutcome.STUCK,
            reason="External dependency unavailable",
        )
        result = IterationResult(
            iteration_num=5,
            outcome=DecisionOutcome.STUCK,
            orient_output=orient_output,
            decision=decision,
        )
        summary = _build_stuck_summary(result)
        assert "5" in summary
        assert "External dependency" in summary or "API key" in summary

    def test_build_max_iterations_summary_with_result(self):
        """Max iterations summary includes last result info."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
            gaps=[
                Gap(description="Gap 1", severity=GapSeverity.MAJOR),
                Gap(description="Gap 2", severity=GapSeverity.MINOR),
            ],
        )
        decision = Decision(outcome=DecisionOutcome.CONTINUE)
        last_result = IterationResult(
            iteration_num=20,
            outcome=DecisionOutcome.CONTINUE,
            orient_output=orient_output,
            decision=decision,
        )
        summary = _build_max_iterations_summary(last_result, 20)
        assert "20" in summary
        assert "CONTINUE" in summary
        assert "2" in summary  # 2 remaining gaps

    def test_build_max_iterations_summary_without_result(self):
        """Max iterations summary handles None last_result."""
        summary = _build_max_iterations_summary(None, 10)
        assert "10" in summary
        assert "maximum" in summary.lower()


class TestBuildIterationHistory:
    """Tests for _build_iteration_history function."""

    def test_build_iteration_history_empty(self):
        """Empty history when no previous iterations."""
        db = MagicMock()
        db.get_iterations.return_value = []

        history = _build_iteration_history(db, "run-123", 1)
        assert history == []

    def test_build_iteration_history_excludes_current(self):
        """History excludes current iteration."""
        db = MagicMock()
        mock_iteration = MagicMock()
        mock_iteration.number = 2
        mock_iteration.intent = "Previous intent"
        mock_iteration.outcome = IterationOutcome.CONTINUE
        mock_iteration.id = 1
        db.get_iterations.return_value = [mock_iteration]
        db.get_agent_outputs.return_value = []

        # Current iteration is 2, so iteration 2 should be excluded
        history = _build_iteration_history(db, "run-123", 2)
        assert history == []

        # Current iteration is 3, so iteration 2 should be included
        history = _build_iteration_history(db, "run-123", 3)
        assert len(history) == 1
        assert history[0]["number"] == 2
        assert history[0]["intent"] == "Previous intent"


class TestRunIteration:
    """Tests for run_iteration function."""

    @pytest.mark.asyncio
    async def test_run_iteration_done(self):
        """run_iteration returns DONE when spec is satisfied."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
        )

        # Mock dependencies
        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []

        # Mock SENSE
        mock_claims = MagicMock()

        # Mock ORIENT to return DONE
        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All criteria verified",
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_iteration(ctx, 1, git_client, trace_client, db)

            assert result.outcome == DecisionOutcome.DONE
            assert result.iteration_num == 1
            assert result.act_output is None  # No ACT for DONE

    @pytest.mark.asyncio
    async def test_run_iteration_stuck(self):
        """run_iteration returns STUCK when no actionable work."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []

        mock_claims = MagicMock()

        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            gaps=[Gap(description="Blocked", severity=GapSeverity.CRITICAL)],
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_iteration(ctx, 1, git_client, trace_client, db)

            assert result.outcome == DecisionOutcome.STUCK
            assert result.act_output is None

    @pytest.mark.asyncio
    async def test_run_iteration_continue_with_act(self):
        """run_iteration executes ACT when CONTINUE with iteration_plan."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []

        mock_claims = MagicMock()

        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            iteration_plan=IterationPlan(
                intent="Implement feature",
                tasks=[
                    PlannedTask(
                        task_id="ralph-task1",
                        title="Task 1",
                        rationale="First",
                    )
                ],
                approach="TDD",
            ),
        )

        mock_act_output = ActOutput(
            tasks_completed=["ralph-task1"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["abc123"],
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_iteration(ctx, 1, git_client, trace_client, db)

            assert result.outcome == DecisionOutcome.CONTINUE
            assert result.act_output is not None
            assert "ralph-task1" in result.act_output.tasks_completed

    @pytest.mark.asyncio
    async def test_run_iteration_continue_without_plan_skips_act(self):
        """run_iteration skips ACT when CONTINUE but no iteration_plan."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []

        mock_claims = MagicMock()

        # ORIENT says CONTINUE but no iteration_plan
        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
            iteration_plan=None,
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_iteration(ctx, 1, git_client, trace_client, db)

            assert result.outcome == DecisionOutcome.CONTINUE
            assert result.act_output is None  # ACT skipped


class TestRunLoop:
    """Tests for run_loop function."""

    @pytest.mark.asyncio
    async def test_run_loop_done_first_iteration(self):
        """run_loop returns done when first iteration succeeds."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
            max_iterations=10,
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []
        db.create_iteration.return_value = MagicMock(id=1)
        db.get_agent_outputs.return_value = []

        mock_claims = MagicMock()
        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="Done",
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_loop(ctx, git_client, trace_client, db)

            assert result.status == "done"
            assert result.iterations_completed == 1

    @pytest.mark.asyncio
    async def test_run_loop_stuck(self):
        """run_loop returns stuck when iteration is stuck."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
            max_iterations=10,
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []
        db.create_iteration.return_value = MagicMock(id=1)
        db.get_agent_outputs.return_value = []

        mock_claims = MagicMock()
        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            gaps=[Gap(description="Blocked", severity=GapSeverity.CRITICAL)],
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_loop(ctx, git_client, trace_client, db)

            assert result.status == "stuck"
            assert result.iterations_completed == 1

    @pytest.mark.asyncio
    async def test_run_loop_max_iterations(self):
        """run_loop returns max_iterations when limit reached."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
            max_iterations=3,  # Low limit for testing
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []
        db.create_iteration.return_value = MagicMock(id=1)
        db.get_agent_outputs.return_value = []

        mock_claims = MagicMock()

        # Always return CONTINUE (with iteration plan to exercise ACT)
        mock_orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            iteration_plan=IterationPlan(
                intent="Keep working",
                tasks=[
                    PlannedTask(
                        task_id="task-1", title="Task", rationale="Work"
                    )
                ],
                approach="TDD",
            ),
        )

        mock_act_output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=[],
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", new_callable=AsyncMock, return_value=mock_orient_output), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_loop(ctx, git_client, trace_client, db)

            assert result.status == "max_iterations"
            assert result.iterations_completed == 3

    @pytest.mark.asyncio
    async def test_run_loop_multiple_iterations_then_done(self):
        """run_loop completes after multiple iterations."""
        ctx = RunContext(
            project_id="test-project",
            spec_content="# Spec",
            milestone_branch="feature/test",
            run_id="run-123",
            max_iterations=10,
        )

        git_client = MagicMock()
        trace_client = MagicMock()
        db = MagicMock()
        db.get_iterations.return_value = []
        db.create_iteration.return_value = MagicMock(id=1)
        db.get_agent_outputs.return_value = []

        mock_claims = MagicMock()

        # First two iterations return CONTINUE, third returns DONE
        call_count = [0]

        async def mock_orient(ctx):
            call_count[0] += 1
            if call_count[0] < 3:
                return OrientOutput(
                    spec_satisfied=SpecSatisfied.FALSE,
                    actionable_work_exists=True,
                    confidence=Confidence.HIGH,
                    iteration_plan=IterationPlan(
                        intent=f"Iteration {call_count[0]}",
                        tasks=[
                            PlannedTask(
                                task_id=f"task-{call_count[0]}",
                                title="Task",
                                rationale="Work",
                            )
                        ],
                        approach="TDD",
                    ),
                )
            else:
                return OrientOutput(
                    spec_satisfied=SpecSatisfied.TRUE,
                    actionable_work_exists=False,
                    confidence=Confidence.HIGH,
                    summary="All done",
                )

        mock_act_output = ActOutput(
            tasks_completed=["task"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["abc"],
        )

        with patch("soda.runner.sense", return_value=mock_claims), \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            result = await run_loop(ctx, git_client, trace_client, db)

            assert result.status == "done"
            assert result.iterations_completed == 3


# =============================================================================
# Run Completion Tests
# =============================================================================


class TestBuildRunSummary:
    """Tests for _build_run_summary function."""

    def test_build_run_summary_done(self):
        """Build summary for DONE status includes all sections."""
        summary = _build_run_summary(
            run_id="run-abc123",
            status="done",
            iterations=5,
            tasks_completed=["ralph-task1", "ralph-task2"],
            tasks_blocked=[],
            learnings=["Tests are in tests/soda/"],
            spec_title="My Feature",
            completion_time=datetime(2024, 1, 21, 10, 30, 0),
            milestone_branch="soda/milestone-abc123",
        )

        assert "# SODA Run Summary" in summary
        assert "run-abc123" in summary
        assert "DONE" in summary
        assert "**Iterations:** 5" in summary
        assert "My Feature" in summary
        assert "ralph-task1" in summary
        assert "ralph-task2" in summary
        assert "Tests are in tests/soda/" in summary
        assert "soda/milestone-abc123" in summary
        assert "gh pr create" in summary

    def test_build_run_summary_stuck(self):
        """Build summary for STUCK status includes blocked tasks."""
        blocked = [
            BlockedTask(task_id="ralph-blocked1", reason="Missing API key"),
            BlockedTask(task_id="ralph-blocked2", reason="External service down"),
        ]
        summary = _build_run_summary(
            run_id="run-xyz789",
            status="stuck",
            iterations=3,
            tasks_completed=["ralph-done"],
            tasks_blocked=blocked,
            learnings=[],
            spec_title="Blocked Feature",
            completion_time=datetime(2024, 1, 21, 11, 0, 0),
        )

        assert "STUCK" in summary
        assert "ralph-blocked1" in summary
        assert "Missing API key" in summary
        assert "ralph-blocked2" in summary
        assert "External service down" in summary
        assert "soda resume" in summary

    def test_build_run_summary_no_tasks_completed(self):
        """Build summary handles no completed tasks."""
        summary = _build_run_summary(
            run_id="run-empty",
            status="stuck",
            iterations=1,
            tasks_completed=[],
            tasks_blocked=[],
            learnings=[],
            spec_title="Empty Run",
            completion_time=datetime(2024, 1, 21, 12, 0, 0),
        )

        assert "*No tasks completed*" in summary
        assert "*No blocked tasks*" in summary
        assert "*No learnings captured*" in summary

    def test_build_run_summary_without_milestone_branch(self):
        """Build summary handles missing milestone branch."""
        summary = _build_run_summary(
            run_id="run-nobranch",
            status="done",
            iterations=2,
            tasks_completed=["task1"],
            tasks_blocked=[],
            learnings=[],
            spec_title="No Branch",
            completion_time=datetime(2024, 1, 21, 13, 0, 0),
            milestone_branch=None,
        )

        assert "Review the changes" in summary
        assert "Create a pull request" in summary


class TestCompleteRun:
    """Tests for complete_run function."""

    def test_complete_run_done(self):
        """complete_run updates database and writes summary for DONE status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            project_id = "test-project-id"
            summaries_dir = Path(tmpdir) / "summaries"
            summaries_dir.mkdir(parents=True)

            # Mock db
            db = MagicMock()

            # Patch get_project_summaries_dir to return our temp dir
            with patch("soda.runner.get_project_summaries_dir", return_value=summaries_dir):
                summary_path = complete_run(
                    run_id="run-abc123",
                    project_id=project_id,
                    status="done",
                    iterations=5,
                    tasks_completed=["ralph-task1", "ralph-task2"],
                    tasks_blocked=[],
                    learnings=["Learning 1"],
                    db=db,
                    spec_title="Test Feature",
                    milestone_branch="soda/milestone-test",
                )

            # Verify database was updated
            db.update_run_status.assert_called_once()
            call_args = db.update_run_status.call_args
            assert call_args[0][0] == "run-abc123"
            # RunStatus.DONE
            from soda.state.models import RunStatus
            assert call_args[0][1] == RunStatus.DONE

            # Verify summary file was created
            assert summary_path.exists()
            content = summary_path.read_text()
            assert "DONE" in content
            assert "ralph-task1" in content

    def test_complete_run_stuck(self):
        """complete_run updates database and writes summary for STUCK status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_id = "test-project-id"
            summaries_dir = Path(tmpdir) / "summaries"
            summaries_dir.mkdir(parents=True)

            db = MagicMock()
            blocked_tasks = [
                BlockedTask(task_id="ralph-blocked", reason="Missing dependency"),
            ]

            with patch("soda.runner.get_project_summaries_dir", return_value=summaries_dir):
                summary_path = complete_run(
                    run_id="run-xyz789",
                    project_id=project_id,
                    status="stuck",
                    iterations=3,
                    tasks_completed=["ralph-done"],
                    tasks_blocked=blocked_tasks,
                    learnings=[],
                    db=db,
                    spec_title="Stuck Feature",
                )

            # Verify database was updated with STUCK status
            db.update_run_status.assert_called_once()
            call_args = db.update_run_status.call_args
            from soda.state.models import RunStatus
            assert call_args[0][1] == RunStatus.STUCK

            # Verify summary file contains blocked info
            content = summary_path.read_text()
            assert "STUCK" in content
            assert "ralph-blocked" in content
            assert "Missing dependency" in content

    def test_complete_run_returns_summary_path(self):
        """complete_run returns the path to the summary file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summaries_dir = Path(tmpdir) / "summaries"
            summaries_dir.mkdir(parents=True)

            db = MagicMock()

            with patch("soda.runner.get_project_summaries_dir", return_value=summaries_dir):
                summary_path = complete_run(
                    run_id="run-return-test",
                    project_id="test-id",
                    status="done",
                    iterations=1,
                    tasks_completed=[],
                    tasks_blocked=[],
                    learnings=[],
                    db=db,
                )

            assert isinstance(summary_path, Path)
            assert summary_path.parent == summaries_dir
            assert summary_path.suffix == ".md"
            # Filename format: run-<first8chars>-<timestamp>.md
            assert summary_path.name.startswith("run-run-retu")

    def test_complete_run_summary_filename_format(self):
        """complete_run creates summary with correct filename format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summaries_dir = Path(tmpdir) / "summaries"
            summaries_dir.mkdir(parents=True)

            db = MagicMock()

            with patch("soda.runner.get_project_summaries_dir", return_value=summaries_dir):
                summary_path = complete_run(
                    run_id="abc12345-more-stuff",
                    project_id="test-id",
                    status="done",
                    iterations=1,
                    tasks_completed=[],
                    tasks_blocked=[],
                    learnings=[],
                    db=db,
                )

            # Filename should be run-<first8chars>-<timestamp>.md
            # For run_id "abc12345-more-stuff", first 8 chars is "abc12345"
            assert summary_path.name.startswith("run-abc12345")
            assert summary_path.name.endswith(".md")


class TestPrintCompletionMessage:
    """Tests for _print_completion_message function."""

    def test_print_completion_message_done(self, capsys):
        """Print completion message for DONE status."""
        _print_completion_message(
            status="done",
            iterations=5,
            tasks_completed=["task1", "task2", "task3"],
            tasks_blocked=[],
            milestone_branch="soda/milestone-test",
        )

        captured = capsys.readouterr()
        assert "SODA Run Complete" in captured.out
        assert "Status: DONE" in captured.out
        assert "Iterations: 5" in captured.out
        assert "Tasks completed: 3" in captured.out
        assert "soda/milestone-test" in captured.out
        assert "gh pr create" in captured.out

    def test_print_completion_message_stuck(self, capsys):
        """Print completion message for STUCK status."""
        blocked = [
            BlockedTask(task_id="ralph-b1", reason="Reason 1"),
            BlockedTask(task_id="ralph-b2", reason="Reason 2"),
        ]
        _print_completion_message(
            status="stuck",
            iterations=3,
            tasks_completed=["task1"],
            tasks_blocked=blocked,
        )

        captured = capsys.readouterr()
        assert "SODA Run Stuck" in captured.out
        assert "Status: STUCK" in captured.out
        assert "Iterations: 3" in captured.out
        assert "Tasks blocked: 2" in captured.out
        assert "ralph-b1" in captured.out
        assert "soda resume" in captured.out

    def test_print_completion_message_many_blocked(self, capsys):
        """Print completion message truncates blocked list."""
        blocked = [
            BlockedTask(task_id=f"ralph-b{i}", reason=f"Reason {i}")
            for i in range(5)
        ]
        _print_completion_message(
            status="stuck",
            iterations=1,
            tasks_completed=[],
            tasks_blocked=blocked,
        )

        captured = capsys.readouterr()
        # Only first 3 should be shown
        assert "ralph-b0" in captured.out
        assert "ralph-b1" in captured.out
        assert "ralph-b2" in captured.out
        assert "ralph-b3" not in captured.out
        assert "and 2 more" in captured.out

    def test_print_completion_message_done_no_branch(self, capsys):
        """Print completion message for DONE without milestone branch."""
        _print_completion_message(
            status="done",
            iterations=2,
            tasks_completed=["task1"],
            tasks_blocked=[],
            milestone_branch=None,
        )

        captured = capsys.readouterr()
        assert "Review the changes" in captured.out
        assert "Create a pull request" in captured.out
