"""Integration tests for SODA Full Loop (M6).

These tests exercise the full SODA loop end-to-end:
- Real git operations (in temp directories)
- Mocked LLM calls (orient, act)
- Real database operations (in temp directories)

Test scenarios:
1. Happy Path End-to-End
2. STUCK and Resume
3. Max Iterations
4. Kickstart (New Project)
5. Bootstrap Idempotency
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from soda.act import ActOutput, BlockedTask
from soda.decide import DecisionOutcome
from soda.orient import (
    Confidence,
    Gap,
    GapSeverity,
    IterationPlan,
    OrientOutput,
    PlannedTask,
    SpecSatisfied,
)
from soda.runner import (
    BootstrapResult,
    MilestoneContext,
    RunContext,
    RunResult,
    bootstrap,
    run_loop,
    setup_milestone,
)
from soda.state.db import SodaDB
from soda.state.git import GitClient
from soda.state.models import RunStatus
from soda.state.trace import TraceClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with git initialized.

    Returns a Path to the project directory with:
    - Git repo initialized
    - Initial empty commit
    """
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    git = GitClient(cwd=str(project_dir))
    git._run_git(["init"])
    git._run_git(["commit", "--allow-empty", "-m", "Initial commit"])

    return project_dir


@pytest.fixture
def temp_project_with_structure(temp_project):
    """Create a temp project with existing code structure.

    Adds pyproject.toml and src/ directory to simulate an existing project.
    """
    (temp_project / "pyproject.toml").write_text('[project]\nname = "test"')
    (temp_project / "src").mkdir()
    (temp_project / "src" / "__init__.py").write_text("")
    return temp_project


@pytest.fixture
def simple_spec():
    """A simple spec for testing."""
    return """# Test Feature

## Acceptance Criteria
- [ ] WHEN test runs THEN it passes
"""


@pytest.fixture
def impossible_spec():
    """A spec that cannot be satisfied (for STUCK testing)."""
    return """# Impossible Feature

## Acceptance Criteria
- [ ] WHEN impossible condition THEN magic happens
- [ ] WHEN external API unavailable THEN still works
"""


@pytest.fixture
def mock_trace_client():
    """Create a mock TraceClient that doesn't make real calls."""
    client = MagicMock(spec=TraceClient)
    client.create_task.return_value = "ralph-mock-task"
    client.post_comment.return_value = None
    client.close_task.return_value = None
    return client


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = SodaDB(str(db_path))
    yield db
    db.close()


def create_done_orient_output():
    """Create an OrientOutput that signals DONE."""
    return OrientOutput(
        spec_satisfied=SpecSatisfied.TRUE,
        actionable_work_exists=False,
        confidence=Confidence.HIGH,
        summary="All acceptance criteria verified",
    )


def create_continue_orient_output(task_id="ralph-task1", intent="Implement feature"):
    """Create an OrientOutput that signals CONTINUE with work to do."""
    return OrientOutput(
        spec_satisfied=SpecSatisfied.FALSE,
        actionable_work_exists=True,
        confidence=Confidence.HIGH,
        iteration_plan=IterationPlan(
            intent=intent,
            tasks=[
                PlannedTask(
                    task_id=task_id,
                    title="Test Task",
                    rationale="Needs to be done",
                )
            ],
            approach="TDD approach",
        ),
    )


def create_stuck_orient_output(gap_description="Cannot proceed"):
    """Create an OrientOutput that signals STUCK."""
    return OrientOutput(
        spec_satisfied=SpecSatisfied.FALSE,
        actionable_work_exists=False,
        confidence=Confidence.HIGH,
        gaps=[Gap(description=gap_description, severity=GapSeverity.CRITICAL)],
    )


def create_act_output(tasks_completed=None, tasks_blocked=None, commits=None):
    """Create an ActOutput with configurable results."""
    return ActOutput(
        tasks_completed=tasks_completed or [],
        tasks_blocked=tasks_blocked or [],
        task_comments=[],
        new_subtasks=[],
        learnings=[],
        commits=commits or [],
    )


# =============================================================================
# Test: Happy Path End-to-End
# =============================================================================


