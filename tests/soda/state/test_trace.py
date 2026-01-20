"""Tests for Soda Trace CLI integration."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from soda.state.trace import (
    Comment,
    Task,
    TraceClient,
    TraceError,
)


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self):
        """Task can be created with required fields."""
        task = Task(
            id="ralph-123",
            title="Test task",
            status="open",
            priority=2,
        )
        assert task.id == "ralph-123"
        assert task.title == "Test task"
        assert task.status == "open"
        assert task.priority == 2
        assert task.description is None
        assert task.parent_id is None

    def test_task_with_optional_fields(self):
        """Task can be created with optional fields."""
        task = Task(
            id="ralph-123",
            title="Test task",
            status="open",
            priority=2,
            description="A detailed description",
            parent_id="ralph-parent",
        )
        assert task.description == "A detailed description"
        assert task.parent_id == "ralph-parent"


class TestComment:
    """Tests for Comment dataclass."""

    def test_comment_creation(self):
        """Comment can be created with required fields."""
        comment = Comment(
            timestamp="2026-01-20 15:30:00",
            source="executor",
            text="Test comment",
        )
        assert comment.timestamp == "2026-01-20 15:30:00"
        assert comment.source == "executor"
        assert comment.text == "Test comment"


class TestTraceClientGetOpenTasks:
    """Tests for TraceClient.get_open_tasks()."""

    def test_get_open_tasks_parses_ready_output(self):
        """get_open_tasks parses trc ready output correctly."""
        client = TraceClient()
        mock_output = """Ready work (not blocked):

\u25cb ralph-abc123 [P2] Test task one
   \u2514\u2500 child of: ralph-parent - Parent task
\u25cb ralph-def456 [P1] Test task two
"""
        with patch.object(client, "_run_command", return_value=mock_output):
            tasks = client.get_open_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "ralph-abc123"
        assert tasks[0].title == "Test task one"
        assert tasks[0].priority == 2
        assert tasks[0].parent_id == "ralph-parent"

        assert tasks[1].id == "ralph-def456"
        assert tasks[1].title == "Test task two"
        assert tasks[1].priority == 1
        assert tasks[1].parent_id is None

    def test_get_open_tasks_with_root_filter(self):
        """get_open_tasks filters by root_id."""
        client = TraceClient()
        mock_output = """Ready work (not blocked):

\u25cb ralph-child1 [P2] Child task one
   \u2514\u2500 child of: ralph-root - Root task
\u25cb ralph-other [P2] Other task
   \u2514\u2500 child of: ralph-different - Different parent
"""
        with patch.object(client, "_run_command", return_value=mock_output):
            tasks = client.get_open_tasks(root_id="ralph-root")

        # Should only return tasks under ralph-root
        assert len(tasks) == 1
        assert tasks[0].id == "ralph-child1"

    def test_get_open_tasks_handles_empty_output(self):
        """get_open_tasks handles empty results."""
        client = TraceClient()
        mock_output = "Ready work (not blocked):\n\n"
        with patch.object(client, "_run_command", return_value=mock_output):
            tasks = client.get_open_tasks()

        assert tasks == []


class TestTraceClientGetBlockedTasks:
    """Tests for TraceClient.get_blocked_tasks()."""

    def test_get_blocked_tasks_identifies_blocked(self):
        """get_blocked_tasks returns blocked tasks."""
        client = TraceClient()
        # trc list output includes all tasks, but trc ready only shows unblocked
        # Blocked tasks are those in list but not in ready
        mock_list_output = """\u25cb ralph-task1 [P2] Unblocked task
\u25cb ralph-task2 [P2] Blocked task
   \u2514\u2500 blocked by: ralph-blocker - Blocker
"""
        with patch.object(client, "_run_command", return_value=mock_list_output):
            tasks = client.get_blocked_tasks()

        # Should identify task2 as blocked (has "blocked by" line)
        assert len(tasks) == 1
        assert tasks[0].id == "ralph-task2"

    def test_get_blocked_tasks_handles_no_blocked(self):
        """get_blocked_tasks returns empty when no blocked tasks."""
        client = TraceClient()
        mock_output = """\u25cb ralph-task1 [P2] Unblocked task
"""
        with patch.object(client, "_run_command", return_value=mock_output):
            tasks = client.get_blocked_tasks()

        assert tasks == []


class TestTraceClientGetTaskComments:
    """Tests for TraceClient.get_task_comments()."""

    def test_get_task_comments_parses_show_output(self):
        """get_task_comments parses trc show output correctly."""
        client = TraceClient()
        mock_output = """ID:          ralph-test123
Title:       Test task
Status:      open
Priority:    2
Project:     test-project (uuid-here)
Created:     2026-01-20T10:00:00Z
Updated:     2026-01-20T15:00:00Z

Description:
Test description here

Comments:
  [2026-01-20 10:30:00] planner: First comment
  [2026-01-20 11:00:00] executor: Second comment
