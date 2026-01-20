"""Tests for GitBranchManager integration in executor.py.

This test module verifies that executor.py uses GitBranchManager
for worktree operations instead of standalone functions, as required
by the spec:
- 'Git operations extracted to GitBranchManager class with guaranteed cleanup'
- 'worktree paths include run_id to prevent conflicts'
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestExecutorUsesGitBranchManager:
    """Test that executor uses GitBranchManager for git operations."""

    def test_run_executor_accepts_run_id_parameter(self):
        """Test that run_executor accepts a run_id parameter for parallel execution isolation."""
        import inspect
        from ralph2.agents.executor import run_executor

        sig = inspect.signature(run_executor)
        param_names = list(sig.parameters.keys())

        # run_executor should accept run_id parameter
        assert "run_id" in param_names, (
            "run_executor should accept run_id parameter for worktree path isolation"
        )

    @pytest.mark.asyncio
    async def test_executor_uses_git_branch_manager_context(self):
        """Test that executor uses GitBranchManager context manager when work_item_id is provided."""
        from ralph2.agents.executor import run_executor

        # Mock GitBranchManager
        mock_manager = MagicMock()
        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
        mock_manager.__exit__ = MagicMock(return_value=False)
        mock_manager.worktree_path = "/mock/worktree"
        mock_manager.merge_to_main = MagicMock(return_value=(True, ""))
        mock_manager.check_merge_conflicts = MagicMock(return_value=(False, ""))
        mock_manager.cleanup = MagicMock(return_value=True)

        # Mock the agent execution
        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Test completed"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None

        with patch('ralph2.agents.executor.GitBranchManager', return_value=mock_manager) as mock_gbm_class:
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                with patch('os.getcwd', return_value='/mock/repo'):
                    result = await run_executor(
                        iteration_intent="Test intent",
                        spec_content="Test spec",
                        work_item_id="ralph-test1",
                        run_id="run-abc123"
                    )

        # Verify GitBranchManager was instantiated with correct arguments
        mock_gbm_class.assert_called_once()
        call_kwargs = mock_gbm_class.call_args[1]
        assert call_kwargs.get('work_item_id') == "ralph-test1"
        assert call_kwargs.get('run_id') == "run-abc123"

    @pytest.mark.asyncio
    async def test_executor_passes_run_id_to_git_branch_manager(self):
        """Test that executor passes run_id to GitBranchManager for path isolation."""
        from ralph2.agents.executor import run_executor

        captured_args = {}

        class MockGitBranchManager:
            def __init__(self, **kwargs):
                captured_args.update(kwargs)
                self.worktree_path = "/mock/worktree"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def merge_to_main(self):
                return True, ""

            def cleanup(self):
                return True

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Test completed"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None

        with patch('ralph2.agents.executor.GitBranchManager', MockGitBranchManager):
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                with patch('os.getcwd', return_value='/mock/repo'):
                    result = await run_executor(
                        iteration_intent="Test intent",
                        spec_content="Test spec",
                        work_item_id="ralph-test1",
                        run_id="ralph2-run-xyz789"
                    )

        # Verify run_id was passed
        assert "run_id" in captured_args
        assert captured_args["run_id"] == "ralph2-run-xyz789"

    @pytest.mark.asyncio
    async def test_executor_guaranteed_cleanup_on_exception(self):
        """Test that GitBranchManager guarantees cleanup even when agent fails."""
        from ralph2.agents.executor import run_executor

        cleanup_called = [False]

        class MockGitBranchManager:
            def __init__(self, **kwargs):
                self.worktree_path = "/mock/worktree"
                self._worktree_created = False

            def __enter__(self):
                self._worktree_created = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self._worktree_created:
                    cleanup_called[0] = True
                return False

            def merge_to_main(self):
                return True, ""

            def cleanup(self):
                return True

        with patch('ralph2.agents.executor.GitBranchManager', MockGitBranchManager):
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                # Make agent raise an exception
                mock_agent.side_effect = Exception("Agent crashed")

                with patch('os.getcwd', return_value='/mock/repo'):
                    # Even though agent crashes, cleanup should be guaranteed
                    result = await run_executor(
                        iteration_intent="Test intent",
                        spec_content="Test spec",
                        work_item_id="ralph-test1",
                        run_id="run-abc123"
                    )

        # Cleanup should have been called via context manager __exit__
        assert cleanup_called[0], "Cleanup should be called even when agent fails"

    @pytest.mark.asyncio
    async def test_executor_without_work_item_does_not_use_git_manager(self):
        """Test that executor doesn't use GitBranchManager when no work_item_id is provided."""
        from ralph2.agents.executor import run_executor

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Test completed"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None

        with patch('ralph2.agents.executor.GitBranchManager') as mock_gbm_class:
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                result = await run_executor(
                    iteration_intent="Test intent",
                    spec_content="Test spec",
                    # No work_item_id or run_id
                )

        # GitBranchManager should NOT be called when no work_item_id
        mock_gbm_class.assert_not_called()


class TestExecutorGitIntegrationBranches:
    """Test different execution paths with GitBranchManager integration."""

    @pytest.mark.asyncio
    async def test_executor_merge_success_path(self):
        """Test executor handles successful merge via GitBranchManager."""
        from ralph2.agents.executor import run_executor

        merge_called = [False]
        exit_called = [False]  # Context manager __exit__ for cleanup

        class MockGitBranchManager:
            def __init__(self, **kwargs):
                self.worktree_path = "/mock/worktree"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                exit_called[0] = True  # Context manager handles cleanup
                return False

            def merge_to_main(self):
                merge_called[0] = True
                return True, ""

            def cleanup(self):
                return True

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Test completed"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None

        with patch('ralph2.agents.executor.GitBranchManager', MockGitBranchManager):
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                with patch('os.getcwd', return_value='/mock/repo'):
                    result = await run_executor(
                        iteration_intent="Test intent",
                        spec_content="Test spec",
                        work_item_id="ralph-test1",
                        run_id="run-abc123"
                    )

        assert merge_called[0], "merge_to_main should be called on Completed status"
        # Context manager __exit__ handles cleanup automatically
        assert exit_called[0], "Context manager __exit__ should be called for cleanup"

    @pytest.mark.asyncio
    async def test_executor_blocked_status_abandons_worktree(self):
        """Test that Blocked status abandons worktree without merging."""
        from ralph2.agents.executor import run_executor

        merge_called = [False]
        exit_called = [False]  # Context manager __exit__ for cleanup

        class MockGitBranchManager:
            def __init__(self, **kwargs):
                self.worktree_path = "/mock/worktree"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                exit_called[0] = True  # Context manager handles cleanup
                return False

            def merge_to_main(self):
                merge_called[0] = True
                return True, ""

            def cleanup(self):
                return True

        mock_result = MagicMock()
        mock_result.status = "Blocked"
        mock_result.what_was_done = "Got stuck"
        mock_result.blockers = "Missing dependency"
        mock_result.notes = None
        mock_result.efficiency_notes = None

        with patch('ralph2.agents.executor.GitBranchManager', MockGitBranchManager):
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                with patch('os.getcwd', return_value='/mock/repo'):
                    result = await run_executor(
                        iteration_intent="Test intent",
                        spec_content="Test spec",
                        work_item_id="ralph-test1",
                        run_id="run-abc123"
                    )

        # On Blocked status, should NOT merge but should cleanup via __exit__
        assert not merge_called[0], "Should NOT merge on Blocked status"
        # Context manager __exit__ handles cleanup automatically
        assert exit_called[0], "Context manager __exit__ should be called for cleanup"
