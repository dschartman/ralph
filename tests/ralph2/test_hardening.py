"""Tests for Ralph2 hardening: validation, GitBranchManager, and feedback duplicate checking."""

import pytest
import re
from unittest.mock import patch, MagicMock
import subprocess


class TestRootWorkItemIdValidation:
    """Tests for root_work_item_id validation."""

    def test_valid_work_item_id_format(self):
        """Test that valid work item IDs match expected format."""
        from ralph2.runner import validate_work_item_id

        valid_ids = [
            "ralph-1abc23",
            "proj-xyz789",
            "test-a1b2c3",
            "ralph2-abcdef",
            "tmpro-ddk9g-b2fi3m",  # Multi-segment ID (from temp dirs)
            "ralph2-executor-ralph-0ikoux",  # Nested/compound ID
        ]

        for work_item_id in valid_ids:
            assert validate_work_item_id(work_item_id) is True, f"Should be valid: {work_item_id}"

    def test_invalid_work_item_id_format(self):
        """Test that invalid work item IDs are rejected."""
        from ralph2.runner import validate_work_item_id

        invalid_ids = [
            "",
            "nohyphen",
            "123-456",  # Starts with numbers
            "abc",  # Missing second part
            "../etc/passwd",  # Path traversal attempt
            "ralph; rm -rf /",  # Command injection attempt
            "ralph`whoami`test",  # Backtick injection
            "ralph$(cat /etc/passwd)",  # Subshell injection
            "-startswithhyphen",  # Starts with hyphen
            "ends-with-hyphen-",  # Ends with hyphen
        ]

        for work_item_id in invalid_ids:
            assert validate_work_item_id(work_item_id) is False, f"Should be invalid: {work_item_id}"

    def test_ensure_root_work_item_validates_input(self):
        """Test that _ensure_root_work_item validates provided ID before subprocess call."""
        from ralph2.runner import Ralph2Runner
        from ralph2.project import ProjectContext
        from unittest.mock import MagicMock

        # Create mock project context
        mock_ctx = MagicMock(spec=ProjectContext)
        mock_ctx.project_root = "/tmp/test"
        mock_ctx.db_path = "/tmp/test/.ralph2/state.db"
        mock_ctx.outputs_dir = "/tmp/test/.ralph2/outputs"

        # Create mock for spec file reading
        with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value="# Test Spec")))))):
            with patch("ralph2.runner.Ralph2DB"):
                # Test with invalid work item ID - should raise error
                with pytest.raises(ValueError) as exc_info:
                    runner = Ralph2Runner(
                        spec_path="test.md",
                        project_context=mock_ctx,
                        root_work_item_id="../malicious/path"
                    )

                assert "Invalid work item ID format" in str(exc_info.value)