class TestHappyPathEndToEnd:
    """Test the full loop completing successfully in a few iterations."""

    @pytest.mark.asyncio
    async def test_loop_reaches_done_in_few_iterations(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Loop runs SENSE → ORIENT → DECIDE → ACT and reaches DONE."""
        # Setup
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        # Bootstrap
        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        assert bootstrap_result.project_id is not None
        assert bootstrap_result.is_kickstart is False  # Has structure

        # Setup milestone
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )
        assert milestone_ctx.milestone_branch.startswith("soda/milestone-")

        # Create run context
        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=10,
            working_directory=working_dir,
            run_id="test-run-happy",
        )

        # Mock ORIENT to return CONTINUE once, then DONE
        call_count = [0]

        async def mock_orient(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_continue_orient_output(intent="First iteration")
            else:
                return create_done_orient_output()

        # Mock ACT to return success
        mock_act_output = create_act_output(
            tasks_completed=["ralph-task1"],
            commits=["abc123"],
        )

        # Run the loop
        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()

            result = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        # Verify
        assert result.status == "done"
        assert result.iterations_completed == 2
        assert "satisfied" in result.summary.lower() or "2" in result.summary

    @pytest.mark.asyncio
    async def test_loop_creates_commits_on_milestone_branch(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Work is committed on the milestone branch."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        # Bootstrap and milestone setup
        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        # Verify we're on the milestone branch
        current_branch = git_client.get_current_branch()
        assert current_branch == milestone_ctx.milestone_branch


# =============================================================================
# Test: STUCK and Resume
# =============================================================================


class TestStuckAndResume:
    """Test STUCK handling and run resumption."""

    @pytest.mark.asyncio
    async def test_loop_reaches_stuck_when_no_actionable_work(
        self, temp_project_with_structure, impossible_spec, mock_trace_client, temp_db
    ):
        """Loop reaches STUCK when ORIENT says no actionable work."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(impossible_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        # Bootstrap and setup
        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=10,
            working_directory=working_dir,
            run_id="test-run-stuck",
        )

        # Mock ORIENT to return STUCK
        async def mock_orient(ctx):
            return create_stuck_orient_output("External API unavailable")

        # Run the loop
        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()

            result = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        # Verify STUCK
        assert result.status == "stuck"
        assert result.iterations_completed == 1

    @pytest.mark.asyncio
    async def test_resume_after_stuck_can_reach_done(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Resuming a stuck run can reach DONE after human input."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        # Bootstrap and setup
        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        # First run: gets STUCK
        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=10,
            working_directory=working_dir,
            run_id="test-run-resume",
        )

        first_call = [True]

        async def mock_orient_with_resume(ctx):
            if first_call[0]:
                first_call[0] = False
                return create_stuck_orient_output("Need human input")
            else:
                return create_done_orient_output()

        # First run - gets stuck
        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient_with_resume), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            result1 = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        assert result1.status == "stuck"

        # Reset for resume
        first_call[0] = False  # Already consumed the stuck response

        # Second run - simulates resume after human input
        run_ctx_resumed = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=10,
            working_directory=working_dir,
            run_id="test-run-resume-2",
        )

        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient_with_resume), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            result2 = await run_loop(run_ctx_resumed, git_client, mock_trace_client, temp_db)

        assert result2.status == "done"


# =============================================================================
# Test: Max Iterations
# =============================================================================


class TestMaxIterations:
    """Test max iterations handling."""

    @pytest.mark.asyncio
    async def test_loop_halts_at_max_iterations(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Loop stops when max iterations reached."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        # Small max_iterations for testing
        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=3,
            working_directory=working_dir,
            run_id="test-run-max",
        )

        # Always return CONTINUE (never done)
        iteration_count = [0]

        async def mock_orient_always_continue(ctx):
            iteration_count[0] += 1
            return create_continue_orient_output(
                task_id=f"ralph-task{iteration_count[0]}",
                intent=f"Iteration {iteration_count[0]}"
            )

        mock_act_output = create_act_output(commits=["commit"])

        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient_always_continue), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            result = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        assert result.status == "max_iterations"
        assert result.iterations_completed == 3
        assert "3" in result.summary or "maximum" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_max_iterations_preserves_progress(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Max iterations preserves work done so far."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=2,
            working_directory=working_dir,
            run_id="test-run-max-progress",
        )

        async def mock_orient(ctx):
            return create_continue_orient_output()

        mock_act_output = create_act_output(
            tasks_completed=["ralph-task1"],
            commits=["abc123"],
        )

        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            result = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        # Should have completed 2 iterations worth of work
        assert result.iterations_completed == 2


# =============================================================================
# Test: Kickstart (New Project)
# =============================================================================


