"""Tests for Ralph2 parallel executor execution."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import asyncio

from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext


@pytest.fixture
def ralph2_runner():
    """Create a Ralph2Runner instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a spec file
        spec_path = os.path.join(tmpdir, "Ralph2file")
        with open(spec_path, 'w') as f:
            f.write("# Test Spec\nImplement feature X\n")

        # Create ProjectContext for ralph2
        project_dir = Path(tmpdir) / ".ralph2_state"
        project_dir.mkdir(parents=True)
        (project_dir / "outputs").mkdir(parents=True)
        (project_dir / "summaries").mkdir(parents=True)

        context = MagicMock(spec=ProjectContext)
        context.project_id = "test-project-id"
        context.db_path = project_dir / "ralph2.db"
        context.outputs_dir = project_dir / "outputs"
        context.summaries_dir = project_dir / "summaries"

        runner = Ralph2Runner(spec_path, context)

        try:
            yield runner
        finally:
            runner.close()


class TestParallelExecutorExecution:
    """Test parallel execution of multiple executors in Ralph2."""

    @pytest.mark.asyncio
    async def test_multiple_executors_run_in_parallel(self, ralph2_runner):
        """Test that multiple executors run concurrently when ITERATION_PLAN specifies them."""
        executor_calls = []

        async def mock_planner_fn(*args, **kwargs):
            return {
                "intent": "Work on tasks in parallel",
                "decision": {
                    "decision": "CONTINUE",
                    "reason": "Work remaining",
                    "blocker": None
                },
                "iteration_plan": {
                    "executor_count": 2,
                    "work_items": [
                        {"work_item_id": "ralph-task1", "description": "Task 1", "executor_number": 1},
                        {"work_item_id": "ralph-task2", "description": "Task 2", "executor_number": 2}
                    ]
                },
                "messages": []
            }

        async def mock_executor_fn(*args, **kwargs):
            # Track when this executor was called
            executor_calls.append({
                "time": asyncio.get_event_loop().time(),
                "work_item_id": kwargs.get("work_item_id")
            })
            # Simulate some work
            await asyncio.sleep(0.1)
            return {
                "status": "Completed",
                "summary": f"Completed {kwargs.get('work_item_id')}",
                "messages": []
            }

        with patch('ralph2.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph2.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph2.runner.run_verifier') as mock_verifier, \
             patch('ralph2.runner.CodeReviewerSpecialist') as mock_specialist_class, \
             patch('ralph2.runner.run_specialist') as mock_run_specialist, \
             patch('ralph2.runner.read_memory', return_value=""):

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

            mock_run_specialist.return_value = {
                "specialist_name": "code_reviewer",
                "feedback": [],
                "full_output": "",
                "messages": []
            }

            status = await ralph2_runner.run(max_iterations=1)

            # Verify both executors were called
            assert len(executor_calls) == 2
            assert executor_calls[0]["work_item_id"] == "ralph-task1"
            assert executor_calls[1]["work_item_id"] == "ralph-task2"

            # Verify they ran in parallel (start times should be close)
            time_diff = abs(executor_calls[0]["time"] - executor_calls[1]["time"])
            assert time_diff < 0.05  # Started within 50ms of each other

    @pytest.mark.asyncio
    async def test_executor_receives_work_item_id(self, ralph2_runner):
        """Test that each executor receives its assigned work item ID."""
        executor_calls = []

        async def mock_planner_fn(*args, **kwargs):
            return {
                "intent": "Work on specific tasks",
                "decision": {
                    "decision": "CONTINUE",
                    "reason": "Work remaining",
                    "blocker": None
                },
                "iteration_plan": {
                    "executor_count": 2,
                    "work_items": [
                        {"work_item_id": "ralph-abc123", "description": "Fix bug", "executor_number": 1},
                        {"work_item_id": "ralph-def456", "description": "Add feature", "executor_number": 2}
                    ]
                },
                "messages": []
            }

        async def mock_executor_fn(*args, **kwargs):
            executor_calls.append(kwargs)
            return {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

        with patch('ralph2.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph2.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph2.runner.run_verifier') as mock_verifier, \
             patch('ralph2.runner.CodeReviewerSpecialist') as mock_specialist_class, \
             patch('ralph2.runner.run_specialist') as mock_run_specialist, \
             patch('ralph2.runner.read_memory', return_value=""):

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

            mock_run_specialist.return_value = {
                "specialist_name": "code_reviewer",
                "feedback": [],
                "full_output": "",
                "messages": []
            }

            await ralph2_runner.run(max_iterations=1)

            # Verify each executor received correct work item ID
            assert len(executor_calls) == 2
            work_item_ids = [call.get("work_item_id") for call in executor_calls]
            assert "ralph-abc123" in work_item_ids
            assert "ralph-def456" in work_item_ids

    @pytest.mark.asyncio
    async def test_fallback_to_single_executor_when_no_plan(self, ralph2_runner):
        """Test that runner falls back to single executor when ITERATION_PLAN is None."""
        async def mock_planner_fn(*args, **kwargs):
            return {
                "intent": "Work on task",
                "decision": {
                    "decision": "CONTINUE",
                    "reason": "Work remaining",
                    "blocker": None
                },
                "iteration_plan": None,  # No plan provided
                "messages": []
            }

        executor_call_count = [0]

        async def mock_executor_fn(*args, **kwargs):
            executor_call_count[0] += 1
            return {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

        with patch('ralph2.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph2.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph2.runner.run_verifier') as mock_verifier, \
             patch('ralph2.runner.CodeReviewerSpecialist') as mock_specialist_class, \
             patch('ralph2.runner.run_specialist') as mock_run_specialist, \
             patch('ralph2.runner.read_memory', return_value=""):

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

            mock_run_specialist.return_value = {
                "specialist_name": "code_reviewer",
                "feedback": [],
                "full_output": "",
                "messages": []
            }

            status = await ralph2_runner.run(max_iterations=1)

            # Should fall back to single executor
            assert executor_call_count[0] == 1

    @pytest.mark.asyncio
    async def test_all_executors_complete_before_verifier_runs(self, ralph2_runner):
        """Test that verifier only runs after all executors complete."""
        execution_order = []

        async def mock_planner_fn(*args, **kwargs):
            return {
                "intent": "Work in parallel",
                "decision": {
                    "decision": "CONTINUE",
                    "reason": "Work remaining",
                    "blocker": None
                },
                "iteration_plan": {
                    "executor_count": 3,
                    "work_items": [
                        {"work_item_id": "ralph-task1", "description": "Task 1", "executor_number": 1},
                        {"work_item_id": "ralph-task2", "description": "Task 2", "executor_number": 2},
                        {"work_item_id": "ralph-task3", "description": "Task 3", "executor_number": 3}
                    ]
                },
                "messages": []
            }

        async def mock_executor_fn(*args, **kwargs):
            work_item = kwargs.get("work_item_id")
            execution_order.append(f"executor-{work_item}-start")
            await asyncio.sleep(0.05)
            execution_order.append(f"executor-{work_item}-end")
            return {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

        async def mock_verifier_fn(*args, **kwargs):
            execution_order.append("verifier-start")
            return {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

        with patch('ralph2.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph2.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph2.runner.run_verifier', side_effect=mock_verifier_fn), \
             patch('ralph2.runner.read_memory', return_value=""):

            await ralph2_runner.run(max_iterations=1)

            # Verify verifier started after all executors ended
            verifier_index = execution_order.index("verifier-start")

            # All executor-end events should come before verifier-start
            executor_end_indices = [i for i, e in enumerate(execution_order) if "executor" in e and "end" in e]
            assert all(idx < verifier_index for idx in executor_end_indices)
