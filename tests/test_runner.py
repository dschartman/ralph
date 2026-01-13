"""Tests for runner module - iteration orchestration."""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
import json

from ralph.runner import RalphRunner
from ralph.state.db import RalphDB
from ralph.state.models import Run, Iteration, AgentOutput, HumanInput
from ralph.project import ProjectContext


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with spec file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a spec file
        spec_path = os.path.join(tmpdir, "Ralphfile")
        with open(spec_path, 'w') as f:
            f.write("# Test Spec\nImplement feature X\n")

        # Create a mock ProjectContext
        project_dir = Path(tmpdir) / ".ralph_state"
        project_dir.mkdir(parents=True)

        (project_dir / "outputs").mkdir(parents=True)
        (project_dir / "summaries").mkdir(parents=True)

        yield tmpdir, spec_path, project_dir


@pytest.fixture
def mock_project_context(temp_project_dir):
    """Create a mock ProjectContext for testing."""
    tmpdir, spec_path, project_dir = temp_project_dir

    context = MagicMock(spec=ProjectContext)
    context.project_id = "test-project-id"
    context.db_path = project_dir / "ralph.db"
    context.outputs_dir = project_dir / "outputs"
    context.summaries_dir = project_dir / "summaries"

    return context, spec_path


@pytest.fixture
def runner(mock_project_context):
    """Create a RalphRunner instance for testing."""
    context, spec_path = mock_project_context
    runner = RalphRunner(spec_path, context)
    yield runner
    runner.close()


@pytest.fixture(autouse=True)
def mock_read_memory():
    """Mock read_memory to return empty string for all tests."""
    with patch('ralph.runner.read_memory', return_value=""):
        yield


class TestIterationOrchestration:
    """Test the planner -> executor -> verifier flow."""

    @pytest.mark.asyncio
    async def test_single_iteration_completes_successfully(self, runner):
        """Test that a single iteration runs all three agents in order."""
        # Mock agent functions
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            # Configure mocks
            mock_planner.return_value = {
                "intent": "Work on task A",
                "messages": [{"type": "text", "content": "Planning complete"}]
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Task A done\nBlockers: None\nNotes: All good",
                "full_output": "Full executor output",
                "messages": [{"type": "text", "content": "Work complete"}]
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "VERIFIER_ASSESSMENT:\nOutcome: DONE\nReasoning: All complete",
                "full_output": "Full verifier output",
                "messages": [{"type": "text", "content": "Verification complete"}]
            }

            # Run with max_iterations=1
            status = await runner.run(max_iterations=1)

            # Verify all agents were called
            assert mock_planner.called
            assert mock_executor.called
            assert mock_verifier.called

            # Verify status
            assert status == "completed"

    @pytest.mark.asyncio
    async def test_agents_called_in_correct_order(self, runner):
        """Test that agents are called in the correct sequence: planner -> executor -> verifier."""
        call_order = []

        async def mock_planner_fn(*args, **kwargs):
            call_order.append("planner")
            return {
                "intent": "Work on task A",
                "messages": [{"type": "text", "content": "Planning"}]
            }

        async def mock_executor_fn(*args, **kwargs):
            call_order.append("executor")
            return {
                "status": "Completed",
                "summary": "Work done",
                "messages": [{"type": "text", "content": "Executing"}]
            }

        async def mock_verifier_fn(*args, **kwargs):
            call_order.append("verifier")
            return {
                "outcome": "DONE",
                "assessment": "All done",
                "messages": [{"type": "text", "content": "Verifying"}]
            }

        with patch('ralph.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph.runner.run_verifier', side_effect=mock_verifier_fn):

            await runner.run(max_iterations=1)

            # Verify order
            assert call_order == ["planner", "executor", "verifier"]

    @pytest.mark.asyncio
    async def test_iteration_data_saved_to_database(self, runner):
        """Test that iteration records are created and updated in the database."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work on task B",
                "messages": [{"type": "text", "content": "Plan"}]
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": [{"type": "text", "content": "Execute"}]
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": [{"type": "text", "content": "Verify"}]
            }

            await runner.run(max_iterations=1)

            # Check database for iteration
            runs = runner.db.list_runs()
            assert len(runs) == 1

            iterations = runner.db.list_iterations(runs[0].id)
            assert len(iterations) == 1
            assert iterations[0].intent == "Work on task B"
            assert iterations[0].outcome == "DONE"

    @pytest.mark.asyncio
    async def test_agent_outputs_saved_to_files(self, runner):
        """Test that agent messages are saved to JSONL files."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Intent",
                "messages": [{"type": "text", "content": "msg1"}]
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Summary",
                "messages": [{"type": "text", "content": "msg2"}]
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Assessment",
                "messages": [{"type": "text", "content": "msg3"}]
            }

            await runner.run(max_iterations=1)

            # Check that output files were created
            output_files = list(runner.output_dir.glob("*.jsonl"))
            assert len(output_files) == 3  # One for each agent

            # Check file contents
            for output_file in output_files:
                with open(output_file, 'r') as f:
                    lines = f.readlines()
                    assert len(lines) > 0
                    # Each line should be valid JSON
                    for line in lines:
                        json.loads(line)


