"""Tests for Executor git worktree isolation.

This tests the NEW worktree-based implementation that provides
true filesystem isolation for parallel executors.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import subprocess

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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            # Mock os.chdir and os.getcwd to avoid actual filesystem changes
            with patch('os.chdir'):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Created worktree and worked\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                        msg.result = "Work done"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
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
    async def test_executor_passes_worktree_path_to_agent(self):
        """Test that executor changes working directory to the worktree before running the agent."""
        git_commands = []
        chdir_calls = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        def mock_chdir(path):
            chdir_calls.append(path)

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.chdir', side_effect=mock_chdir):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                        msg.result = "Work done"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
                        result = await run_executor(
                            iteration_intent="Test task",
                            spec_content="Test spec",
                            memory="",
                            work_item_id="ralph-test1"
                        )

        # Verify that chdir was called to switch to worktree and back
        assert len(chdir_calls) >= 1, "Should have called os.chdir to change to worktree"
        # First call should be to the worktree directory
        assert 'ralph-test1' in chdir_calls[0], f"First chdir should be to worktree, got: {chdir_calls[0]}"

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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.chdir'):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                        msg.result = "Work done"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.chdir'):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                        msg.result = "Work done"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.chdir'):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Partial work\nBlockers: Missing dependency\nNotes: Cannot proceed\nEfficiency Notes: None")]
                        msg.result = "Blocked"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
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
                # Extract the path (second argument after 'add')
                cmd_str = ' '.join(cmd)
                # Simple extraction - in real command would be like: git worktree add /path/to/worktree branch
                worktree_paths.append(cmd_str)

            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.chdir'):
                with patch('os.getcwd', return_value='/mock/repo'):
                    async def mock_query(*args, **kwargs):
                        from claude_agent_sdk.types import AssistantMessage, TextBlock

                        msg = MagicMock(spec=AssistantMessage)
                        msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                        msg.result = "Work done"
                        yield msg

                    with patch('ralph2.agents.executor.query', side_effect=mock_query):
                        # Simulate two executors running in parallel
                        import asyncio
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