"""
        with patch.object(client, "_run_command", return_value=mock_output):
            comments = client.get_task_comments("ralph-test123")

        assert len(comments) == 2
        assert comments[0].timestamp == "2026-01-20 10:30:00"
        assert comments[0].source == "planner"
        assert comments[0].text == "First comment"
        assert comments[1].source == "executor"
        assert comments[1].text == "Second comment"

    def test_get_task_comments_handles_no_comments(self):
        """get_task_comments handles tasks without comments."""
        client = TraceClient()
        mock_output = """ID:          ralph-test123
Title:       Test task
Status:      open
Priority:    2
Project:     test-project
Created:     2026-01-20T10:00:00Z
Updated:     2026-01-20T15:00:00Z

Description:
Test description
"""
        with patch.object(client, "_run_command", return_value=mock_output):
            comments = client.get_task_comments("ralph-test123")

        assert comments == []


class TestTraceClientCreateTask:
    """Tests for TraceClient.create_task()."""

    def test_create_task_returns_task_id(self):
        """create_task returns the created task ID."""
        client = TraceClient()
        mock_output = "Created issue ralph-new123: New task title\n"
        with patch.object(client, "_run_command", return_value=mock_output):
            task_id = client.create_task(
                title="New task title",
                description="Task description",
            )

        assert task_id == "ralph-new123"

    def test_create_task_with_parent(self):
        """create_task passes parent to trc create."""
        client = TraceClient()
        mock_output = "Created issue ralph-child: Child task\n"
        with patch.object(client, "_run_command", return_value=mock_output) as mock_run:
            client.create_task(
                title="Child task",
                description="Child description",
                parent="ralph-parent",
            )

        # Verify command includes --parent
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--parent" in cmd
        assert "ralph-parent" in cmd

    def test_create_task_calls_trc_correctly(self):
        """create_task calls trc with correct arguments."""
        client = TraceClient()
        mock_output = "Created issue ralph-new: Title\n"
        with patch.object(client, "_run_command", return_value=mock_output) as mock_run:
            client.create_task(
                title="My Task",
                description="My Description",
            )

        call_args = mock_run.call_args[0][0]
        assert "trc" in call_args
        assert "create" in call_args
        assert "My Task" in call_args
        assert "--description" in call_args
        assert "My Description" in call_args


class TestTraceClientCloseTask:
    """Tests for TraceClient.close_task()."""

    def test_close_task_calls_trc_close(self):
        """close_task calls trc close with task ID."""
        client = TraceClient()
        with patch.object(client, "_run_command", return_value="") as mock_run:
            client.close_task("ralph-toclose")

        call_args = mock_run.call_args[0][0]
        assert "trc" in call_args
        assert "close" in call_args
        assert "ralph-toclose" in call_args

    def test_close_task_with_message(self):
        """close_task can include closing message."""
        client = TraceClient()
        with patch.object(client, "_run_command", return_value="") as mock_run:
            client.close_task("ralph-toclose", message="Done!")

        call_args = mock_run.call_args[0][0]
        assert "--message" in call_args
        assert "Done!" in call_args


class TestTraceClientPostComment:
    """Tests for TraceClient.post_comment()."""

    def test_post_comment_calls_trc_comment(self):
        """post_comment calls trc comment with correct args."""
        client = TraceClient()
        with patch.object(client, "_run_command", return_value="") as mock_run:
            client.post_comment("ralph-task", "My comment text")

        call_args = mock_run.call_args[0][0]
        assert "trc" in call_args
        assert "comment" in call_args
        assert "ralph-task" in call_args
        assert "My comment text" in call_args

    def test_post_comment_with_source(self):
        """post_comment can specify source."""
        client = TraceClient()
        with patch.object(client, "_run_command", return_value="") as mock_run:
            client.post_comment("ralph-task", "Comment", source="executor")

        call_args = mock_run.call_args[0][0]
        assert "--source" in call_args
        assert "executor" in call_args


class TestTraceClientRunCommand:
    """Tests for TraceClient._run_command()."""

    def test_run_command_executes_subprocess(self):
        """_run_command executes subprocess and returns output."""
        client = TraceClient()
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                stdout="command output",
                returncode=0,
            )
            result = client._run_command(["trc", "list"])

        mock_subprocess.assert_called_once()
        assert result == "command output"

    def test_run_command_raises_on_error(self):
        """_run_command raises TraceError on command failure."""
        client = TraceClient()
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                stdout="",
                stderr="Error message",
                returncode=1,
            )
            with pytest.raises(TraceError) as exc_info:
                client._run_command(["trc", "invalid"])

        assert "Error message" in str(exc_info.value)

    def test_run_command_handles_subprocess_exception(self):
        """_run_command handles subprocess.CalledProcessError."""
        client = TraceClient()
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.side_effect = subprocess.SubprocessError("trc not found")
            with pytest.raises(TraceError) as exc_info:
                client._run_command(["trc", "list"])

        assert "trc not found" in str(exc_info.value)


class TestTraceError:
    """Tests for TraceError exception."""

    def test_trace_error_inherits_from_exception(self):
        """TraceError is a proper exception."""
        error = TraceError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"
