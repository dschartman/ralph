"""Tests for refactoring tasks: atomic file write, iteration summaries extraction, and conflict resolution extraction.

These tests verify:
1. Atomic file write for project ID (ralph-1vsr70)
2. _get_last_iteration_summaries() extraction in runner.py (ralph-t7wnpl)
3. _attempt_conflict_resolution() extraction in executor.py (ralph-45te54)
"""

import pytest
import tempfile
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestAtomicFileWrite:
    """Tests for atomic file write in get_project_id."""

    def test_atomic_write_creates_file(self):
        """Test that atomic write creates the file correctly."""
        from ralph2.project import get_project_id, RALPH2_ID_FILENAME
        import uuid

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            project_id = get_project_id(project_root)

            # Should be a valid UUID
            uuid.UUID(project_id)

            # File should exist with correct content
            id_file = project_root / RALPH2_ID_FILENAME
            assert id_file.exists()
            assert id_file.read_text().strip() == project_id

    def test_atomic_write_uses_temp_file(self):
        """Test that atomic write uses a temp file before renaming.

        The implementation uses os.link + os.unlink for exclusive creation,
        with fallback to os.replace. We verify by checking for temp file usage
        through mkstemp tracking.
        """
        from ralph2.project import get_project_id, RALPH2_ID_FILENAME

        # Track mkstemp calls to verify temp file pattern
        import tempfile as tf
        original_mkstemp = tf.mkstemp
        mkstemp_calls = []

        def tracking_mkstemp(*args, **kwargs):
            result = original_mkstemp(*args, **kwargs)
            mkstemp_calls.append((args, kwargs, result))
            return result

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch('tempfile.mkstemp', side_effect=tracking_mkstemp):
                project_id = get_project_id(project_root)

            # Should have used mkstemp for temp file creation
            assert len(mkstemp_calls) == 1
            args, kwargs, (fd, temp_path) = mkstemp_calls[0]
            # Should have used .ralph2-id- prefix
            assert kwargs.get('prefix') == '.ralph2-id-' or (len(args) > 1 and '.ralph2-id-' in str(args))
            # Dir should be project root
            assert kwargs.get('dir') == project_root or (args and args[0] == project_root)

    def test_atomic_write_no_partial_content_on_failure(self):
        """Test that failed writes don't leave partial files.

        We simulate a failure during the atomic write by making os.link fail
        (after mkstemp succeeds but before the link completes). The implementation
        should clean up the temp file.
        """
        from ralph2.project import get_project_id, RALPH2_ID_FILENAME

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            id_path = project_root / RALPH2_ID_FILENAME

            # Simulate os.write failure (happens before any atomic ops)
            with patch('os.write', side_effect=OSError("Simulated write failure")):
                with pytest.raises(OSError):
                    get_project_id(project_root)

            # The actual file should not exist (no partial write)
            assert not id_path.exists()
            # Also no temp files should be left (cleanup should have run)
            temp_files = list(project_root.glob('.ralph2-id-*'))
            assert len(temp_files) == 0, f"Temp files left behind: {temp_files}"

    def test_atomic_write_idempotent(self):
        """Test that multiple calls return the same ID."""
        from ralph2.project import get_project_id

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            id1 = get_project_id(project_root)
            id2 = get_project_id(project_root)

            assert id1 == id2

    def test_concurrent_atomic_writes(self):
        """Test that concurrent writes don't corrupt the file."""
        from ralph2.project import get_project_id

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            results = []
            errors = []

            def write_id():
                try:
                    result = get_project_id(project_root)
                    results.append(result)
                except Exception as e:
                    errors.append(e)

            # Launch multiple concurrent writes
            threads = [threading.Thread(target=write_id) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # No errors should have occurred
            assert not errors, f"Concurrent write errors: {errors}"

            # All results should be the same (first one won)
            assert len(set(results)) == 1, "Concurrent writes produced different IDs"


class TestIterationSummariesExtraction:
    """Tests for _get_last_iteration_summaries helper method extraction.

    The original task (ralph-t7wnpl) was to extract complex nested conditionals
    for last_* variable initialization into a helper method. The method is
    named _get_last_iteration_summaries and takes run_id and last_iteration.
    """

    def test_helper_method_exists(self):
        """Test that _get_last_iteration_summaries method exists on Ralph2Runner."""
        from ralph2.runner import Ralph2Runner
        import inspect

        methods = [name for name, _ in inspect.getmembers(Ralph2Runner, predicate=inspect.isfunction)]
        assert '_get_last_iteration_summaries' in methods, (
            f"_get_last_iteration_summaries not found in Ralph2Runner. "
            f"Available methods with 'last' or 'iteration': {[m for m in methods if 'last' in m.lower() or 'iteration' in m.lower()]}"
        )

    def test_helper_returns_three_values(self):
        """Test that _get_last_iteration_summaries returns a tuple of three strings/None."""
        from ralph2.runner import Ralph2Runner
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import AgentOutput, Iteration
        from unittest.mock import MagicMock
        from datetime import datetime

        # Create mock runner
        mock_db = MagicMock(spec=Ralph2DB)
        mock_runner = MagicMock(spec=Ralph2Runner)
        mock_runner.db = mock_db

        mock_iteration = Iteration(
            id=1, run_id="test-run", number=1, intent="test",
            outcome="test", started_at=datetime.now()
        )

        mock_outputs = [
            AgentOutput(
                id=1, iteration_id=1, agent_type="executor",
                raw_output_path="/tmp/test", summary="executor summary"
            ),
            AgentOutput(
                id=2, iteration_id=1, agent_type="verifier",
                raw_output_path="/tmp/test", summary="verifier assessment"
            ),
            AgentOutput(
                id=3, iteration_id=1, agent_type="specialist",
                raw_output_path="/tmp/test", summary="specialist feedback"
            ),
        ]

        mock_db.get_agent_outputs.return_value = mock_outputs

        # Call the method (unbound, passing self)
        result = Ralph2Runner._get_last_iteration_summaries(mock_runner, "test-run", mock_iteration)

        # Should return tuple of 3
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_helper_extracts_executor_summary(self):
        """Test extraction of executor summary."""
        from ralph2.runner import Ralph2Runner
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import AgentOutput, Iteration
        from unittest.mock import MagicMock
        from datetime import datetime

        mock_db = MagicMock(spec=Ralph2DB)
        mock_runner = MagicMock(spec=Ralph2Runner)
        mock_runner.db = mock_db

        mock_iteration = Iteration(
            id=1, run_id="test-run", number=1, intent="test",
            outcome="test", started_at=datetime.now()
        )

        mock_outputs = [
            AgentOutput(
                id=1, iteration_id=1, agent_type="executor",
                raw_output_path="/tmp/test", summary="executor did this work"
            ),
        ]
        mock_db.get_agent_outputs.return_value = mock_outputs

        last_exec, last_verify, last_spec = Ralph2Runner._get_last_iteration_summaries(
            mock_runner, "test-run", mock_iteration
        )

        assert last_exec == "executor did this work"

    def test_helper_returns_none_when_no_iteration(self):
        """Test that helper returns None values when no iteration exists."""
        from ralph2.runner import Ralph2Runner
        from unittest.mock import MagicMock

        mock_runner = MagicMock(spec=Ralph2Runner)

        result = Ralph2Runner._get_last_iteration_summaries(mock_runner, "test-run", None)

        assert result == (None, None, None)


class TestConflictResolutionExtraction:
    """Tests for _attempt_conflict_resolution method extraction."""

    def test_helper_function_exists(self):
        """Test that _attempt_conflict_resolution function exists."""
        from ralph2.agents import executor
        import inspect

        # Check for the function
        members = dict(inspect.getmembers(executor, predicate=inspect.isfunction))
        assert '_attempt_conflict_resolution' in members, (
            f"_attempt_conflict_resolution not found in executor module. "
            f"Available functions: {list(members.keys())}"
        )

    @pytest.mark.asyncio
    async def test_conflict_resolution_returns_executor_result(self):
        """Test that conflict resolution returns an ExecutorResult."""
        from ralph2.agents.executor import _attempt_conflict_resolution, ExecutorResult
        from claude_agent_sdk import ClaudeAgentOptions
        from ralph2.git import GitBranchManager
        from unittest.mock import MagicMock, AsyncMock, patch

        # Create mocks
        mock_result = ExecutorResult(
            status="Completed",
            what_was_done="test work",
            work_committed=True,
            traces_updated=True
        )

        mock_options = MagicMock(spec=ClaudeAgentOptions)
        mock_git_manager = MagicMock(spec=GitBranchManager)
        mock_git_manager.check_merge_conflicts.return_value = (False, "")
        mock_git_manager.merge_to_main.return_value = (True, None)

        with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = (
                ExecutorResult(status="Completed", what_was_done="resolved", work_committed=True, traces_updated=True),
                "output",
                []
            )

            result = await _attempt_conflict_resolution(
                original_result=mock_result,
                merge_error="CONFLICT in file.py",
                options=mock_options,
                git_manager=mock_git_manager
            )

        assert isinstance(result, ExecutorResult)

    @pytest.mark.asyncio
    async def test_conflict_resolution_handles_failure(self):
        """Test that conflict resolution handles failure gracefully."""
        from ralph2.agents.executor import _attempt_conflict_resolution, ExecutorResult
        from claude_agent_sdk import ClaudeAgentOptions
        from ralph2.git import GitBranchManager
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_result = ExecutorResult(
            status="Completed",
            what_was_done="test work",
            work_committed=True,
            traces_updated=True
        )

        mock_options = MagicMock(spec=ClaudeAgentOptions)
        mock_git_manager = MagicMock(spec=GitBranchManager)
        mock_git_manager.check_merge_conflicts.return_value = (True, "still conflicted")
        mock_git_manager.merge_to_main.return_value = (False, "merge failed")

        with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
            # Simulate agent failing to resolve
            mock_agent.return_value = (
                ExecutorResult(status="Blocked", what_was_done="failed", work_committed=False, traces_updated=False),
                "output",
                []
            )

            result = await _attempt_conflict_resolution(
                original_result=mock_result,
                merge_error="CONFLICT in file.py",
                options=mock_options,
                git_manager=mock_git_manager
            )

        # Should return Blocked status on failure
        assert result.status == "Blocked"
        assert "conflict" in result.what_was_done.lower() or "merge" in result.what_was_done.lower()

    @pytest.mark.asyncio
    async def test_conflict_resolution_agent_error_handled(self):
        """Test that agent errors during conflict resolution are handled."""
        from ralph2.agents.executor import _attempt_conflict_resolution, ExecutorResult
        from claude_agent_sdk import ClaudeAgentOptions
        from ralph2.git import GitBranchManager
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_result = ExecutorResult(
            status="Completed",
            what_was_done="test work",
            work_committed=True,
            traces_updated=True
        )

        mock_options = MagicMock(spec=ClaudeAgentOptions)
        mock_git_manager = MagicMock(spec=GitBranchManager)
        mock_git_manager.merge_to_main.return_value = (False, "still failed")

        with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = Exception("Agent crashed")

            result = await _attempt_conflict_resolution(
                original_result=mock_result,
                merge_error="CONFLICT in file.py",
                options=mock_options,
                git_manager=mock_git_manager
            )

        # Should return Blocked on error
        assert result.status == "Blocked"
