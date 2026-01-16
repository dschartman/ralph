"""Tests for Ralph2Runner refactoring - verifying smaller methods.

The spec requires: `Ralph2Runner.run()` broken into smaller methods (each < 50 lines)
"""

import pytest
import inspect
from ralph2.runner import Ralph2Runner


class TestRunnerMethodSizes:
    """Test that Runner methods are small enough (<50 lines each)."""

    MAX_METHOD_LINES = 50

    def _get_method_line_count(self, method) -> int:
        """Get the number of lines in a method body."""
        source = inspect.getsource(method)
        # Count non-empty, non-comment lines in the method body
        lines = source.split('\n')
        # Find the start of the method body (after the def line and docstring)
        in_docstring = False
        body_started = False
        code_lines = 0

        for line in lines:
            stripped = line.strip()

            # Skip the def line
            if stripped.startswith('def ') or stripped.startswith('async def '):
                body_started = True
                continue

            if not body_started:
                continue

            # Handle docstrings
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                    continue
                elif stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    # Single-line docstring
                    continue
                else:
                    in_docstring = True
                    continue

            if in_docstring:
                continue

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            code_lines += 1

        return code_lines

    def test_run_method_under_50_lines(self):
        """The main run() method should be under 50 lines."""
        line_count = self._get_method_line_count(Ralph2Runner.run)
        assert line_count <= self.MAX_METHOD_LINES, (
            f"run() method has {line_count} lines of code, "
            f"should be <= {self.MAX_METHOD_LINES} lines"
        )

    def test_all_public_methods_under_50_lines(self):
        """All public methods should be under 50 lines each."""
        methods = inspect.getmembers(Ralph2Runner, predicate=inspect.isfunction)

        oversized_methods = []
        for name, method in methods:
            if name.startswith('_'):
                continue  # Skip private methods
            try:
                line_count = self._get_method_line_count(method)
                if line_count > self.MAX_METHOD_LINES:
                    oversized_methods.append((name, line_count))
            except (OSError, TypeError):
                # Can't inspect built-in or C methods
                pass

        assert not oversized_methods, (
            f"The following public methods exceed {self.MAX_METHOD_LINES} lines: "
            f"{oversized_methods}"
        )

    def test_private_helper_methods_exist(self):
        """Runner should have helper methods for run() phases."""
        # These are the helper methods we expect after refactoring
        expected_helpers = [
            '_run_planner_phase',
            '_run_executor_phase',
            '_run_feedback_phase',
            '_handle_human_inputs',
        ]

        runner_methods = [name for name, _ in inspect.getmembers(Ralph2Runner, predicate=inspect.isfunction)]

        for helper in expected_helpers:
            assert helper in runner_methods, (
                f"Expected helper method '{helper}' not found in Ralph2Runner. "
                f"Available methods: {runner_methods}"
            )
