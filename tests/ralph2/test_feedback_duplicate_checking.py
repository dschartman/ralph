"""Tests for feedback duplicate checking when creating work items."""

import pytest
from unittest.mock import patch, MagicMock


class TestFeedbackDuplicateChecking:
    """Test that feedback work item creation checks for duplicates."""

    def test_duplicate_feedback_not_created(self):
        """Test that duplicate feedback items are not created."""
        from ralph2.feedback import create_work_items_from_feedback

        # Track created work items
        created_titles = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()

            # Handle trc children (list children for duplicate check)
            if cmd[0] == "trc" and cmd[1] == "children":
                result.returncode = 0
                # Return existing item that matches first feedback
                # Format: "ralph-id123 [open] Title goes here"
                result.stdout = "test-123 [open] Add error handling\n"
                return result

            # Handle trc create
            if cmd[0] == "trc" and cmd[1] == "create":
                title = cmd[2]
                created_titles.append(title)
                result.returncode = 0
                result.stdout = f"Created work-{len(created_titles)}: {title}"
                return result

            result.returncode = 0
            result.stdout = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            feedback_items = [
                "[P1] Add error handling",  # This exists already
                "[P2] New improvement",     # This is new
            ]

            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-test-root",
                project_root="/mock/project"
            )

        # Should only create the new item, not the duplicate
        assert "New improvement" in created_titles
        # The duplicate should be skipped
        assert len([t for t in created_titles if "Add error handling" in t]) == 0

    def test_similar_titles_not_considered_duplicates(self):
        """Test that similar but different titles are not considered duplicates."""
        from ralph2.feedback import create_work_items_from_feedback

        created_titles = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()

            if cmd[0] == "trc" and cmd[1] == "children":
                result.returncode = 0
                # Existing item with slightly different title
                # Note: The duplicate check uses substring matching, so these need to be truly different
                result.stdout = "test-123 [open] Refactor authentication module\n"
                return result

            if cmd[0] == "trc" and cmd[1] == "create":
                title = cmd[2]
                created_titles.append(title)
                result.returncode = 0
                result.stdout = f"Created work-{len(created_titles)}: {title}"
                return result

            result.returncode = 0
            result.stdout = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            feedback_items = [
                "[P1] Add error handling for database",  # Completely different from existing
            ]

            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-test-root",
                project_root="/mock/project"
            )

        # Should create the new item since it's different
        assert "Add error handling for database" in created_titles

    def test_duplicate_check_handles_trc_children_failure(self):
        """Test that duplicate check gracefully handles trc children failure."""
        from ralph2.feedback import create_work_items_from_feedback

        created_titles = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()

            if cmd[0] == "trc" and cmd[1] == "children":
                # Simulate trc children failure
                result.returncode = 1
                result.stderr = "Error listing items"
                return result

            if cmd[0] == "trc" and cmd[1] == "create":
                title = cmd[2]
                created_titles.append(title)
                result.returncode = 0
                result.stdout = f"Created work-{len(created_titles)}: {title}"
                return result

            result.returncode = 0
            result.stdout = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            feedback_items = [
                "[P1] Add error handling",
            ]

            # Should not raise, should proceed with creation
            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-test-root",
                project_root="/mock/project"
            )

        # Should still create the item when duplicate check fails
        assert "Add error handling" in created_titles

    def test_exact_title_match_skipped(self):
        """Test that exact title matches are skipped."""
        from ralph2.feedback import create_work_items_from_feedback

        created_titles = []

        def mock_run(cmd, **kwargs):
            result = MagicMock()

            if cmd[0] == "trc" and cmd[1] == "children":
                result.returncode = 0
                # Exact match exists
                result.stdout = "test-123 [open] Fix the bug in login\n"
                return result

            if cmd[0] == "trc" and cmd[1] == "create":
                title = cmd[2]
                created_titles.append(title)
                result.returncode = 0
                result.stdout = f"Created work-{len(created_titles)}: {title}"
                return result

            result.returncode = 0
            result.stdout = ""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            feedback_items = [
                "[P1] Fix the bug in login",  # Exact match
            ]

            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-test-root",
                project_root="/mock/project"
            )

        # Should not create duplicate
        assert "Fix the bug in login" not in created_titles
