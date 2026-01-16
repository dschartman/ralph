"""Tests for milestone completion logic when Planner declares DONE."""

import subprocess
import pytest
from pathlib import Path


@pytest.fixture
def trace_repo(tmp_path):
    """Create a temporary trace repository for testing."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize git first (trace requires it)
    subprocess.run(
        ["git", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True
    )

    # Initialize trace
    subprocess.run(
        ["trc", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True
    )

    return repo_dir


def test_milestone_completion_categorizes_and_reparents_open_children(trace_repo):
    """
    WHEN Planner declares DONE with open children under root work item
    THEN all open children are categorized and reparented to new category parents
    AND the original root work item is closed
    """
    # Create root work item
    result = subprocess.run(
        ["trc", "create", "Test Spec Milestone", "--description", "Test spec for milestone completion"],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    root_id = result.stdout.split()[1].rstrip(":")

    # Create some open child work items with different characteristics
    result = subprocess.run(
        ["trc", "create", "Add authentication feature",
         "--description", "Implement user authentication with JWT tokens",
         "--parent", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    child1_id = result.stdout.split()[1].rstrip(":")

    result = subprocess.run(
        ["trc", "create", "Fix login bug",
         "--description", "Login button not responding on mobile",
         "--parent", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    child2_id = result.stdout.split()[1].rstrip(":")

    result = subprocess.run(
        ["trc", "create", "Refactor database layer",
         "--description", "Extract database logic into separate module",
         "--parent", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    child3_id = result.stdout.split()[1].rstrip(":")

    result = subprocess.run(
        ["trc", "create", "Update API documentation",
         "--description", "Document new authentication endpoints",
         "--parent", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    child4_id = result.stdout.split()[1].rstrip(":")

    # Import the milestone completion function
    from ralph2.milestone import complete_milestone

    # Execute milestone completion
    complete_milestone(root_id, str(trace_repo))

    # Verify root work item is closed
    result = subprocess.run(
        ["trc", "show", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    assert "Status:      closed" in result.stdout

    # Verify children have new parents (not the root)
    for child_id in [child1_id, child2_id, child3_id, child4_id]:
        result = subprocess.run(
            ["trc", "show", child_id],
            cwd=trace_repo,
            capture_output=True,
            text=True,
            check=True
        )
        # Should have a parent dependency listed
        assert "Dependencies:" in result.stdout
        assert "parent" in result.stdout
        # Parent should NOT be the root_id
        assert root_id not in result.stdout or "parent" not in result.stdout.split(root_id)[0]


def test_milestone_completion_creates_max_5_categories(trace_repo):
    """
    WHEN Planner declares DONE with many diverse open children
    THEN at most 5 category parents are created
    """
    # Create root work item
    result = subprocess.run(
        ["trc", "create", "Large Spec Milestone", "--description", "Test spec with many tasks"],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    root_id = result.stdout.split()[1].rstrip(":")

    # Create many diverse child work items (10 different types of work)
    task_types = [
        ("Feature: Add search", "Implement search functionality"),
        ("Feature: Add filters", "Add filter controls"),
        ("Bug: Fix pagination", "Pagination broken on page 2"),
        ("Bug: Fix sorting", "Sort order incorrect"),
        ("Refactor: Extract utils", "Move utility functions"),
        ("Refactor: Simplify API", "Clean up API interface"),
        ("Docs: API guide", "Document API endpoints"),
        ("Docs: User guide", "Write user documentation"),
        ("Test: Add unit tests", "Increase test coverage"),
        ("Test: Add e2e tests", "Add end-to-end tests"),
    ]

    child_ids = []
    for title, desc in task_types:
        result = subprocess.run(
            ["trc", "create", title, "--description", desc, "--parent", root_id],
            cwd=trace_repo,
            capture_output=True,
            text=True,
            check=True
        )
        child_id = result.stdout.split()[1].rstrip(":")
        child_ids.append(child_id)

    # Import the milestone completion function
    from ralph2.milestone import complete_milestone

    # Execute milestone completion
    new_parent_ids = complete_milestone(root_id, str(trace_repo))

    # Verify at most 5 category parents were created
    assert len(new_parent_ids) <= 5, f"Expected at most 5 categories, got {len(new_parent_ids)}"

    # Verify all children were reparented
    for child_id in child_ids:
        result = subprocess.run(
            ["trc", "show", child_id],
            cwd=trace_repo,
            capture_output=True,
            text=True,
            check=True
        )
        # Should have a parent dependency
        assert "parent" in result.stdout


def test_milestone_completion_handles_no_open_children(trace_repo):
    """
    WHEN Planner declares DONE with no open children
    THEN root work item is closed without creating category parents
    """
    # Create root work item
    result = subprocess.run(
        ["trc", "create", "Complete Spec", "--description", "All work done"],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    root_id = result.stdout.split()[1].rstrip(":")

    # Import the milestone completion function
    from ralph2.milestone import complete_milestone

    # Execute milestone completion
    new_parent_ids = complete_milestone(root_id, str(trace_repo))

    # Verify no new parents were created
    assert len(new_parent_ids) == 0

    # Verify root work item is closed
    result = subprocess.run(
        ["trc", "show", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    assert "Status:      closed" in result.stdout


def test_milestone_completion_uses_backlog_for_uncategorizable_items(trace_repo):
    """
    WHEN a child work item cannot be categorized
    THEN it is reparented to a "Backlog" category
    """
    # Create root work item
    result = subprocess.run(
        ["trc", "create", "Spec with misc items", "--description", "Some random work"],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    root_id = result.stdout.split()[1].rstrip(":")

    # Create a vague/uncategorizable child
    result = subprocess.run(
        ["trc", "create", "TODO",
         "--description", "Something unclear",
         "--parent", root_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    child_id = result.stdout.split()[1].rstrip(":")

    # Import the milestone completion function
    from ralph2.milestone import complete_milestone

    # Execute milestone completion
    new_parent_ids = complete_milestone(root_id, str(trace_repo))

    # Should have created at least one parent (Backlog)
    assert len(new_parent_ids) >= 1

    # Verify child was reparented
    result = subprocess.run(
        ["trc", "show", child_id],
        cwd=trace_repo,
        capture_output=True,
        text=True,
        check=True
    )
    assert "parent" in result.stdout
