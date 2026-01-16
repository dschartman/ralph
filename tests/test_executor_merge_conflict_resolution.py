"""Tests for Executor merge conflict resolution."""

import pytest
from unittest.mock import MagicMock, patch
from ralph2.agents.executor import run_executor


class TestExecutorMergeConflictResolution:
    """Test that executor attempts to resolve merge conflicts before abandoning."""

    @pytest.mark.asyncio
    async def test_executor_attempts_conflict_resolution_before_abandoning(self):
        """Test that executor invokes the agent to resolve conflicts when they occur."""
        git_commands = []
        query_call_count = [0]

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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                query_call_count[0] += 1
                msg = MagicMock(spec=AssistantMessage)

                if query_call_count[0] == 1:
                    # First call: normal work
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                else:
                    # Second call: conflict resolution attempt
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Resolved merge conflicts\nBlockers: None\nNotes: Fixed conflicts in file.py\nEfficiency Notes: None")]

                msg.result = "Work done"
                yield msg

            with patch('ralph2.agents.executor.query', side_effect=mock_query):
                result = await run_executor(
                    iteration_intent="Test task",
                    spec_content="Test spec",
                    memory="",
                    work_item_id="ralph-conflict-resolve"
                )

        # Verify the agent was called twice (once for work, once for conflict resolution)
        assert query_call_count[0] == 2, f"Expected 2 agent calls (work + conflict resolution), got {query_call_count[0]}"

    @pytest.mark.asyncio
    async def test_executor_abandons_if_conflict_resolution_fails(self):
        """Test that executor abandons branch if agent cannot resolve conflicts."""
        git_commands = []
        query_call_count = [0]

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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                query_call_count[0] += 1
                msg = MagicMock(spec=AssistantMessage)

                if query_call_count[0] == 1:
                    # First call: normal work
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                else:
                    # Second call: conflict resolution fails
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Attempted conflict resolution\nBlockers: Cannot resolve complex conflicts\nNotes: Conflicts too complex\nEfficiency Notes: None")]

                msg.result = "Work done"
                yield msg

            with patch('ralph2.agents.executor.query', side_effect=mock_query):
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
        query_call_count = [0]
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

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                query_call_count[0] += 1
                msg = MagicMock(spec=AssistantMessage)

                if query_call_count[0] == 1:
                    # First call: normal work
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work done\nBlockers: None\nNotes: Test\nEfficiency Notes: None")]
                else:
                    # Second call: successful conflict resolution
                    msg.content = [MagicMock(spec=TextBlock, text="EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Resolved merge conflicts and committed\nBlockers: None\nNotes: Fixed conflicts\nEfficiency Notes: None")]

                msg.result = "Work done"
                yield msg

            with patch('ralph2.agents.executor.query', side_effect=mock_query):
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

        # Verify no branch deletion (successful merge)
        delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(delete_cmds) == 0, "Branch should not be deleted after successful merge"
