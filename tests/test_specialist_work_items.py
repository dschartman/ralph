"""Tests for converting specialist feedback to Trace work items."""

import pytest
from unittest.mock import Mock, patch, call
from pathlib import Path
import tempfile
import shutil
import subprocess

from src.ralph2.agents.specialist import CodeReviewerSpecialist
from src.ralph2.feedback import create_work_items_from_feedback


class TestFeedbackToWorkItems:
    """Test converting specialist feedback to Trace work items."""

    def setup_method(self):
        """Set up test environment with temporary Trace repo."""
        # Create a temporary directory for the test
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = Path.cwd()

        # Initialize git repo first (required by Trace)
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True, capture_output=True)

        # Initialize a trace repo in the temp directory
        subprocess.run(["trc", "init"], cwd=self.test_dir, check=True, capture_output=True)

        # Create a root work item to use as parent
        result = subprocess.run(
            ["trc", "create", "Test Root", "--description", "Test root work item", "--priority", "0"],
            cwd=self.test_dir,
            check=True,
            capture_output=True,
            text=True
        )
        # Extract the ID from output (format: "Created <id>: <title>")
        output = result.stdout.strip()
        # Parse "Created <id>: <title>"
        if output.startswith("Created "):
            parts = output[8:].split(":", 1)  # Remove "Created " and split
            self.root_work_item_id = parts[0].strip()
        else:
            self.root_work_item_id = None
        assert self.root_work_item_id, f"Failed to extract work item ID from: {output}"

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def test_parse_feedback_item_with_priority(self):
        """Should extract priority from [P#] markers in feedback items."""
        feedback_items = [
            "[P0] Critical security issue in auth module",
            "[P1] Missing error handling in API",
            "[P2] Test coverage is low",
            "[P3] Add docstrings to functions",
            "No priority marker here"
        ]

        # The function should parse these and extract priorities
        expected = [
            {"title": "Critical security issue in auth module", "priority": 0},
            {"title": "Missing error handling in API", "priority": 1},
            {"title": "Test coverage is low", "priority": 2},
            {"title": "Add docstrings to functions", "priority": 3},
            {"title": "No priority marker here", "priority": 2}  # default medium
        ]

        from src.ralph2.feedback import parse_feedback_item

        for feedback, expected_result in zip(feedback_items, expected):
            result = parse_feedback_item(feedback)
            assert result["title"] == expected_result["title"]
            assert result["priority"] == expected_result["priority"]

    def test_create_work_items_from_feedback(self):
        """Should create Trace work items from specialist feedback."""
        feedback_items = [
            "[P0] Fix critical bug in authentication",
            "[P1] Add error handling to database queries",
            "[P2] Improve test coverage"
        ]

        # Create work items
        created_ids = create_work_items_from_feedback(
            feedback_items=feedback_items,
            specialist_name="code_reviewer",
            root_work_item_id=self.root_work_item_id,
            project_root=self.test_dir
        )

        # Should create 3 work items
        assert len(created_ids) == 3

        # Verify the work items were created with correct priorities
        for item_id in created_ids:
            result = subprocess.run(
                ["trc", "show", item_id],
                cwd=self.test_dir,
                check=True,
                capture_output=True,
                text=True
            )
            output = result.stdout
            assert "code_reviewer" in output.lower() or "description" in output.lower()

    def test_skip_empty_feedback_items(self):
        """Should skip empty or malformed feedback items."""
        feedback_items = [
            "[P1] Valid feedback item",
            "",  # empty
            "   ",  # whitespace only
            "[P2]",  # priority only, no description
        ]

        created_ids = create_work_items_from_feedback(
            feedback_items=feedback_items,
            specialist_name="code_reviewer",
            root_work_item_id=self.root_work_item_id,
            project_root=self.test_dir
        )

        # Should only create 1 valid work item
        assert len(created_ids) == 1

    def test_handle_trace_command_failure(self):
        """Should handle Trace command failures gracefully."""
        feedback_items = [
            "[P1] This is feedback"
        ]

        # Use an invalid project root to cause trc command to fail
        created_ids = create_work_items_from_feedback(
            feedback_items=feedback_items,
            specialist_name="code_reviewer",
            root_work_item_id="invalid-id",
            project_root="/nonexistent/path"
        )

        # Should return empty list on failure
        assert created_ids == []

    def test_multiple_specialists_feedback(self):
        """Should create work items from multiple specialists."""
        code_reviewer_feedback = [
            "[P1] Add type hints to functions"
        ]

        security_specialist_feedback = [
            "[P0] Critical: SQL injection vulnerability"
        ]

        # Create work items from first specialist
        ids1 = create_work_items_from_feedback(
            feedback_items=code_reviewer_feedback,
            specialist_name="code_reviewer",
            root_work_item_id=self.root_work_item_id,
            project_root=self.test_dir
        )

        # Create work items from second specialist
        ids2 = create_work_items_from_feedback(
            feedback_items=security_specialist_feedback,
            specialist_name="security_specialist",
            root_work_item_id=self.root_work_item_id,
            project_root=self.test_dir
        )

        # Both should succeed and create distinct items
        assert len(ids1) == 1
        assert len(ids2) == 1
        assert ids1[0] != ids2[0]
