"""Tests for milestone completion integration in Ralph2Runner.

The spec requires:
- WHEN Planner declares DONE, THEN all open children of the root work item are reparented
- WHEN Planner declares DONE, THEN the original root work item is closed via `trc close`
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext
from ralph2.state.models import Run, Iteration

# Store original subprocess.run to use in mocks
_original_subprocess_run = subprocess.run


@pytest.fixture
def temp_project():
    """Create a temporary project directory with git and trace initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Initialize git
        _original_subprocess_run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "config", "user.name", "Test User"], cwd=project_root, check=True, capture_output=True)

        # Initialize trace
        _original_subprocess_run(["trc", "init"], cwd=project_root, check=True, capture_output=True)

        # Create a Ralph2file
        ralph2file = project_root / "Ralph2file"
        ralph2file.write_text("# Test Spec\n\nThis is a test specification.")

        # Commit initial state
        _original_subprocess_run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True, capture_output=True)

        yield project_root


class TestMilestoneIntegration:
    """Test that milestone completion is called when Planner declares DONE."""

    def test_complete_milestone_called_on_done(self, temp_project):
        """
        WHEN Planner declares DONE
        THEN complete_milestone() is called with root_work_item_id
        """
        ctx = ProjectContext(temp_project)

        # Create root work item
        result = _original_subprocess_run(
            ["trc", "create", "Test Milestone", "--description", "Test milestone"],
            cwd=temp_project,
            capture_output=True,
            text=True,
            check=True
        )
        root_id = result.stdout.split()[1].rstrip(":")

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=root_id
        )

        # Track whether complete_milestone was called
        complete_milestone_called = [False]
        complete_milestone_args = [None]

        def mock_complete_milestone(root_work_item_id, project_root):
            complete_milestone_called[0] = True
            complete_milestone_args[0] = (root_work_item_id, project_root)
            return []  # Return empty list of new parent IDs

        # Mock _handle_planner_termination to track what happens on DONE
        with patch('ralph2.runner.complete_milestone', mock_complete_milestone):
            # Simulate planner termination with DONE
            from ralph2.runner import IterationContext
            ctx_iter = IterationContext(
                run_id="test-run",
                iteration_id=1,
                iteration_number=1,
                intent="Test intent",
                memory="",
                decision={'decision': 'DONE', 'reason': 'All work complete'}
            )

            # Call the termination handler
            success, status = runner._handle_planner_termination(ctx_iter)

        # Verify complete_milestone was called
        assert complete_milestone_called[0], "complete_milestone() should be called when Planner declares DONE"
        assert complete_milestone_args[0][0] == root_id, f"complete_milestone() should be called with root_work_item_id={root_id}"

    def test_complete_milestone_not_called_on_stuck(self, temp_project):
        """
        WHEN Planner declares STUCK
        THEN complete_milestone() is NOT called
        """
        ctx = ProjectContext(temp_project)

        # Create root work item
        result = _original_subprocess_run(
            ["trc", "create", "Test Milestone", "--description", "Test milestone"],
            cwd=temp_project,
            capture_output=True,
            text=True,
            check=True
        )
        root_id = result.stdout.split()[1].rstrip(":")

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=root_id
        )

        # Track whether complete_milestone was called
        complete_milestone_called = [False]

        def mock_complete_milestone(root_work_item_id, project_root):
            complete_milestone_called[0] = True
            return []

        with patch('ralph2.runner.complete_milestone', mock_complete_milestone):
            from ralph2.runner import IterationContext
            ctx_iter = IterationContext(
                run_id="test-run",
                iteration_id=1,
                iteration_number=1,
                intent="Test intent",
                memory="",
                decision={'decision': 'STUCK', 'reason': 'Cannot proceed', 'blocker': 'Missing dependency'}
            )

            # Call the termination handler
            success, status = runner._handle_planner_termination(ctx_iter)

        # Verify complete_milestone was NOT called for STUCK
        assert not complete_milestone_called[0], "complete_milestone() should NOT be called when Planner declares STUCK"

    def test_complete_milestone_not_called_without_root_work_item(self, temp_project):
        """
        WHEN Planner declares DONE but there is no root_work_item_id
        THEN complete_milestone() is NOT called (nothing to close)
        """
        ctx = ProjectContext(temp_project)

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None  # No root work item
        )

        complete_milestone_called = [False]

        def mock_complete_milestone(root_work_item_id, project_root):
            complete_milestone_called[0] = True
            return []

        with patch('ralph2.runner.complete_milestone', mock_complete_milestone):
            from ralph2.runner import IterationContext
            ctx_iter = IterationContext(
                run_id="test-run",
                iteration_id=1,
                iteration_number=1,
                intent="Test intent",
                memory="",
                decision={'decision': 'DONE', 'reason': 'All work complete'}
            )

            runner._handle_planner_termination(ctx_iter)

        # Verify complete_milestone was NOT called (no root work item)
        assert not complete_milestone_called[0], "complete_milestone() should NOT be called when there is no root_work_item_id"

    def test_complete_milestone_error_logged_but_run_completes(self, temp_project, capfd):
        """
        WHEN complete_milestone() fails
        THEN error is logged but run still completes (graceful degradation)
        """
        ctx = ProjectContext(temp_project)

        # Create root work item
        result = _original_subprocess_run(
            ["trc", "create", "Test Milestone", "--description", "Test milestone"],
            cwd=temp_project,
            capture_output=True,
            text=True,
            check=True
        )
        root_id = result.stdout.split()[1].rstrip(":")

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=root_id
        )

        def mock_complete_milestone_error(root_work_item_id, project_root):
            raise RuntimeError("Failed to complete milestone")

        with patch('ralph2.runner.complete_milestone', mock_complete_milestone_error):
            from ralph2.runner import IterationContext
            ctx_iter = IterationContext(
                run_id="test-run",
                iteration_id=1,
                iteration_number=1,
                intent="Test intent",
                memory="",
                decision={'decision': 'DONE', 'reason': 'All work complete'}
            )

            # Should not raise - error should be caught and logged
            success, status = runner._handle_planner_termination(ctx_iter)

        # Run should still complete
        assert status == "completed"

        # Error should be logged
        captured = capfd.readouterr()
        assert "milestone" in captured.out.lower() or "warning" in captured.out.lower()
