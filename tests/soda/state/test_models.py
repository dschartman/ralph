"""Tests for Soda state models."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from soda.state.models import (
    Run,
    RunStatus,
    Iteration,
    IterationOutcome,
    AgentOutput,
    AgentType,
    HumanInput,
    InputType,
)


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_status_values(self):
        """RunStatus enum has expected values."""
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.DONE.value == "done"
        assert RunStatus.STUCK.value == "stuck"
        assert RunStatus.PAUSED.value == "paused"
        assert RunStatus.ABORTED.value == "aborted"


class TestRun:
    """Tests for Run dataclass."""

    def test_create_run(self):
        """Can create a Run with required fields."""
        now = datetime.now()
        run = Run(
            id="run-123",
            spec_path="spec.md",
            spec_content="# Spec content",
            status=RunStatus.RUNNING,
            config={"key": "value"},
            started_at=now,
        )

        assert run.id == "run-123"
        assert run.spec_path == "spec.md"
        assert run.spec_content == "# Spec content"
        assert run.status == RunStatus.RUNNING
        assert run.config == {"key": "value"}
        assert run.started_at == now
        assert run.ended_at is None
        assert run.root_work_item_id is None
        assert run.milestone_branch is None

    def test_run_with_optional_fields(self):
        """Can create a Run with optional fields."""
        now = datetime.now()
        ended = datetime.now()
        run = Run(
            id="run-456",
            spec_path="spec2.md",
            spec_content="# Content",
            status=RunStatus.DONE,
            config={},
            started_at=now,
            ended_at=ended,
            root_work_item_id="item-789",
            milestone_branch="feature/test",
        )

        assert run.ended_at == ended
        assert run.root_work_item_id == "item-789"
        assert run.milestone_branch == "feature/test"

    def test_run_to_dict(self):
        """Run.to_dict() returns proper dictionary representation."""
        now = datetime(2026, 1, 20, 12, 0, 0)
        ended = datetime(2026, 1, 20, 13, 0, 0)
        run = Run(
            id="run-abc",
            spec_path="path/to/spec.md",
            spec_content="content",
            status=RunStatus.DONE,
            config={"nested": {"value": 1}},
            started_at=now,
            ended_at=ended,
            root_work_item_id="work-item",
            milestone_branch="feature/branch",
        )

        result = run.to_dict()

        assert result["id"] == "run-abc"
        assert result["spec_path"] == "path/to/spec.md"
        assert result["spec_content"] == "content"
        assert result["status"] == "done"
        assert result["config"] == json.dumps({"nested": {"value": 1}})
        assert result["started_at"] == "2026-01-20T12:00:00"
        assert result["ended_at"] == "2026-01-20T13:00:00"
        assert result["root_work_item_id"] == "work-item"
        assert result["milestone_branch"] == "feature/branch"

    def test_run_to_dict_with_none_values(self):
        """Run.to_dict() handles None values correctly."""
        now = datetime(2026, 1, 20, 12, 0, 0)
        run = Run(
            id="run-def",
            spec_path="spec.md",
            spec_content="content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )

        result = run.to_dict()

        assert result["ended_at"] is None
        assert result["root_work_item_id"] is None
        assert result["milestone_branch"] is None


class TestIterationOutcome:
    """Tests for IterationOutcome enum."""

    def test_outcome_values(self):
        """IterationOutcome enum has expected values."""
        assert IterationOutcome.CONTINUE.value == "continue"
        assert IterationOutcome.DONE.value == "done"
        assert IterationOutcome.STUCK.value == "stuck"


class TestIteration:
    """Tests for Iteration dataclass."""

    def test_create_iteration(self):
        """Can create an Iteration with required fields."""
        now = datetime.now()
        iteration = Iteration(
            id=None,
            run_id="run-123",
            number=1,
            intent="Implement feature X",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )

        assert iteration.id is None
        assert iteration.run_id == "run-123"
        assert iteration.number == 1
        assert iteration.intent == "Implement feature X"
        assert iteration.outcome == IterationOutcome.CONTINUE
        assert iteration.started_at == now
        assert iteration.ended_at is None

    def test_iteration_with_id_and_ended_at(self):
        """Can create an Iteration with optional fields."""
        now = datetime.now()
        ended = datetime.now()
        iteration = Iteration(
            id=42,
            run_id="run-456",
            number=5,
            intent="Fix bug Y",
            outcome=IterationOutcome.DONE,
            started_at=now,
            ended_at=ended,
        )

        assert iteration.id == 42
        assert iteration.ended_at == ended

    def test_iteration_to_dict(self):
        """Iteration.to_dict() returns proper dictionary representation."""
        now = datetime(2026, 1, 20, 14, 30, 0)
        ended = datetime(2026, 1, 20, 15, 0, 0)
        iteration = Iteration(
            id=10,
            run_id="run-xyz",
            number=3,
            intent="Refactor module Z",
            outcome=IterationOutcome.STUCK,
            started_at=now,
            ended_at=ended,
        )

        result = iteration.to_dict()

        assert result["id"] == 10
        assert result["run_id"] == "run-xyz"
        assert result["number"] == 3
        assert result["intent"] == "Refactor module Z"
        assert result["outcome"] == "stuck"
        assert result["started_at"] == "2026-01-20T14:30:00"
        assert result["ended_at"] == "2026-01-20T15:00:00"

    def test_iteration_to_dict_with_none_values(self):
        """Iteration.to_dict() handles None values correctly."""
        now = datetime(2026, 1, 20, 14, 30, 0)
        iteration = Iteration(
            id=None,
            run_id="run-abc",
            number=1,
            intent="Initial work",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )

        result = iteration.to_dict()

        assert result["id"] is None
        assert result["ended_at"] is None


class TestAgentType:
    """Tests for AgentType enum."""

    def test_agent_type_values(self):
        """AgentType enum has expected values."""
        assert AgentType.PLANNER.value == "planner"
        assert AgentType.EXECUTOR.value == "executor"
        assert AgentType.VERIFIER.value == "verifier"


class TestAgentOutput:
    """Tests for AgentOutput dataclass."""

    def test_create_agent_output(self):
        """Can create an AgentOutput with required fields."""
        output = AgentOutput(
            id=None,
            iteration_id=5,
            agent_type=AgentType.PLANNER,
            raw_output_path="outputs/planner_123.jsonl",
            summary="Planned 3 work items",
        )

        assert output.id is None
        assert output.iteration_id == 5
        assert output.agent_type == AgentType.PLANNER
        assert output.raw_output_path == "outputs/planner_123.jsonl"
        assert output.summary == "Planned 3 work items"

    def test_agent_output_with_id(self):
        """Can create an AgentOutput with id."""
        output = AgentOutput(
            id=99,
            iteration_id=10,
            agent_type=AgentType.EXECUTOR,
            raw_output_path="outputs/executor_456.jsonl",
            summary="Executed task successfully",
        )

        assert output.id == 99

    def test_agent_output_to_dict(self):
        """AgentOutput.to_dict() returns proper dictionary representation."""
        output = AgentOutput(
            id=25,
            iteration_id=7,
            agent_type=AgentType.VERIFIER,
            raw_output_path="outputs/verifier_789.jsonl",
            summary="Verification passed",
        )

        result = output.to_dict()

        assert result["id"] == 25
        assert result["iteration_id"] == 7
        assert result["agent_type"] == "verifier"
        assert result["raw_output_path"] == "outputs/verifier_789.jsonl"
        assert result["summary"] == "Verification passed"


class TestInputType:
    """Tests for InputType enum."""

    def test_input_type_values(self):
        """InputType enum has expected values."""
        assert InputType.COMMENT.value == "comment"
        assert InputType.PAUSE.value == "pause"
        assert InputType.RESUME.value == "resume"
        assert InputType.ABORT.value == "abort"


class TestHumanInput:
    """Tests for HumanInput dataclass."""

    def test_create_human_input(self):
        """Can create a HumanInput with required fields."""
        now = datetime.now()
        human_input = HumanInput(
            id=None,
            run_id="run-123",
            input_type=InputType.COMMENT,
            content="Focus on tests",
            created_at=now,
        )

        assert human_input.id is None
        assert human_input.run_id == "run-123"
        assert human_input.input_type == InputType.COMMENT
        assert human_input.content == "Focus on tests"
        assert human_input.created_at == now
        assert human_input.consumed_at is None

    def test_human_input_with_consumed_at(self):
        """Can create a HumanInput with consumed_at."""
        now = datetime.now()
        consumed = datetime.now()
        human_input = HumanInput(
            id=15,
            run_id="run-456",
            input_type=InputType.PAUSE,
            content="",
            created_at=now,
            consumed_at=consumed,
        )

        assert human_input.id == 15
        assert human_input.consumed_at == consumed

    def test_human_input_to_dict(self):
        """HumanInput.to_dict() returns proper dictionary representation."""
        created = datetime(2026, 1, 20, 16, 0, 0)
        consumed = datetime(2026, 1, 20, 16, 5, 0)
        human_input = HumanInput(
            id=30,
            run_id="run-abc",
            input_type=InputType.ABORT,
            content="Stop the run",
            created_at=created,
            consumed_at=consumed,
        )

        result = human_input.to_dict()

        assert result["id"] == 30
        assert result["run_id"] == "run-abc"
        assert result["input_type"] == "abort"
        assert result["content"] == "Stop the run"
        assert result["created_at"] == "2026-01-20T16:00:00"
        assert result["consumed_at"] == "2026-01-20T16:05:00"

    def test_human_input_to_dict_with_none_values(self):
        """HumanInput.to_dict() handles None values correctly."""
        created = datetime(2026, 1, 20, 16, 0, 0)
        human_input = HumanInput(
            id=None,
            run_id="run-def",
            input_type=InputType.RESUME,
            content="",
            created_at=created,
        )

        result = human_input.to_dict()

        assert result["id"] is None
        assert result["consumed_at"] is None