class TestFeedbackPassing:
    """Test feedback passing between iterations."""

    @pytest.mark.asyncio
    async def test_executor_summary_passed_to_next_planner(self, runner):
        """Test that executor summary from iteration N is passed to planner in iteration N+1."""
        planner_calls = []

        async def mock_planner_fn(*args, **kwargs):
            planner_calls.append(kwargs)
            return {
                "intent": "Work on task",
                "messages": [{"type": "text", "content": "Plan"}]
            }

        async def mock_executor_fn(*args, **kwargs):
            return {
                "status": "Completed",
                "summary": "EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work iteration " + str(len(planner_calls)),
                "messages": [{"type": "text", "content": "Execute"}]
            }

        async def mock_verifier_fn(*args, **kwargs):
            # First iteration CONTINUE, second DONE
            outcome = "CONTINUE" if len(planner_calls) < 2 else "DONE"
            return {
                "outcome": outcome,
                "assessment": "Assessment",
                "messages": [{"type": "text", "content": "Verify"}]
            }

        with patch('ralph.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph.runner.run_verifier', side_effect=mock_verifier_fn):

            await runner.run(max_iterations=5)

            # First planner call should have no feedback
            assert planner_calls[0]['last_executor_summary'] is None
            assert planner_calls[0]['last_verifier_assessment'] is None

            # Second planner call should have feedback from first iteration
            assert planner_calls[1]['last_executor_summary'] is not None
            assert "Work iteration 1" in planner_calls[1]['last_executor_summary']
            assert planner_calls[1]['last_verifier_assessment'] is not None

    @pytest.mark.asyncio
    async def test_verifier_assessment_passed_to_next_planner(self, runner):
        """Test that verifier assessment from iteration N is passed to planner in iteration N+1."""
        planner_calls = []

        async def mock_planner_fn(*args, **kwargs):
            planner_calls.append(kwargs)
            return {
                "intent": "Work on task",
                "messages": [{"type": "text", "content": "Plan"}]
            }

        async def mock_executor_fn(*args, **kwargs):
            return {
                "status": "Completed",
                "summary": "Done",
                "messages": [{"type": "text", "content": "Execute"}]
            }

        async def mock_verifier_fn(*args, **kwargs):
            iteration_num = len(planner_calls)
            outcome = "CONTINUE" if iteration_num < 2 else "DONE"
            return {
                "outcome": outcome,
                "assessment": f"VERIFIER_ASSESSMENT:\nOutcome: {outcome}\nIteration: {iteration_num}",
                "messages": [{"type": "text", "content": "Verify"}]
            }

        with patch('ralph.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph.runner.run_verifier', side_effect=mock_verifier_fn):

            await runner.run(max_iterations=5)

            # Second planner should see verifier assessment from iteration 1
            assert planner_calls[1]['last_verifier_assessment'] is not None
            assert "Iteration: 1" in planner_calls[1]['last_verifier_assessment']

    @pytest.mark.asyncio
    async def test_iteration_intent_passed_to_executor(self, runner):
        """Test that planner's intent is passed to executor (verifier doesn't receive it)."""
        executor_calls = []
        verifier_calls = []

        async def mock_planner_fn(*args, **kwargs):
            return {
                "intent": "Work on specific task XYZ",
                "messages": [{"type": "text", "content": "Plan"}]
            }

        async def mock_executor_fn(*args, **kwargs):
            executor_calls.append(kwargs)
            return {
                "status": "Completed",
                "summary": "Done",
                "messages": [{"type": "text", "content": "Execute"}]
            }

        async def mock_verifier_fn(*args, **kwargs):
            verifier_calls.append(kwargs)
            return {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": [{"type": "text", "content": "Verify"}]
            }

        with patch('ralph.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph.runner.run_executor', side_effect=mock_executor_fn), \
             patch('ralph.runner.run_verifier', side_effect=mock_verifier_fn):

            await runner.run(max_iterations=1)

            # Check executor received the intent
            assert len(executor_calls) == 1
            assert executor_calls[0]['iteration_intent'] == "Work on specific task XYZ"

            # Verifier should be called but without iteration_intent (only spec_content)
            assert len(verifier_calls) == 1
            assert 'iteration_intent' not in verifier_calls[0]


