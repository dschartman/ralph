"""Tests for Executor git branch isolation."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from ralph2.agents.executor import run_executor


class TestExecutorGitBranchIsolation:
    """Test that executor creates and manages feature branches."""

    @pytest.mark.asyncio
    async def test_executor_creates_feature_branch(self):
        """Test that executor creates a feature branch ralph2/<work-item-id> before starting work."""
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
        mock_result.what_was_done = "Created branch"
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

        # Verify a branch creation command was issued (now via 'git branch')
        branch_create_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and 'ralph2/ralph-abc123' in ' '.join(cmd)]
        assert len(branch_create_cmds) > 0, "No branch creation command found"

        # Verify the branch name follows the pattern ralph2/<work-item-id>
        branch_cmd = branch_create_cmds[0]
        assert 'ralph2/ralph-abc123' in ' '.join(branch_cmd), f"Branch name incorrect: {branch_cmd}"

    @pytest.mark.asyncio
    async def test_executor_merges_branch_on_success(self):
        """Test that executor merges branch to main on successful completion."""
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
                        work_item_id="ralph-xyz789"
                    )

        # Verify merge sequence: checkout main, merge feature branch
        checkout_main_cmds = [cmd for cmd in git_commands if 'checkout' in ' '.join(cmd) and 'main' in ' '.join(cmd)]
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]

        assert len(checkout_main_cmds) > 0, "No checkout main command found"
        assert len(merge_cmds) > 0, "No merge command found"

        # Verify merge includes the feature branch
        merge_cmd = merge_cmds[0]
        assert 'ralph2/ralph-xyz789' in ' '.join(merge_cmd), f"Merge command doesn't reference feature branch: {merge_cmd}"

    @pytest.mark.asyncio
    async def test_executor_abandons_branch_on_blocked_status(self):
        """Test that executor abandons branch (doesn't merge) when status is Blocked."""
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

        # Verify no merge command was issued
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]
        assert len(merge_cmds) == 0, f"Merge should not happen on Blocked status, but found: {merge_cmds}"

        # Verify branch deletion command was issued
        delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(delete_cmds) > 0, "Branch should be deleted on Blocked status"

    @pytest.mark.asyncio
    async def test_executor_handles_merge_conflict(self):
        """Test that executor reports Blocked status when merge conflict occurs."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()

            # Simulate merge conflict
            if 'merge' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "CONFLICT: Merge conflict in file.py"
            else:
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
                        work_item_id="ralph-conflict1"
                    )

        # Verify status is Blocked due to merge conflict
        assert result["status"] == "Blocked", "Executor should report Blocked status on merge conflict"
        assert "merge conflict" in result["summary"].lower() or "conflict" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_executor_without_work_item_id_skips_git_isolation(self):
        """Test that executor without work_item_id doesn't create branches (backward compatibility)."""
        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
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
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                result = await run_executor(
                    iteration_intent="Test task",
                    spec_content="Test spec",
                    memory="",
                    work_item_id=None  # No work item ID
                )

        # Verify no git branch commands were issued
        branch_cmds = [cmd for cmd in git_commands if 'checkout' in ' '.join(cmd) and '-b' in cmd]
        assert len(branch_cmds) == 0, "No branch creation should happen without work_item_id"
