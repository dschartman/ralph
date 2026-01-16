"""Tests for auto-resume functionality in Ralph2Runner."""

import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import shutil

from ralph2.runner import Ralph2Runner
from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run, Iteration
from ralph2.project import ProjectContext


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with Ralph2file."""
    temp_dir = tempfile.mkdtemp()
    ralph2file = Path(temp_dir) / "Ralph2file"
    ralph2file.write_text("# Test Spec\n\nTest spec content")

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def project_context(temp_project_dir):
    """Create a ProjectContext for testing."""
    # Mock ProjectContext to use temp directory
    ctx = Mock(spec=ProjectContext)
    ctx.__class__ = ProjectContext
    ctx.project_root = Path(temp_project_dir)
    ctx.project_id = "test-project-id"

    # Create temp state directory
    state_dir = Path(tempfile.mkdtemp())
    ctx.state_dir = state_dir
    ctx.db_path = state_dir / "ralph2.db"
    ctx.outputs_dir = state_dir / "outputs"
    ctx.summaries_dir = state_dir / "summaries"
    ctx.outputs_dir.mkdir(parents=True, exist_ok=True)
    ctx.summaries_dir.mkdir(parents=True, exist_ok=True)

    yield ctx

    # Cleanup
    shutil.rmtree(state_dir)


@pytest.mark.asyncio
async def test_new_run_when_no_existing_run(project_context, temp_project_dir):
    """Test that a new run is created when no existing run exists."""
    spec_path = str(Path(temp_project_dir) / "Ralph2file")

    # Create runner
    runner = Ralph2Runner(spec_path, project_context)

    # Check that no runs exist
    runs = runner.db.list_runs()
    assert len(runs) == 0

    # Mock agents to return immediately
    with patch('ralph2.runner.run_planner') as mock_planner, \
         patch('ralph2.runner.run_executor') as mock_executor, \
         patch('ralph2.runner.run_verifier') as mock_verifier:

        mock_planner.return_value = {
            "intent": "Test intent",
            "decision": {"decision": "DONE", "reason": "Test complete"},
            "iteration_plan": None,
            "messages": []
        }

        # Run with max_iterations=1
        status = await runner.run(max_iterations=1)

    # Should create exactly one run
    runs = runner.db.list_runs()
    assert len(runs) == 1
    assert runs[0].status == "completed"

    runner.close()


@pytest.mark.asyncio
async def test_resume_interrupted_run(project_context, temp_project_dir):
    """Test that an interrupted run is resumed instead of creating a new one."""
    spec_path = str(Path(temp_project_dir) / "Ralph2file")

    # Create an interrupted run manually
    db = Ralph2DB(str(project_context.db_path))

    interrupted_run = Run(
        id="ralph2-interrupted",
        spec_path=spec_path,
        spec_content="# Test Spec\n\nTest spec content",
        status="running",  # Interrupted run has status "running"
        config={"max_iterations": 50},
        started_at=datetime.now()
    )
    db.create_run(interrupted_run)

    # Create some completed iterations for this run
    iteration1 = Iteration(
        id=None,
        run_id=interrupted_run.id,
        number=1,
        intent="First iteration",
        outcome="CONTINUE",
        started_at=datetime.now(),
        ended_at=datetime.now()
    )
    db.create_iteration(iteration1)

    iteration2 = Iteration(
        id=None,
        run_id=interrupted_run.id,
        number=2,
        intent="Second iteration",
        outcome="CONTINUE",
        started_at=datetime.now(),
        ended_at=datetime.now()
    )
    db.create_iteration(iteration2)

    db.close()

    # Create runner (should detect and resume interrupted run)
    runner = Ralph2Runner(spec_path, project_context)

    # Mock agents to return immediately
    with patch('ralph2.runner.run_planner') as mock_planner, \
         patch('ralph2.runner.run_executor') as mock_executor, \
         patch('ralph2.runner.run_verifier') as mock_verifier:

        mock_planner.return_value = {
            "intent": "Resume intent",
            "decision": {"decision": "DONE", "reason": "Resume complete"},
            "iteration_plan": None,
            "messages": []
        }

        # Run
        status = await runner.run(max_iterations=10)

    # Should resume the interrupted run, not create a new one
    runs = runner.db.list_runs()
    assert len(runs) == 1
    assert runs[0].id == "ralph2-interrupted"

    # Should have created iteration 3
    iterations = runner.db.list_iterations(runs[0].id)
    assert len(iterations) == 3
    assert iterations[2].number == 3

    runner.close()


@pytest.mark.asyncio
async def test_new_run_when_previous_run_completed(project_context, temp_project_dir):
    """Test that a new run is created when previous run was completed."""
    spec_path = str(Path(temp_project_dir) / "Ralph2file")

    # Create a completed run manually
    db = Ralph2DB(str(project_context.db_path))

    completed_run = Run(
        id="ralph2-completed",
        spec_path=spec_path,
        spec_content="# Test Spec\n\nTest spec content",
        status="completed",  # Completed run
        config={"max_iterations": 50},
        started_at=datetime.now(),
        ended_at=datetime.now()
    )
    db.create_run(completed_run)
    db.close()

    # Create runner (should create a new run, not resume)
    runner = Ralph2Runner(spec_path, project_context)

    # Mock agents to return immediately
    with patch('ralph2.runner.run_planner') as mock_planner:
        mock_planner.return_value = {
            "intent": "New run intent",
            "decision": {"decision": "DONE", "reason": "New run complete"},
            "iteration_plan": None,
            "messages": []
        }

        # Run
        status = await runner.run(max_iterations=1)

    # Should create a new run
    runs = runner.db.list_runs()
    assert len(runs) == 2
    assert runs[0].id != "ralph2-completed"  # First in list is most recent

    runner.close()


@pytest.mark.asyncio
async def test_cleanup_abandoned_branches_on_resume(project_context, temp_project_dir):
    """Test that abandoned feature branches are cleaned up on resume."""
    spec_path = str(Path(temp_project_dir) / "Ralph2file")

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=temp_project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_project_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=temp_project_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_project_dir, capture_output=True)

    # Create an abandoned feature branch
    subprocess.run(["git", "checkout", "-b", "ralph2/ralph-test123"], cwd=temp_project_dir, capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=temp_project_dir, capture_output=True, check=False)
    subprocess.run(["git", "checkout", "master"], cwd=temp_project_dir, capture_output=True, check=False)

    # Create an interrupted run
    db = Ralph2DB(str(project_context.db_path))
    interrupted_run = Run(
        id="ralph2-interrupted",
        spec_path=spec_path,
        spec_content="# Test Spec\n\nTest spec content",
        status="running",
        config={"max_iterations": 50},
        started_at=datetime.now()
    )
    db.create_run(interrupted_run)
    db.close()

    # Verify branch exists
    result = subprocess.run(["git", "branch"], cwd=temp_project_dir, capture_output=True, text=True)
    assert "ralph2/ralph-test123" in result.stdout

    # Create runner and run (should clean up branches)
    runner = Ralph2Runner(spec_path, project_context)

    with patch('ralph2.runner.run_planner') as mock_planner:
        mock_planner.return_value = {
            "intent": "Resume with cleanup",
            "decision": {"decision": "DONE", "reason": "Cleaned up"},
            "iteration_plan": None,
            "messages": []
        }

        # Run - should clean up abandoned branches
        status = await runner.run(max_iterations=1)

    # Verify branch was deleted
    result = subprocess.run(["git", "branch"], cwd=temp_project_dir, capture_output=True, text=True)
    assert "ralph2/ralph-test123" not in result.stdout

    runner.close()
