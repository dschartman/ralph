"""Tests for ACT data structures and act() function."""

import pytest
from pydantic import ValidationError

from soda.act import (
    ActOutput,
    BlockedTask,
    TaskComment,
    NewTask,
)


# =============================================================================
# BlockedTask Model Tests
# =============================================================================


class TestBlockedTask:
    """Tests for BlockedTask model."""

    def test_blocked_task_creation(self):
        """BlockedTask can be created with task_id and reason."""
        blocked = BlockedTask(
            task_id="ralph-abc123",
            reason="Missing API key for external service",
        )
        assert blocked.task_id == "ralph-abc123"
        assert blocked.reason == "Missing API key for external service"

    def test_blocked_task_requires_task_id(self):
        """BlockedTask requires task_id field."""
        with pytest.raises(ValidationError):
            BlockedTask(reason="Some reason")

    def test_blocked_task_requires_reason(self):
        """BlockedTask requires reason field."""
        with pytest.raises(ValidationError):
            BlockedTask(task_id="ralph-abc123")

    def test_blocked_task_serialization(self):
        """BlockedTask can be serialized to dict."""
        blocked = BlockedTask(
            task_id="ralph-xyz789",
            reason="Tests require database connection",
        )
        data = blocked.model_dump()
        assert data["task_id"] == "ralph-xyz789"
        assert data["reason"] == "Tests require database connection"


# =============================================================================
# TaskComment Model Tests
# =============================================================================


class TestTaskComment:
    """Tests for TaskComment model (ACT-specific, simpler than sense.TaskComment)."""

    def test_task_comment_creation(self):
        """TaskComment can be created with task_id and comment."""
        comment = TaskComment(
            task_id="ralph-abc123",
            comment="Started working on implementation",
        )
        assert comment.task_id == "ralph-abc123"
        assert comment.comment == "Started working on implementation"

    def test_task_comment_requires_task_id(self):
        """TaskComment requires task_id field."""
        with pytest.raises(ValidationError):
            TaskComment(comment="Some comment")

    def test_task_comment_requires_comment(self):
        """TaskComment requires comment field."""
        with pytest.raises(ValidationError):
            TaskComment(task_id="ralph-abc123")

    def test_task_comment_serialization(self):
        """TaskComment can be serialized to dict."""
        comment = TaskComment(
            task_id="ralph-xyz789",
            comment="Completed unit tests",
        )
        data = comment.model_dump()
        assert data["task_id"] == "ralph-xyz789"
        assert data["comment"] == "Completed unit tests"


# =============================================================================
# NewTask Model Tests (imported from orient, verify it works)
# =============================================================================


class TestNewTask:
    """Tests for NewTask model (reused from orient)."""

    def test_new_task_creation_minimal(self):
        """NewTask can be created with just title and description."""
        task = NewTask(
            title="Add validation",
            description="Add input validation to the API endpoint",
        )
        assert task.title == "Add validation"
        assert task.description == "Add input validation to the API endpoint"
        assert task.priority == 1  # default

    def test_new_task_creation_full(self):
        """NewTask can be created with all fields."""
        task = NewTask(
            title="Fix bug",
            description="Fix null pointer in parser",
            priority=0,
            parent_id="ralph-abc123",
            blocked_by="ralph-xyz789",
        )
        assert task.title == "Fix bug"
        assert task.description == "Fix null pointer in parser"
        assert task.priority == 0
        assert task.parent_id == "ralph-abc123"
        assert task.blocked_by == "ralph-xyz789"

    def test_new_task_requires_title(self):
        """NewTask requires title field."""
        with pytest.raises(ValidationError):
            NewTask(description="Some description")

    def test_new_task_requires_description(self):
        """NewTask requires description field."""
        with pytest.raises(ValidationError):
            NewTask(title="Some title")

    def test_new_task_priority_validation(self):
        """NewTask priority must be 0, 1, or 2."""
        with pytest.raises(ValidationError):
            NewTask(title="Test", description="Desc", priority=3)
        with pytest.raises(ValidationError):
            NewTask(title="Test", description="Desc", priority=-1)


# =============================================================================
# ActOutput Model Tests
# =============================================================================