class TestKickstart:
    """Test kickstart handling for new projects without structure."""

    @pytest.mark.asyncio
    async def test_kickstart_detected_for_empty_project(self, temp_project, simple_spec):
        """Bootstrap detects kickstart for empty project."""
        spec_path = temp_project / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project)

        result = await bootstrap(working_dir, str(spec_path))

        assert result.is_kickstart is True

    @pytest.mark.asyncio
    async def test_kickstart_not_detected_for_existing_structure(
        self, temp_project_with_structure, simple_spec
    ):
        """Bootstrap does not detect kickstart for project with structure."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)

        result = await bootstrap(working_dir, str(spec_path))

        assert result.is_kickstart is False

    @pytest.mark.asyncio
    async def test_kickstart_project_can_reach_done(
        self, temp_project, simple_spec, mock_trace_client, temp_db
    ):
        """Kickstart project can still complete the loop."""
        spec_path = temp_project / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project)
        git_client = GitClient(cwd=working_dir)

        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        assert bootstrap_result.is_kickstart is True

        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=5,
            working_directory=working_dir,
            run_id="test-run-kickstart",
        )

        # First iteration scaffolds, second completes
        call_count = [0]

        async def mock_orient(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_continue_orient_output(intent="Scaffold project structure")
            else:
                return create_done_orient_output()

        mock_act_output = create_act_output(
            tasks_completed=["ralph-scaffold"],
            commits=["scaffold-commit"],
        )

        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            result = await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        assert result.status == "done"


# =============================================================================
# Test: Bootstrap Idempotency
# =============================================================================


class TestBootstrapIdempotency:
    """Test that bootstrap is idempotent."""

    @pytest.mark.asyncio
    async def test_bootstrap_reuses_project_id(self, temp_project, simple_spec):
        """Running bootstrap twice reuses the same project ID."""
        spec_path = temp_project / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project)

        # First bootstrap
        result1 = await bootstrap(working_dir, str(spec_path))
        assert result1.is_new_project is True

        # Second bootstrap
        result2 = await bootstrap(working_dir, str(spec_path))
        assert result2.is_new_project is False

        # Same project ID
        assert result1.project_id == result2.project_id

    @pytest.mark.asyncio
    async def test_bootstrap_preserves_soda_id_file(self, temp_project, simple_spec):
        """.soda-id file is preserved across bootstraps."""
        spec_path = temp_project / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project)
        soda_id_path = temp_project / ".soda-id"

        # First bootstrap
        await bootstrap(working_dir, str(spec_path))
        assert soda_id_path.exists()
        first_id = soda_id_path.read_text().strip()

        # Second bootstrap
        await bootstrap(working_dir, str(spec_path))
        assert soda_id_path.exists()
        second_id = soda_id_path.read_text().strip()

        assert first_id == second_id

    @pytest.mark.asyncio
    async def test_milestone_reused_on_resume(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Resuming reuses existing milestone branch and work item."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        # First setup
        bootstrap_result = await bootstrap(working_dir, str(spec_path))

        # Create a run record to simulate previous run
        from soda.state.models import Run

        run1 = Run(
            id="existing-run",
            spec_path=str(spec_path),
            spec_content=simple_spec,
            status=RunStatus.PAUSED,
            milestone_branch="soda/milestone-existing",
            root_work_item_id="ralph-existing",
            config={},
            started_at=datetime.now(),
        )
        temp_db.create_run(run1)

        # Create the branch so checkout works
        git_client._run_git(["branch", "soda/milestone-existing"])

        # Setup milestone with run_id (resume mode)
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
            run_id="existing-run",
        )

        # Should reuse existing
        assert milestone_ctx.is_resumed is True
        assert milestone_ctx.milestone_branch == "soda/milestone-existing"
        assert milestone_ctx.root_work_item_id == "ralph-existing"

        # Trace should NOT have been called (no new work item)
        mock_trace_client.create_task.assert_not_called()


# =============================================================================
# Test: Database Recording
# =============================================================================


class TestDatabaseRecording:
    """Test that iterations are properly recorded in the database."""

    @pytest.mark.asyncio
    async def test_iterations_recorded_in_database(
        self, temp_project_with_structure, simple_spec, mock_trace_client, temp_db
    ):
        """Each iteration is recorded in the database."""
        spec_path = temp_project_with_structure / "Sodafile"
        spec_path.write_text(simple_spec)

        working_dir = str(temp_project_with_structure)
        git_client = GitClient(cwd=working_dir)

        bootstrap_result = await bootstrap(working_dir, str(spec_path))
        milestone_ctx = await setup_milestone(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            git_client=git_client,
            trace_client=mock_trace_client,
            db=temp_db,
        )

        run_id = "test-run-db-record"

        # Create run record
        from soda.state.models import Run

        run = Run(
            id=run_id,
            spec_path=str(spec_path),
            spec_content=simple_spec,
            status=RunStatus.RUNNING,
            config={},
            started_at=datetime.now(),
        )
        temp_db.create_run(run)

        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id,
            max_iterations=3,
            working_directory=working_dir,
            run_id=run_id,
        )

        # Two iterations then done
        call_count = [0]

        async def mock_orient(ctx):
            call_count[0] += 1
            if call_count[0] < 3:
                return create_continue_orient_output(intent=f"Iteration {call_count[0]}")
            else:
                return create_done_orient_output()

        mock_act_output = create_act_output(commits=["abc"])

        with patch("soda.runner.sense") as mock_sense, \
             patch("soda.runner.orient", mock_orient), \
             patch("soda.runner.act", new_callable=AsyncMock, return_value=mock_act_output), \
             patch("soda.runner.read_memory", return_value=""):

            mock_sense.return_value = MagicMock()
            await run_loop(run_ctx, git_client, mock_trace_client, temp_db)

        # Check database
        iterations = temp_db.get_iterations(run_id)
        assert len(iterations) == 3

        # Verify iteration details
        assert iterations[0].number == 1
        assert iterations[1].number == 2
        assert iterations[2].number == 3