class TestFeedbackDuplicateChecking:
    """Tests for feedback duplicate checking."""

    def test_duplicate_feedback_not_created(self):
        """Test that duplicate feedback items are not created as work items."""
        from ralph2.feedback import create_work_items_from_feedback

        with patch("subprocess.run") as mock_run:
            # First call: children (returns one matching)
            # Second call: create would be skipped

            def side_effect(*args, **kwargs):
                cmd = args[0]
                if "trc" in cmd and "children" in cmd:
                    # Return existing work item that matches
                    return MagicMock(
                        returncode=0,
                        stdout="ralph-existing123 [open] Add error handling"
                    )
                elif "trc" in cmd and "create" in cmd:
                    return MagicMock(
                        returncode=0,
                        stdout="Created ralph-new456: Add error handling"
                    )
                return MagicMock(returncode=0)

            mock_run.side_effect = side_effect

            feedback_items = ["Add error handling"]  # Same as existing

            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-root123",
                project_root="/project"
            )

            # Should not create duplicates
            # The create command should not have been called for the duplicate
            create_calls = [c for c in mock_run.call_args_list if "create" in str(c)]
            # Duplicate should have been detected and skipped
            assert len(created_ids) == 0

    def test_non_duplicate_feedback_created(self):
        """Test that non-duplicate feedback items are created as work items."""
        from ralph2.feedback import create_work_items_from_feedback

        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if "trc" in cmd and "children" in cmd:
                    # Return existing items - none match
                    return MagicMock(
                        returncode=0,
                        stdout=""  # No existing children
                    )
                elif "trc" in cmd and "create" in cmd:
                    return MagicMock(
                        returncode=0,
                        stdout="Created ralph-new456: New unique feedback"
                    )
                return MagicMock(returncode=0)

            mock_run.side_effect = side_effect

            feedback_items = ["New unique feedback"]

            created_ids = create_work_items_from_feedback(
                feedback_items=feedback_items,
                specialist_name="code_reviewer",
                root_work_item_id="ralph-root123",
                project_root="/project"
            )

            # Should create the new item
            assert len(created_ids) == 1
            assert created_ids[0] == "ralph-new456"

    def test_is_duplicate_feedback_exact_match(self):
        """Test that exact title matches are detected as duplicates."""
        from ralph2.feedback import _is_duplicate_feedback

        existing = {"add error handling", "fix bug"}
        assert _is_duplicate_feedback("Add error handling", existing) is True

    def test_is_duplicate_feedback_substring_match(self):
        """Test that substring matches are detected as duplicates."""
        from ralph2.feedback import _is_duplicate_feedback

        existing = {"add error handling to api endpoints"}
        assert _is_duplicate_feedback("Add error handling", existing) is True
        assert _is_duplicate_feedback("error handling to api", existing) is True

    def test_is_duplicate_feedback_no_match(self):
        """Test that non-matching titles are not flagged as duplicates."""
        from ralph2.feedback import _is_duplicate_feedback

        existing = {"add error handling", "fix bug"}
        assert _is_duplicate_feedback("Refactor database module", existing) is False


class TestRunnerRefactoring:
    """Tests for Runner.run() refactoring into smaller methods."""

    def test_run_method_calls_smaller_methods(self):
        """Test that run() delegates to smaller, focused methods."""
        # This is a structural test - we verify the method exists and is callable
        from ralph2.runner import Ralph2Runner

        # Verify refactored methods exist
        assert hasattr(Ralph2Runner, '_initialize_run')
        assert hasattr(Ralph2Runner, '_run_planner_phase')
        assert hasattr(Ralph2Runner, '_run_executor_phase')
        assert hasattr(Ralph2Runner, '_run_feedback_phase')
        assert hasattr(Ralph2Runner, '_handle_human_inputs')
        assert hasattr(Ralph2Runner, '_setup_root_work_item')
        assert hasattr(Ralph2Runner, '_check_planner_decision')

        # All should be callable
        assert callable(getattr(Ralph2Runner, '_initialize_run', None))
        assert callable(getattr(Ralph2Runner, '_run_planner_phase', None))
        assert callable(getattr(Ralph2Runner, '_run_executor_phase', None))
        assert callable(getattr(Ralph2Runner, '_run_feedback_phase', None))
        assert callable(getattr(Ralph2Runner, '_handle_human_inputs', None))
        assert callable(getattr(Ralph2Runner, '_setup_root_work_item', None))
        assert callable(getattr(Ralph2Runner, '_check_planner_decision', None))

    def test_smaller_methods_exist_and_are_documented(self):
        """Test that smaller methods have docstrings."""
        from ralph2.runner import Ralph2Runner

        # Check docstrings exist for key refactored methods
        for method_name in [
            '_initialize_run', '_run_planner_phase', '_run_executor_phase',
            '_run_feedback_phase', '_handle_human_inputs', '_setup_root_work_item',
            '_check_planner_decision', '_resume_run', '_create_new_run'
        ]:
            method = getattr(Ralph2Runner, method_name, None)
            assert method is not None, f"{method_name} should exist"
            assert method.__doc__ is not None, f"{method_name} should have a docstring"

    def test_run_method_is_concise(self):
        """Test that the main run() method is concise and delegates work."""
        from ralph2.runner import Ralph2Runner
        import inspect

        # Get the source of the run method
        source = inspect.getsource(Ralph2Runner.run)
        lines = [l for l in source.split('\n') if l.strip() and not l.strip().startswith('#')]

        # The main run() method should be reasonably short (under ~60 lines)
        # This allows for setup, loop, and cleanup while delegating heavy work
        assert len(lines) < 70, f"run() method should be < 70 lines, got {len(lines)}"