class TestActOutput:
    """Tests for ActOutput model."""

    def test_act_output_creation_empty(self):
        """ActOutput can be created with empty lists (all work blocked)."""
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=[],
        )
        assert output.tasks_completed == []
        assert output.tasks_blocked == []
        assert output.task_comments == []
        assert output.new_subtasks == []
        assert output.learnings == []
        assert output.commits == []

    def test_act_output_creation_with_completed_tasks(self):
        """ActOutput can include completed task IDs."""
        output = ActOutput(
            tasks_completed=["ralph-abc123", "ralph-def456"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["a1b2c3d"],
        )
        assert output.tasks_completed == ["ralph-abc123", "ralph-def456"]
        assert output.commits == ["a1b2c3d"]

    def test_act_output_creation_with_blocked_tasks(self):
        """ActOutput can include blocked tasks with reasons."""
        blocked = BlockedTask(
            task_id="ralph-xyz789",
            reason="External API unavailable",
        )
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[blocked],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=[],
        )
        assert len(output.tasks_blocked) == 1
        assert output.tasks_blocked[0].task_id == "ralph-xyz789"
        assert output.tasks_blocked[0].reason == "External API unavailable"

    def test_act_output_creation_with_comments(self):
        """ActOutput can include task comments."""
        comment = TaskComment(
            task_id="ralph-abc123",
            comment="Implemented feature X",
        )
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[],
            task_comments=[comment],
            new_subtasks=[],
            learnings=[],
            commits=["abc1234"],
        )
        assert len(output.task_comments) == 1
        assert output.task_comments[0].comment == "Implemented feature X"

    def test_act_output_creation_with_subtasks(self):
        """ActOutput can include new subtasks discovered during work."""
        subtask = NewTask(
            title="Handle edge case",
            description="Add handling for null input",
            parent_id="ralph-abc123",
        )
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[subtask],
            learnings=[],
            commits=[],
        )
        assert len(output.new_subtasks) == 1
        assert output.new_subtasks[0].title == "Handle edge case"
        assert output.new_subtasks[0].parent_id == "ralph-abc123"

    def test_act_output_creation_with_learnings(self):
        """ActOutput can include learnings/efficiency knowledge."""
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[
                "Run tests with `uv run pytest tests/soda/ -v`",
                "API client is in src/soda/api.py",
            ],
            commits=["abc1234"],
        )
        assert len(output.learnings) == 2
        assert "pytest" in output.learnings[0]

    def test_act_output_creation_with_multiple_commits(self):
        """ActOutput can include multiple commit hashes."""
        output = ActOutput(
            tasks_completed=["ralph-abc123", "ralph-def456"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["a1b2c3d", "e5f6g7h", "i9j0k1l"],
        )
        assert len(output.commits) == 3

    def test_act_output_full_example(self):
        """ActOutput can hold a realistic full ACT phase output."""
        output = ActOutput(
            tasks_completed=["ralph-task1", "ralph-task2"],
            tasks_blocked=[
                BlockedTask(
                    task_id="ralph-task3",
                    reason="Requires external API key",
                ),
            ],
            task_comments=[
                TaskComment(
                    task_id="ralph-task1",
                    comment="Started implementation",
                ),
                TaskComment(
                    task_id="ralph-task1",
                    comment="Tests passing",
                ),
                TaskComment(
                    task_id="ralph-task3",
                    comment="Blocked: needs API key",
                ),
            ],
            new_subtasks=[
                NewTask(
                    title="Add error handling",
                    description="Handle timeout errors in API client",
                    parent_id="ralph-task1",
                    priority=1,
                ),
            ],
            learnings=[
                "Project uses uv for dependency management",
                "Run `trc list` to see all tasks",
            ],
            commits=["abc1234def", "567890abc"],
        )
        assert len(output.tasks_completed) == 2
        assert len(output.tasks_blocked) == 1
        assert len(output.task_comments) == 3
        assert len(output.new_subtasks) == 1
        assert len(output.learnings) == 2
        assert len(output.commits) == 2

    def test_act_output_serialization(self):
        """ActOutput can be serialized to dict (JSON-compatible)."""
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[
                BlockedTask(task_id="ralph-xyz789", reason="Blocked reason"),
            ],
            task_comments=[
                TaskComment(task_id="ralph-abc123", comment="Done"),
            ],
            new_subtasks=[
                NewTask(title="Subtask", description="Desc"),
            ],
            learnings=["A learning"],
            commits=["abc1234"],
        )
        data = output.model_dump()
        assert data["tasks_completed"] == ["ralph-abc123"]
        assert data["tasks_blocked"][0]["task_id"] == "ralph-xyz789"
        assert data["task_comments"][0]["comment"] == "Done"
        assert data["new_subtasks"][0]["title"] == "Subtask"
        assert data["learnings"] == ["A learning"]
        assert data["commits"] == ["abc1234"]

    def test_act_output_defaults_to_empty_lists(self):
        """ActOutput uses default_factory for empty lists."""
        output = ActOutput()
        assert output.tasks_completed == []
        assert output.tasks_blocked == []
        assert output.task_comments == []
        assert output.new_subtasks == []
        assert output.learnings == []
        assert output.commits == []
