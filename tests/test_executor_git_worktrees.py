"""Tests for Executor git worktree isolation.

This tests the worktree-based implementation that provides
true filesystem isolation for parallel executors.

Tests verify that:
- Executor uses cwd parameter instead of os.chdir() to avoid race conditions
- Git worktrees are created/cleaned up properly via GitBranchManager
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from ralph2.agents.executor import run_executor


class TestExecutorGitWorktrees:
    """Test that executor uses git worktrees for true parallel isolation."""

    @pytest.mark.asyncio
    async def test_executor_creates_worktree_instead_of_checkout(self):
        """Test that executor creates a git worktree for work item instead of using checkout."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Created worktree and worked"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                    mock_agent.return_value = (mock_result, "output", [])

                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-abc123"
                    )

        # Verify NO git checkout -b commands (old approach)
        checkout_create_cmds = [cmd for cmd in git_commands if 'checkout' in ' '.join(cmd) and '-b' in cmd]
        assert len(checkout_create_cmds) == 0, f"Should not use 'git checkout -b', found: {checkout_create_cmds}"

        # Verify git worktree add command was issued
        worktree_add_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd)]
        assert len(worktree_add_cmds) > 0, "No 'git worktree add' command found"

        # Verify the worktree path and branch name
        worktree_cmd = worktree_add_cmds[0]
        assert 'ralph2/ralph-abc123' in ' '.join(worktree_cmd), f"Branch name incorrect in worktree command: {worktree_cmd}"

    @pytest.mark.asyncio
    async def test_executor_passes_cwd_to_agent_instead_of_os_chdir(self):
        """Test that executor passes cwd parameter to agent options instead of calling os.chdir().

        This is the key fix for the parallel executor race condition - we MUST NOT
        use os.chdir() because it mutates shared process state.
        """
        captured_options = []
        chdir_calls = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        def mock_chdir(path):
            chdir_calls.append(path)

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        async def capturing_run_agent(prompt, options):
            captured_options.append(options)
            return (mock_result, "output", [])

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Patch os.chdir to track if it's called (it should NOT be)
            with patch('ralph2.agents.executor.os.chdir', side_effect=mock_chdir):
                with patch('os.getcwd', return_value='/mock/repo'):
                    with patch('ralph2.agents.executor._run_executor_agent', side_effect=capturing_run_agent):
                        result = await run_executor(
                            iteration_intent="Test task",
                            spec_content="Test spec",
                            memory="",
                            work_item_id="ralph-test1"
                        )

        # CRITICAL: os.chdir should NOT be called anymore
        assert len(chdir_calls) == 0, f"os.chdir should not be called, but was called with: {chdir_calls}"

        # Agent options should have cwd set to the worktree path
        assert len(captured_options) > 0, "Agent should have been called with options"
        agent_options = captured_options[0]
        assert agent_options.cwd is not None, "Agent options should have cwd set"
        assert 'ralph-test1' in agent_options.cwd, f"cwd should point to worktree for ralph-test1, got: {agent_options.cwd}"

    @pytest.mark.asyncio
    async def test_executor_merges_from_worktree_on_success(self):
        """Test that executor merges work from worktree to main on successful completion."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                    mock_agent.return_value = (mock_result, "output", [])

                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-merge1"
                    )

        # Verify merge command was issued
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]
        assert len(merge_cmds) > 0, "No merge command found"

        # Verify the merge references the feature branch
        merge_cmd = merge_cmds[0]
        assert 'ralph2/ralph-merge1' in ' '.join(merge_cmd), f"Merge command doesn't reference feature branch: {merge_cmd}"

    @pytest.mark.asyncio
    async def test_executor_removes_worktree_on_completion(self):
        """Test that executor cleans up worktree after completion (success or failure)."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                    mock_agent.return_value = (mock_result, "output", [])

                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-cleanup1"
                    )

        # Verify worktree remove command was issued
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_remove_cmds) > 0, "No 'git worktree remove' command found - worktree not cleaned up"

    @pytest.mark.asyncio
    async def test_executor_removes_worktree_on_blocked_status(self):
        """Test that executor cleans up worktree even when work is blocked/abandoned."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_result = MagicMock()
        mock_result.status = "Blocked"
        mock_result.what_was_done = "Partial work"
        mock_result.blockers = "Missing dependency"
        mock_result.notes = "Cannot proceed"
        mock_result.efficiency_notes = None
        mock_result.work_committed = False
        mock_result.traces_updated = True

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                    mock_agent.return_value = (mock_result, "output", [])

                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-blocked1"
                    )

        # Verify worktree remove command was issued
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_remove_cmds) > 0, "Worktree should be cleaned up even on Blocked status"

        # Verify branch deletion command was issued
        delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(delete_cmds) > 0, "Branch should be deleted on Blocked status"

    @pytest.mark.asyncio
    async def test_parallel_executors_have_isolated_worktrees(self):
        """Test that multiple parallel executors get separate worktree directories."""
        worktree_paths = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            # Capture worktree paths from 'git worktree add' commands
            if 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd):
                cmd_str = ' '.join(cmd)
                worktree_paths.append(cmd_str)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                    mock_agent.return_value = (mock_result, "output", [])

                    # Simulate two executors running in parallel
                    results = await asyncio.gather(
                        run_executor(
                            iteration_intent="Task 1",
                            spec_content="Test spec",
                            memory="",
                            work_item_id="ralph-task1"
                        ),
                        run_executor(
                            iteration_intent="Task 2",
                            spec_content="Test spec",
                            memory="",
                            work_item_id="ralph-task2"
                        )
                    )

        # Verify we created separate worktrees for each executor
        assert len(worktree_paths) >= 2, "Should create separate worktrees for parallel executors"

        # Verify the worktree paths are different (contain different work item IDs)
        assert 'ralph-task1' in worktree_paths[0], "First worktree should be for ralph-task1"
        assert 'ralph-task2' in worktree_paths[1], "Second worktree should be for ralph-task2"
