"""Tests for Executor merge conflict resolution."""

import os
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from ralph2.agents.executor import run_executor


class TestExecutorMergeConflictResolution:
    """Test that executor attempts to resolve merge conflicts before abandoning."""

    @pytest.mark.asyncio
    async def test_executor_attempts_conflict_resolution_before_abandoning(self):
        """Test that executor invokes the agent to resolve conflicts when they occur."""
        git_commands = []
        agent_call_count = [0]

        # Create a temporary directory to simulate the worktree
        temp_dir = tempfile.mkdtemp(prefix="ralph2-executor-ralph-conflict-resolve")

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()

            # Simulate merge conflict on first merge attempt
            if 'merge' in ' '.join(cmd) and 'ralph2/' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "CONFLICT: Merge conflict in file.py\nAutomatic merge failed; fix conflicts and then commit the result."
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""

            return result

        def create_mock_result(status="Completed"):
            mock_result = MagicMock()
            mock_result.status = status
            mock_result.what_was_done = "Work done" if agent_call_count[0] == 1 else "Resolved merge conflicts"
            mock_result.blockers = None
            mock_result.notes = None
            mock_result.efficiency_notes = None
            mock_result.work_committed = True
            mock_result.traces_updated = True
            return mock_result

        async def mock_run_agent(prompt, options):
            agent_call_count[0] += 1
            return (create_mock_result(), "output", [])

        try:
            with patch('subprocess.run', side_effect=mock_subprocess_run):
                with patch('os.getcwd', return_value='/mock/repo'):
                    with patch('ralph2.agents.executor._run_executor_agent', side_effect=mock_run_agent):
                        result = await run_executor(
                            iteration_intent="Test task",
                            spec_content="Test spec",
                            memory="",
                            work_item_id="ralph-conflict-resolve"
                        )

            # Verify the agent was called at least twice (once for work, once for conflict resolution)
            assert agent_call_count[0] >= 2, f"Expected at least 2 agent calls (work + conflict resolution), got {agent_call_count[0]}"
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_executor_abandons_if_conflict_resolution_fails(self):
        """Test that executor abandons branch if agent cannot resolve conflicts."""
        git_commands = []
        agent_call_count = [0]

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()

            # Simulate merge conflict that persists
            if 'merge' in ' '.join(cmd) and 'ralph2/' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "CONFLICT: Merge conflict in file.py"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""

            return result

        def create_mock_result():
            mock_result = MagicMock()
            agent_call_count[0] += 1
            if agent_call_count[0] == 1:
                # First call: normal work completed
                mock_result.status = "Completed"
                mock_result.what_was_done = "Work done"
            else:
                # Subsequent calls: conflict resolution fails
                mock_result.status = "Blocked"
                mock_result.what_was_done = "Attempted conflict resolution"
                mock_result.blockers = "Cannot resolve complex conflicts"
            mock_result.notes = None
            mock_result.efficiency_notes = None
            mock_result.work_committed = True
            mock_result.traces_updated = True
            return mock_result

        async def mock_run_agent(prompt, options):
            return (create_mock_result(), "output", [])

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', side_effect=mock_run_agent):
                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-conflict-fail"
                    )

        # Verify status is Blocked
        assert result["status"] == "Blocked", "Executor should report Blocked after failed conflict resolution"

        # Verify branch deletion was attempted
        delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(delete_cmds) > 0, "Branch should be deleted after failed conflict resolution"

    @pytest.mark.asyncio
    async def test_executor_succeeds_after_resolving_conflicts(self):
        """Test that executor successfully completes after resolving conflicts."""
        git_commands = []
        agent_call_count = [0]
        merge_attempt_count = [0]

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()

            # Simulate merge conflict on first attempt, success on second
            if 'merge' in ' '.join(cmd) and 'ralph2/' in ' '.join(cmd):
                merge_attempt_count[0] += 1
                if merge_attempt_count[0] == 1:
                    result.returncode = 1
                    result.stderr = "CONFLICT: Merge conflict in file.py"
                else:
                    result.returncode = 0
                    result.stdout = "Merge successful"
                    result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""

            return result

        def create_mock_result():
            mock_result = MagicMock()
            agent_call_count[0] += 1
            mock_result.status = "Completed"
            if agent_call_count[0] == 1:
                mock_result.what_was_done = "Work done"
            else:
                mock_result.what_was_done = "Resolved merge conflicts and committed"
            mock_result.blockers = None
            mock_result.notes = None
            mock_result.efficiency_notes = None
            mock_result.work_committed = True
            mock_result.traces_updated = True
            return mock_result

        async def mock_run_agent(prompt, options):
            return (create_mock_result(), "output", [])

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('os.getcwd', return_value='/mock/repo'):
                with patch('ralph2.agents.executor._run_executor_agent', side_effect=mock_run_agent):
                    result = await run_executor(
                        iteration_intent="Test task",
                        spec_content="Test spec",
                        memory="",
                        work_item_id="ralph-conflict-success"
                    )

        # Verify status is Completed
        assert result["status"] == "Completed", "Executor should report Completed after successful conflict resolution"

        # Verify merge was attempted twice
        assert merge_attempt_count[0] == 2, f"Expected 2 merge attempts, got {merge_attempt_count[0]}"

        # Verify branch deletion occurred (successful merge cleanup)
        delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(delete_cmds) > 0, "Branch should be deleted after successful merge as part of cleanup"