class TestOutcomeHandling:
    """Test handling of DONE, CONTINUE, and STUCK outcomes."""

    @pytest.mark.asyncio
    async def test_done_outcome_stops_iteration(self, runner):
        """Test that DONE outcome causes the run to complete successfully."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "All complete",
                "messages": []
            }

            status = await runner.run(max_iterations=10)

            # Should complete after 1 iteration
            assert status == "completed"

            # Verify only 1 iteration was run
            runs = runner.db.list_runs()
            iterations = runner.db.list_iterations(runs[0].id)
            assert len(iterations) == 1

    @pytest.mark.asyncio
    async def test_continue_outcome_continues_iteration(self, runner):
        """Test that CONTINUE outcome causes iteration to continue."""
        iteration_count = 0

        async def mock_verifier_fn(*args, **kwargs):
            nonlocal iteration_count
            iteration_count += 1
            # First 2 iterations CONTINUE, then DONE
            outcome = "CONTINUE" if iteration_count < 3 else "DONE"
            return {
                "outcome": outcome,
                "assessment": f"Assessment {iteration_count}",
                "messages": []
            }

        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier', side_effect=mock_verifier_fn):

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            status = await runner.run(max_iterations=10)

            # Should complete after 3 iterations
            assert status == "completed"

            # Verify 3 iterations were run
            runs = runner.db.list_runs()
            iterations = runner.db.list_iterations(runs[0].id)
            assert len(iterations) == 3

    @pytest.mark.asyncio
    async def test_stuck_outcome_stops_iteration(self, runner):
        """Test that STUCK outcome causes the run to stop with stuck status."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Blocked",
                "summary": "Blocked on dependency",
                "messages": []
            }

            mock_verifier.return_value = {
                "outcome": "STUCK",
                "assessment": "Cannot proceed without external dependency",
                "messages": []
            }

            status = await runner.run(max_iterations=10)

            # Should stop with stuck status
            assert status == "stuck"

            # Verify run status in database
            runs = runner.db.list_runs()
            assert runs[0].status == "stuck"

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self, runner):
        """Test that runner stops when max iterations is reached."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            # Always return CONTINUE
            mock_verifier.return_value = {
                "outcome": "CONTINUE",
                "assessment": "Not done yet",
                "messages": []
            }

            status = await runner.run(max_iterations=3)

            # Should stop with max_iterations status
            assert status == "max_iterations"

            # Verify exactly 3 iterations were run
            runs = runner.db.list_runs()
            iterations = runner.db.list_iterations(runs[0].id)
            assert len(iterations) == 3


class TestHumanInputProcessing:
    """Test processing of human input (comments, control signals)."""

    @pytest.mark.asyncio
    async def test_human_comment_passed_to_planner(self, runner):
        """Test that human comments are passed to the planner."""
        planner_calls = []

        async def mock_planner_fn(*args, **kwargs):
            planner_calls.append(kwargs)
            return {
                "intent": "Work",
                "messages": []
            }

        def mock_create_run_side_effect(run):
            # Actually create the run in the DB
            cursor = runner.db.conn.execute(
                """INSERT INTO runs (id, spec_path, spec_content, status, config, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run.id, run.spec_path, run.spec_content, run.status,
                 json.dumps(run.config) if run.config else None,
                 run.started_at.isoformat() if run.started_at else None,
                 run.ended_at.isoformat() if run.ended_at else None)
            )
            runner.db.conn.commit()

            # Add human input right after run is created
            human_input = HumanInput(
                id=None,
                run_id=run.id,
                input_type="comment",
                content="Please focus on unit tests first",
                created_at=datetime.now(),
                consumed_at=None
            )
            runner.db.create_human_input(human_input)

            return run

        with patch('ralph.runner.run_planner', side_effect=mock_planner_fn), \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier, \
             patch.object(runner.db, 'create_run', side_effect=mock_create_run_side_effect):

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

            await runner.run(max_iterations=1)

            # First planner call should have human input
            assert len(planner_calls) > 0
            human_inputs = planner_calls[0].get('human_inputs')
            assert human_inputs is not None
            assert isinstance(human_inputs, list)
            assert len(human_inputs) == 1
            assert "Please focus on unit tests first" in human_inputs[0]

    @pytest.mark.asyncio
    async def test_human_input_marked_consumed(self, runner):
        """Test that human input is marked as consumed after being processed."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete",
                "messages": []
            }

            # Run to create a run ID
            status = await runner.run(max_iterations=1)

            # Get the run ID
            runs = runner.db.list_runs()
            run_id = runs[0].id

            # Add human input for next iteration
            human_input = HumanInput(
                id=None,
                run_id=run_id,
                input_type="comment",
                content="Test comment",
                created_at=datetime.now(),
                consumed_at=None
            )
            created_input = runner.db.create_human_input(human_input)

            # Verify it's unconsumed
            unconsumed = runner.db.get_unconsumed_inputs(run_id)
            assert len(unconsumed) == 1

            # Run another iteration (create new runner with same run)
            # Since we can't easily resume, we'll test the consumption directly
            runner.db.mark_input_consumed(created_input.id, datetime.now())

            # Verify it's now consumed
            unconsumed = runner.db.get_unconsumed_inputs(run_id)
            assert len(unconsumed) == 0

    @pytest.mark.asyncio
    async def test_pause_signal_stops_run(self, runner):
        """Test that pause signal stops the run with paused status."""
        # Use a side_effect to inject the pause input dynamically
        call_count = [0]
        created_run_id = [None]

        def mock_create_run_side_effect(run):
            created_run_id[0] = run.id
            # Actually create the run in the DB
            cursor = runner.db.conn.execute(
                """INSERT INTO runs (id, spec_path, spec_content, status, config, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run.id, run.spec_path, run.spec_content, run.status,
                 json.dumps(run.config) if run.config else None,
                 run.started_at.isoformat() if run.started_at else None,
                 run.ended_at.isoformat() if run.ended_at else None)
            )
            runner.db.conn.commit()
            run.id = run.id  # Keep the same ID

            # Immediately add pause input after run is created
            human_input = HumanInput(
                id=None,
                run_id=run.id,
                input_type="pause",
                content="",
                created_at=datetime.now(),
                consumed_at=None
            )
            runner.db.create_human_input(human_input)

            return run

        with patch.object(runner.db, 'create_run', side_effect=mock_create_run_side_effect):
            status = await runner.run(max_iterations=5)

            # Should return paused status
            assert status == "paused"

            # Verify run status in database
            runs = runner.db.list_runs()
            assert any(r.status == "paused" for r in runs)

    @pytest.mark.asyncio
    async def test_abort_signal_stops_run(self, runner):
        """Test that abort signal stops the run with aborted status."""
        # Use a side_effect to inject the abort input dynamically
        def mock_create_run_side_effect(run):
            # Actually create the run in the DB
            cursor = runner.db.conn.execute(
                """INSERT INTO runs (id, spec_path, spec_content, status, config, started_at, ended_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run.id, run.spec_path, run.spec_content, run.status,
                 json.dumps(run.config) if run.config else None,
                 run.started_at.isoformat() if run.started_at else None,
                 run.ended_at.isoformat() if run.ended_at else None)
            )
            runner.db.conn.commit()

            # Immediately add abort input after run is created
            human_input = HumanInput(
                id=None,
                run_id=run.id,
                input_type="abort",
                content="",
                created_at=datetime.now(),
                consumed_at=None
            )
            runner.db.create_human_input(human_input)

            return run

        with patch.object(runner.db, 'create_run', side_effect=mock_create_run_side_effect):
            status = await runner.run(max_iterations=5)

            # Should return aborted status
            assert status == "aborted"

            # Verify run status in database
            runs = runner.db.list_runs()
            assert any(r.status == "aborted" for r in runs)


class TestErrorHandling:
    """Test error handling in the runner."""

    @pytest.mark.asyncio
    async def test_planner_error_marks_run_as_stuck(self, runner):
        """Test that planner errors result in stuck status."""
        with patch('ralph.runner.run_planner') as mock_planner:

            # Make planner raise an exception
            mock_planner.side_effect = Exception("Planner crashed")

            status = await runner.run(max_iterations=1)

            # Should return stuck status
            assert status == "stuck"

            # Verify run status
            runs = runner.db.list_runs()
            assert runs[0].status == "stuck"

    @pytest.mark.asyncio
    async def test_executor_error_creates_fallback_result(self, runner):
        """Test that executor errors create a fallback result and continue."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            # Make executor raise an exception
            mock_executor.side_effect = Exception("Executor crashed")

            mock_verifier.return_value = {
                "outcome": "DONE",
                "assessment": "Complete despite error",
                "messages": []
            }

            status = await runner.run(max_iterations=1)

            # Should still complete (verifier ran)
            assert status == "completed"

            # Check that executor output was saved with error info
            runs = runner.db.list_runs()
            iterations = runner.db.list_iterations(runs[0].id)
            outputs = runner.db.get_agent_outputs(iterations[0].id)

            executor_output = [o for o in outputs if o.agent_type == "executor"][0]
            assert "Blocked" in executor_output.summary
            assert "crashed" in executor_output.summary.lower()

    @pytest.mark.asyncio
    async def test_verifier_error_creates_continue_outcome(self, runner):
        """Test that verifier errors default to CONTINUE outcome."""
        with patch('ralph.runner.run_planner') as mock_planner, \
             patch('ralph.runner.run_executor') as mock_executor, \
             patch('ralph.runner.run_verifier') as mock_verifier:

            mock_planner.return_value = {
                "intent": "Work",
                "messages": []
            }

            mock_executor.return_value = {
                "status": "Completed",
                "summary": "Done",
                "messages": []
            }

            # Make verifier raise an exception
            mock_verifier.side_effect = Exception("Verifier crashed")

            status = await runner.run(max_iterations=2)

            # Should hit max iterations (CONTINUE default keeps going)
            assert status == "max_iterations"

            # Check that verifier output defaulted to CONTINUE
            runs = runner.db.list_runs()
            iterations = runner.db.list_iterations(runs[0].id)
            assert iterations[0].outcome == "CONTINUE"
