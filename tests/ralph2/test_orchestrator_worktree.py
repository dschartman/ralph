"""Tests for orchestrator-managed worktree lifecycle.

This module tests the new architecture where the orchestrator (runner.py)
manages worktree lifecycle instead of individual executors:

1. Standalone git functions (create_worktree, merge_branch_to_main, remove_worktree)
2. Executor behavior when worktree_path is provided (orchestrator mode)
3. Runner orchestrator methods (_create_worktrees, _merge_worktrees_serial, _cleanup_all_worktrees)
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


class TestStandaloneGitFunctions:
    """Test the standalone git functions for orchestrator use."""

    def test_create_worktree_success(self):
        """Test create_worktree creates branch and worktree."""
        from ralph2.git import create_worktree

        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            worktree_path, branch_name = create_worktree(
                work_item_id="ralph-test1",
                run_id="run-abc123",
                cwd="/mock/repo"
            )

        # Verify branch was created
        branch_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd)]
        assert len(branch_cmds) > 0, "Should create branch"
        assert 'ralph2/ralph-test1' in ' '.join(branch_cmds[0])

        # Verify worktree was created
        worktree_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd)]
        assert len(worktree_cmds) > 0, "Should create worktree"

        assert branch_name == "ralph2/ralph-test1"
        assert "ralph-test1" in worktree_path
        assert "run-abc123" in worktree_path

    def test_create_worktree_cleans_up_branch_on_failure(self):
        """Test create_worktree cleans up branch if worktree creation fails."""
        from ralph2.git import create_worktree

        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            # Branch creation succeeds
            if 'branch' in ' '.join(cmd) and '-D' not in cmd:
                result.returncode = 0
            # Worktree creation fails
            elif 'worktree' in ' '.join(cmd) and 'add' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "worktree failed"
            else:
                result.returncode = 0
            result.stdout = ""
            if not hasattr(result, 'stderr'):
                result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            with patch('ralph2.git._warn'):  # Suppress warning output
                with pytest.raises(RuntimeError, match="Failed to create worktree"):
                    create_worktree(
                        work_item_id="ralph-test1",
                        run_id="run-abc123",
                        cwd="/mock/repo"
                    )

        # Verify branch was cleaned up
        branch_delete_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(branch_delete_cmds) > 0, "Should delete branch on worktree failure"

    def test_merge_branch_to_main_success(self):
        """Test merge_branch_to_main successfully merges."""
        from ralph2.git import merge_branch_to_main

        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            success, error = merge_branch_to_main(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo"
            )

        assert success is True
        assert error == ""

        # Verify checkout main was called
        checkout_cmds = [cmd for cmd in git_commands if 'checkout' in ' '.join(cmd) and 'main' in ' '.join(cmd)]
        assert len(checkout_cmds) > 0, "Should checkout main"

        # Verify merge was called
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]
        assert len(merge_cmds) > 0, "Should merge branch"

    def test_merge_branch_to_main_conflict(self):
        """Test merge_branch_to_main handles merge conflict."""
        from ralph2.git import merge_branch_to_main

        def mock_subprocess_run(cmd, *args, **kwargs):
            result = MagicMock()
            if 'checkout' in ' '.join(cmd):
                result.returncode = 0
            elif 'merge' in ' '.join(cmd):
                result.returncode = 1
                result.stderr = "CONFLICT in file.py"
            elif 'status' in ' '.join(cmd):
                result.returncode = 0
                result.stdout = "UU file.py"
            else:
                result.returncode = 0
            result.stdout = getattr(result, 'stdout', "")
            result.stderr = getattr(result, 'stderr', "")
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            success, error = merge_branch_to_main(
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo"
            )

        assert success is False
        assert "conflict" in error.lower() or "file.py" in error.lower()

    def test_remove_worktree_success(self):
        """Test remove_worktree removes worktree and branch."""
        from ralph2.git import remove_worktree

        git_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            git_commands.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            success = remove_worktree(
                worktree_path="/mock/worktree/path",
                branch_name="ralph2/ralph-test1",
                cwd="/mock/repo"
            )

        assert success is True

        # Verify worktree remove was called
        worktree_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_cmds) > 0, "Should remove worktree"

        # Verify branch delete was called
        branch_cmds = [cmd for cmd in git_commands if 'branch' in ' '.join(cmd) and '-D' in cmd]
        assert len(branch_cmds) > 0, "Should delete branch"

    def test_remove_worktree_logs_failures(self):
        """Test remove_worktree logs but doesn't raise on failure."""
        from ralph2.git import remove_worktree

        def mock_subprocess_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            result.stderr = "error"
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run):
            with patch('ralph2.git._warn') as mock_warn:
                success = remove_worktree(
                    worktree_path="/mock/worktree/path",
                    branch_name="ralph2/ralph-test1",
                    cwd="/mock/repo"
                )

        assert success is False
        # Should have logged warnings for both failures
        assert mock_warn.call_count >= 1

    def test_abort_merge(self):
        """Test abort_merge aborts an in-progress merge."""
        from ralph2.git import abort_merge

        def mock_subprocess_run(cmd, *args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            return result

        with patch('ralph2.git._run_git_command', side_effect=mock_subprocess_run) as mock_run:
            success = abort_merge("/mock/repo")

        assert success is True
        # Verify abort was called with correct args
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'merge' in call_args
        assert '--abort' in call_args


class TestExecutorOrchestratorMode:
    """Test executor behavior when worktree_path is provided (orchestrator mode)."""

    @pytest.mark.asyncio
    async def test_executor_uses_provided_worktree_path(self):
        """Test executor uses worktree_path directly when provided."""
        from ralph2.agents.executor import run_executor

        captured_options = []

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

        with patch('ralph2.agents.executor._run_executor_agent', side_effect=capturing_run_agent):
            result = await run_executor(
                iteration_intent="Test task",
                spec_content="Test spec",
                memory="",
                work_item_id="ralph-test1",
                run_id="run-abc123",
                worktree_path="/provided/worktree/path"  # Orchestrator-provided
            )

        # Agent should have been called with cwd set to provided path
        assert len(captured_options) > 0
        agent_options = captured_options[0]
        assert agent_options.cwd == "/provided/worktree/path"

    @pytest.mark.asyncio
    async def test_executor_does_not_create_branch_when_worktree_provided(self):
        """Test executor doesn't create branch/worktree when worktree_path is provided."""
        from ralph2.agents.executor import run_executor

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = True
        mock_result.traces_updated = True

        with patch('ralph2.agents.executor.GitBranchManager') as mock_gbm:
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                result = await run_executor(
                    iteration_intent="Test task",
                    spec_content="Test spec",
                    memory="",
                    work_item_id="ralph-test1",
                    run_id="run-abc123",
                    worktree_path="/provided/worktree"
                )

        # GitBranchManager should NOT be called when worktree_path is provided
        mock_gbm.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_does_not_merge_when_worktree_provided(self):
        """Test executor skips merge when worktree_path is provided (orchestrator merges)."""
        from ralph2.agents.executor import run_executor

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
            with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
                mock_agent.return_value = (mock_result, "output", [])

                result = await run_executor(
                    iteration_intent="Test task",
                    spec_content="Test spec",
                    memory="",
                    work_item_id="ralph-test1",
                    run_id="run-abc123",
                    worktree_path="/provided/worktree"
                )

        # No merge commands should be issued
        merge_cmds = [cmd for cmd in git_commands if 'merge' in ' '.join(cmd)]
        assert len(merge_cmds) == 0, f"Should NOT merge when worktree_path provided, found: {merge_cmds}"

        # No worktree remove commands should be issued
        worktree_remove_cmds = [cmd for cmd in git_commands if 'worktree' in ' '.join(cmd) and 'remove' in ' '.join(cmd)]
        assert len(worktree_remove_cmds) == 0, "Should NOT cleanup when worktree_path provided"

    @pytest.mark.asyncio
    async def test_executor_still_verifies_commit_in_orchestrator_mode(self):
        """Test executor still verifies commit even in orchestrator mode."""
        from ralph2.agents.executor import run_executor

        mock_result = MagicMock()
        mock_result.status = "Completed"
        mock_result.what_was_done = "Work done"
        mock_result.blockers = None
        mock_result.notes = None
        mock_result.efficiency_notes = None
        mock_result.work_committed = False  # Agent says not committed
        mock_result.traces_updated = True

        with patch('ralph2.agents.executor._run_executor_agent', new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = (mock_result, "output", [])

            with patch('ralph2.agents.executor._check_uncommitted_changes', return_value=False):
                result = await run_executor(
                    iteration_intent="Test task",
                    spec_content="Test spec",
                    memory="",
                    work_item_id="ralph-test1",
                    run_id="run-abc123",
                    worktree_path="/provided/worktree"
                )

        # Should complete successfully
        assert result["status"] == "Completed"


class TestRunnerOrchestratorMethods:
    """Test runner orchestrator methods for worktree lifecycle management."""

    def test_runner_create_worktrees_creates_all(self):
        """Test _create_worktrees creates worktrees for all work items."""
        from ralph2.runner import Ralph2Runner

        work_items = [
            {"work_item_id": "ralph-task1"},
            {"work_item_id": "ralph-task2"},
            {"work_item_id": "ralph-task3"},
        ]

        created_worktrees = []

        def mock_create_worktree(work_item_id, run_id, cwd, base_branch=None):
            path = f"/mock/worktree/{work_item_id}"
            branch = f"ralph2/{work_item_id}"
            created_worktrees.append((work_item_id, path, branch))
            return path, branch

        # Create runner with mocked project_context
        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner._milestone_branch = None  # No milestone branch set

        with patch('ralph2.runner.create_worktree', side_effect=mock_create_worktree):
            result = runner._create_worktrees(work_items, "run-abc123")

        assert len(result) == 3
        assert len(created_worktrees) == 3

        # Verify all work items were processed
        created_ids = [wt[0] for wt in created_worktrees]
        assert "ralph-task1" in created_ids
        assert "ralph-task2" in created_ids
        assert "ralph-task3" in created_ids

    def test_runner_create_worktrees_handles_failures(self):
        """Test _create_worktrees continues even if some fail."""
        from ralph2.runner import Ralph2Runner

        work_items = [
            {"work_item_id": "ralph-task1"},
            {"work_item_id": "ralph-task2"},  # This one will fail
            {"work_item_id": "ralph-task3"},
        ]

        call_count = [0]

        def mock_create_worktree(work_item_id, run_id, cwd, base_branch=None):
            call_count[0] += 1
            if work_item_id == "ralph-task2":
                raise RuntimeError("Failed to create worktree")
            return f"/mock/worktree/{work_item_id}", f"ralph2/{work_item_id}"

        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner._milestone_branch = None  # No milestone branch set

        with patch('ralph2.runner.create_worktree', side_effect=mock_create_worktree):
            result = runner._create_worktrees(work_items, "run-abc123")

        # Should have attempted all 3
        assert call_count[0] == 3

        # Should return only 2 successful ones
        assert len(result) == 2
        result_ids = [wi["work_item_id"] for wi, _, _ in result]
        assert "ralph-task1" in result_ids
        assert "ralph-task3" in result_ids
        assert "ralph-task2" not in result_ids

    @pytest.mark.asyncio
    async def test_runner_merge_worktrees_serial_merges_one_at_a_time(self):
        """Test _merge_worktrees_serial merges worktrees serially."""
        from ralph2.runner import Ralph2Runner

        completed = [
            ({"work_item_id": "ralph-task1"}, "/wt1", "ralph2/ralph-task1"),
            ({"work_item_id": "ralph-task2"}, "/wt2", "ralph2/ralph-task2"),
        ]

        merge_order = []

        def mock_merge(branch_name, cwd, target_branch="main"):
            merge_order.append(branch_name)
            return True, ""

        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner._milestone_branch = None  # No milestone branch, will merge to main

        with patch('ralph2.runner.merge_branch', side_effect=mock_merge):
            failed = await runner._merge_worktrees_serial(completed)

        assert len(failed) == 0
        assert len(merge_order) == 2
        # Verify merges happened in order
        assert merge_order[0] == "ralph2/ralph-task1"
        assert merge_order[1] == "ralph2/ralph-task2"

    @pytest.mark.asyncio
    async def test_runner_merge_worktrees_serial_aborts_on_conflict(self):
        """Test _merge_worktrees_serial aborts merge on conflict."""
        from ralph2.runner import Ralph2Runner

        completed = [
            ({"work_item_id": "ralph-task1"}, "/wt1", "ralph2/ralph-task1"),
        ]

        abort_called = [False]

        def mock_merge(branch_name, cwd, target_branch="main"):
            return False, "Merge conflict"

        def mock_abort(cwd):
            abort_called[0] = True
            return True

        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner._milestone_branch = None  # No milestone branch, will merge to main

        with patch('ralph2.runner.merge_branch', side_effect=mock_merge):
            with patch('ralph2.runner.abort_merge', side_effect=mock_abort):
                failed = await runner._merge_worktrees_serial(completed)

        assert len(failed) == 1
        assert failed[0][0] == "ralph-task1"
        assert abort_called[0] is True

    def test_runner_cleanup_all_worktrees_cleans_all(self):
        """Test _cleanup_all_worktrees cleans up all worktrees."""
        from ralph2.runner import Ralph2Runner

        worktree_info = [
            ({"work_item_id": "ralph-task1"}, "/wt1", "ralph2/ralph-task1"),
            ({"work_item_id": "ralph-task2"}, "/wt2", "ralph2/ralph-task2"),
            ({"work_item_id": "ralph-task3"}, "/wt3", "ralph2/ralph-task3"),
        ]

        cleaned = []

        def mock_remove(worktree_path, branch_name, cwd):
            cleaned.append((worktree_path, branch_name))
            return True

        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"

        with patch('ralph2.runner.remove_worktree', side_effect=mock_remove):
            runner._cleanup_all_worktrees(worktree_info)

        assert len(cleaned) == 3

    def test_runner_cleanup_all_worktrees_continues_on_failure(self):
        """Test _cleanup_all_worktrees continues even if some fail."""
        from ralph2.runner import Ralph2Runner

        worktree_info = [
            ({"work_item_id": "ralph-task1"}, "/wt1", "ralph2/ralph-task1"),
            ({"work_item_id": "ralph-task2"}, "/wt2", "ralph2/ralph-task2"),  # Will fail
            ({"work_item_id": "ralph-task3"}, "/wt3", "ralph2/ralph-task3"),
        ]

        cleanup_attempts = []

        def mock_remove(worktree_path, branch_name, cwd):
            cleanup_attempts.append(worktree_path)
            if worktree_path == "/wt2":
                return False  # Failure
            return True

        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"

        with patch('ralph2.runner.remove_worktree', side_effect=mock_remove):
            # Should not raise even though one cleanup fails
            runner._cleanup_all_worktrees(worktree_info)

        # All 3 should have been attempted
        assert len(cleanup_attempts) == 3


class TestRunnerParallelExecutors:
    """Test the refactored _run_parallel_executors method."""

    @pytest.mark.asyncio
    async def test_parallel_executors_lifecycle(self):
        """Test _run_parallel_executors follows correct lifecycle."""
        from ralph2.runner import Ralph2Runner, IterationContext
        from pathlib import Path

        lifecycle_events = []

        mock_result = {
            "status": "Completed",
            "summary": "Work done",
            "full_output": "",
            "messages": [],
            "result": MagicMock(status="Completed"),
        }

        async def mock_run_executor(**kwargs):
            lifecycle_events.append(("executor", kwargs.get("work_item_id")))
            return mock_result

        def mock_create_worktrees(work_items, run_id):
            lifecycle_events.append(("create_worktrees", len(work_items)))
            return [
                (wi, f"/wt/{wi['work_item_id']}", f"ralph2/{wi['work_item_id']}")
                for wi in work_items
            ]

        async def mock_merge_serial(completed):
            lifecycle_events.append(("merge", len(completed)))
            return []

        def mock_cleanup(worktree_info):
            lifecycle_events.append(("cleanup", len(worktree_info)))

        # Create runner with mocked project_context
        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner.project_context.outputs_dir = Path("/mock/outputs")
        runner.spec_content = "test spec"
        runner.db = MagicMock()
        runner.output_dir = runner.project_context.outputs_dir

        runner._create_worktrees = mock_create_worktrees
        runner._merge_worktrees_serial = mock_merge_serial
        runner._cleanup_all_worktrees = mock_cleanup
        runner._save_agent_messages = MagicMock(return_value="/mock/output.jsonl")

        iter_ctx = IterationContext(
            run_id="run-abc",
            iteration_id=1,
            iteration_number=1,
            intent="Test",
            memory="",
            iteration_plan={
                "work_items": [
                    {"work_item_id": "ralph-task1"},
                    {"work_item_id": "ralph-task2"},
                ]
            }
        )

        with patch('ralph2.runner.run_executor', side_effect=mock_run_executor):
            await runner._run_parallel_executors(iter_ctx)

        # Verify lifecycle order
        assert lifecycle_events[0][0] == "create_worktrees", "Should create worktrees first"
        assert lifecycle_events[1][0] == "executor"
        assert lifecycle_events[2][0] == "executor"
        assert lifecycle_events[3][0] == "merge", "Should merge after executors"
        assert lifecycle_events[4][0] == "cleanup", "Should cleanup last"

    @pytest.mark.asyncio
    async def test_parallel_executors_cleanup_on_exception(self):
        """Test cleanup happens even if executors fail."""
        from ralph2.runner import Ralph2Runner, IterationContext
        from pathlib import Path

        cleanup_called = [False]

        async def mock_run_executor(**kwargs):
            raise Exception("Executor crashed")

        def mock_create_worktrees(work_items, run_id):
            return [
                (wi, f"/wt/{wi['work_item_id']}", f"ralph2/{wi['work_item_id']}")
                for wi in work_items
            ]

        def mock_cleanup(worktree_info):
            cleanup_called[0] = True

        # Create runner with mocked project_context
        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner.project_context.outputs_dir = Path("/mock/outputs")
        runner.spec_content = "test spec"
        runner.db = MagicMock()
        runner.output_dir = runner.project_context.outputs_dir

        runner._create_worktrees = mock_create_worktrees
        runner._merge_worktrees_serial = AsyncMock(return_value=[])
        runner._cleanup_all_worktrees = mock_cleanup
        runner._save_agent_messages = MagicMock(return_value="/mock/output.jsonl")

        iter_ctx = IterationContext(
            run_id="run-abc",
            iteration_id=1,
            iteration_number=1,
            intent="Test",
            memory="",
            iteration_plan={
                "work_items": [
                    {"work_item_id": "ralph-task1"},
                ]
            }
        )

        with patch('ralph2.runner.run_executor', side_effect=mock_run_executor):
            # Should not raise - exceptions are caught
            await runner._run_parallel_executors(iter_ctx)

        # Cleanup should have been called even though executor failed
        assert cleanup_called[0] is True, "Cleanup should be called even on executor failure"

    @pytest.mark.asyncio
    async def test_parallel_executors_passes_worktree_path(self):
        """Test executors receive worktree_path parameter."""
        from ralph2.runner import Ralph2Runner, IterationContext
        from pathlib import Path

        executor_calls = []

        mock_result = {
            "status": "Completed",
            "summary": "Work done",
            "full_output": "",
            "messages": [],
            "result": MagicMock(status="Completed"),
        }

        async def mock_run_executor(**kwargs):
            executor_calls.append(kwargs)
            return mock_result

        def mock_create_worktrees(work_items, run_id):
            return [
                (wi, f"/wt/{wi['work_item_id']}", f"ralph2/{wi['work_item_id']}")
                for wi in work_items
            ]

        # Create runner with mocked project_context
        runner = Ralph2Runner.__new__(Ralph2Runner)
        runner.project_context = MagicMock()
        runner.project_context.project_root = "/mock/repo"
        runner.project_context.outputs_dir = Path("/mock/outputs")
        runner.spec_content = "test spec"
        runner.db = MagicMock()
        runner.output_dir = runner.project_context.outputs_dir

        runner._create_worktrees = mock_create_worktrees
        runner._merge_worktrees_serial = AsyncMock(return_value=[])
        runner._cleanup_all_worktrees = MagicMock()
        runner._save_agent_messages = MagicMock(return_value="/mock/output.jsonl")

        iter_ctx = IterationContext(
            run_id="run-abc",
            iteration_id=1,
            iteration_number=1,
            intent="Test",
            memory="",
            iteration_plan={
                "work_items": [
                    {"work_item_id": "ralph-task1"},
                ]
            }
        )

        with patch('ralph2.runner.run_executor', side_effect=mock_run_executor):
            await runner._run_parallel_executors(iter_ctx)

        # Verify worktree_path was passed
        assert len(executor_calls) == 1
        assert "worktree_path" in executor_calls[0]
        assert executor_calls[0]["worktree_path"] == "/wt/ralph-task1"
