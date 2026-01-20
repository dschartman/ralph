"""Tests for automatic root work item creation and management."""

import pytest
import tempfile
import subprocess
import json
from pathlib import Path
from datetime import datetime

from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run
from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext


@pytest.fixture
def temp_project():
    """Create a temporary project directory with git and trace initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Initialize git
        subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_root, check=True, capture_output=True)

        # Initialize trace
        subprocess.run(["trc", "init"], cwd=project_root, check=True, capture_output=True)

        # Create a Ralph2file
        ralph2file = project_root / "Ralph2file"
        ralph2file.write_text("# Test Spec\n\nThis is a test specification.")

        # Commit initial state
        subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True, capture_output=True)

        yield project_root


def test_root_work_item_auto_created_on_first_run(temp_project):
    """Test that root work item is automatically created on first run."""
    # Create project context
    ctx = ProjectContext(temp_project)

    # Create a runner without specifying root_work_item_id
    runner = Ralph2Runner(
        spec_path=str(temp_project / "Ralph2file"),
        project_context=ctx,
        root_work_item_id=None
    )

    # Initialize the run (simulate first run)
    run_id = f"ralph2-test-{datetime.now().timestamp()}"
    run = Run(
        id=run_id,
        spec_path=str(temp_project / "Ralph2file"),
        spec_content="# Test Spec\n\nThis is a test specification.",
        status="running",
        config={"max_iterations": 10},
        started_at=datetime.now(),
        root_work_item_id=None
    )
    runner.db.create_run(run)

    # Simulate root work item creation
    root_work_item_id = runner._ensure_root_work_item()

    # Verify root work item was created
    assert root_work_item_id is not None
    # Work item ID should match pattern: prefix-suffix
    assert "-" in root_work_item_id

    # Store it in the database (simulating what the runner does)
    runner.db.update_run_root_work_item(run_id, root_work_item_id)

    # Verify it was stored in the database
    stored_run = runner.db.get_run(run_id)
    assert stored_run.root_work_item_id == root_work_item_id

    # Verify the work item exists in Trace
    result = subprocess.run(
        ["trc", "show", root_work_item_id],
        cwd=temp_project,
        capture_output=True,
        text=True,
        check=True
    )
    assert "Test Spec" in result.stdout


def test_root_work_item_stored_and_reused(temp_project):
    """Test that root work item ID is stored and reused on subsequent runs."""
    ctx = ProjectContext(temp_project)

    # First run: create root work item
    runner1 = Ralph2Runner(
        spec_path=str(temp_project / "Ralph2file"),
        project_context=ctx,
        root_work_item_id=None
    )

    run_id_1 = f"ralph2-test-1-{datetime.now().timestamp()}"
    run1 = Run(
        id=run_id_1,
        spec_path=str(temp_project / "Ralph2file"),
        spec_content="# Test Spec\n\nThis is a test specification.",
        status="completed",
        config={"max_iterations": 10},
        started_at=datetime.now(),
        ended_at=datetime.now(),
        root_work_item_id=None
    )
    runner1.db.create_run(run1)

    root_work_item_id_1 = runner1._ensure_root_work_item()
    # Store it in the database (simulating what the runner does)
    runner1.db.update_run_root_work_item(run_id_1, root_work_item_id_1)

    # Second run: should reuse the same root work item
    runner2 = Ralph2Runner(
        spec_path=str(temp_project / "Ralph2file"),
        project_context=ctx,
        root_work_item_id=None
    )

    run_id_2 = f"ralph2-test-2-{datetime.now().timestamp()}"
    run2 = Run(
        id=run_id_2,
        spec_path=str(temp_project / "Ralph2file"),
        spec_content="# Test Spec\n\nThis is a test specification.",
        status="running",
        config={"max_iterations": 10},
        started_at=datetime.now(),
        root_work_item_id=None
    )
    runner2.db.create_run(run2)

    root_work_item_id_2 = runner2._ensure_root_work_item()

    # Verify both runs use the same root work item
    assert root_work_item_id_1 == root_work_item_id_2


def test_explicit_root_work_item_id_honored(temp_project):
    """Test that explicitly provided root work item ID is used instead of auto-creating."""
    ctx = ProjectContext(temp_project)

    # Create a work item manually
    result = subprocess.run(
        ["trc", "create", "Manually Created Work Item", "--description", "Manual test"],
        cwd=temp_project,
        capture_output=True,
        text=True,
        check=True
    )

    # Extract work item ID from output (format: "Created <id>: <title>")
    # Get last line and extract ID between "Created " and ":"
    output_line = result.stdout.strip().split('\n')[-1]
    if output_line.startswith("Created "):
        manual_work_item_id = output_line.split()[1].rstrip(":")
    else:
        manual_work_item_id = output_line.split()[-1]

    # Create runner with explicit root work item ID
    runner = Ralph2Runner(
        spec_path=str(temp_project / "Ralph2file"),
        project_context=ctx,
        root_work_item_id=manual_work_item_id
    )

    run_id = f"ralph2-test-{datetime.now().timestamp()}"
    run = Run(
        id=run_id,
        spec_path=str(temp_project / "Ralph2file"),
        spec_content="# Test Spec\n\nThis is a test specification.",
        status="running",
        config={"max_iterations": 10},
        started_at=datetime.now(),
        root_work_item_id=None
    )
    runner.db.create_run(run)

    root_work_item_id = runner._ensure_root_work_item()

    # Verify the manual ID was used
    assert root_work_item_id == manual_work_item_id


def test_extract_spec_title():
    """Test extracting spec title from content."""
    from ralph2.runner import _extract_spec_title

    # Test with H1 title
    content1 = "# My Project Spec\n\nSome description"
    assert _extract_spec_title(content1) == "My Project Spec"

    # Test with no title
    content2 = "Some content without a title"
    assert _extract_spec_title(content2) == "Spec"

    # Test with multiple lines before H1
    content3 = "Some preamble\n\n# The Actual Title\n\nContent"
    assert _extract_spec_title(content3) == "The Actual Title"
