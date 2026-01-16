"""Unit tests for trace.py - TraceClient and Task classes."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from ralph2.trace import TraceClient, Task


class TestTaskDataclass:
    """Tests for the Task dataclass."""

    def test_task_creation_with_required_fields(self):
        """Test creating a Task with required fields."""
        task = Task(
            id="ralph-test123",
            title="Test task title",
            status="open",
            priority=2,
            project="github.com/test/project",
            created="2024-01-15T10:00:00Z",
            updated="2024-01-15T10:00:00Z",
        )

        assert task.id == "ralph-test123"
        assert task.title == "Test task title"
        assert task.status == "open"
        assert task.priority == 2
        assert task.project == "github.com/test/project"
        assert task.description is None
        assert task.parent is None

    def test_task_creation_with_optional_fields(self):
        """Test creating a Task with optional fields."""
        task = Task(
            id="ralph-test456",
            title="Test with description",
            status="open",
            priority=1,
            project="github.com/test/project",
            created="2024-01-15T10:00:00Z",
            updated="2024-01-15T11:00:00Z",
            description="This is a detailed description\nwith multiple lines",
            parent="ralph-parent789",
        )

        assert task.description == "This is a detailed description\nwith multiple lines"
        assert task.parent == "ralph-parent789"


class TestTraceClientInit:
    """Tests for TraceClient initialization."""

    def test_init_without_project_path(self):
        """Test TraceClient initialization without project path."""
        client = TraceClient()
        assert client.project_path is None

    def test_init_with_project_path(self):
        """Test TraceClient initialization with project path."""
        client = TraceClient(project_path="/path/to/project")
        assert client.project_path == "/path/to/project"


class TestTraceClientRunCommand:
    """Tests for TraceClient._run_command method."""

    def test_run_command_success(self):
        """Test successful command execution."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="command output",
                stderr="",
                returncode=0
            )

            client = TraceClient()
            result = client._run_command(["show", "task-123"])

            assert result == "command output"
            mock_run.assert_called_once()
            # Verify the command was called with trc prefix
            call_args = mock_run.call_args
            assert call_args[0][0] == ["trc", "show", "task-123"]

    def test_run_command_with_project_path(self):
        """Test command execution with project path."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout="output",
                stderr="",
                returncode=0
            )

            client = TraceClient(project_path="/my/project")
            client._run_command(["list"])

            # Verify --project flag was added
            call_args = mock_run.call_args
            assert "--project" in call_args[0][0]
            assert "/my/project" in call_args[0][0]

    def test_run_command_failure_raises_runtime_error(self):
        """Test that command failure raises RuntimeError."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["trc", "show", "nonexistent"],
                stderr="Error: task not found"
            )

            client = TraceClient()
            with pytest.raises(RuntimeError) as exc_info:
                client._run_command(["show", "nonexistent"])

            assert "Trace command failed" in str(exc_info.value)


class TestTraceClientShow:
    """Tests for TraceClient.show method."""

    def test_show_returns_none_on_not_found_and_does_not_log(self, capfd):
        """Test that show returns None when task not found without logging a warning."""
        with patch.object(TraceClient, '_run_command', side_effect=RuntimeError("not found")):
            client = TraceClient()
            task = client.show("nonexistent-task")

            assert task is None

            # Verify no warning was logged for "not found" case
            captured = capfd.readouterr()
            assert "Warning" not in captured.out

    def test_show_logs_warning_on_non_not_found_error(self, capfd):
        """Test that show logs warning for non-'not found' errors."""
        with patch.object(TraceClient, '_run_command', side_effect=RuntimeError("permission denied")):
            client = TraceClient()
            task = client.show("task-123")

            assert task is None

            # Verify warning was logged for non-"not found" error
            captured = capfd.readouterr()
            assert "Warning" in captured.out or "permission denied" in captured.out.lower()

    def test_show_logs_warning_on_connection_error(self, capfd):
        """Test that show logs warning for connection errors."""
        with patch.object(TraceClient, '_run_command', side_effect=RuntimeError("connection refused")):
            client = TraceClient()
            task = client.show("task-123")

            assert task is None

            # Verify warning was logged
            captured = capfd.readouterr()
            assert "Warning" in captured.out or "connection" in captured.out.lower()

    def test_show_returns_task(self):
        """Test that show returns a Task object."""
        mock_output = """ID:          ralph-test123
Title:       Test task title
Status:      open
Priority:    2
Project:     github.com/test/project
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z

Description:
This is the task description.
"""
        with patch.object(TraceClient, '_run_command', return_value=mock_output):
            client = TraceClient()
            task = client.show("ralph-test123")

            assert task is not None
            assert task.id == "ralph-test123"
            assert task.title == "Test task title"
            assert task.status == "open"
            assert task.priority == 2
            assert "This is the task description" in task.description

    def test_show_returns_none_on_not_found(self):
        """Test that show returns None when task not found."""
        with patch.object(TraceClient, '_run_command', side_effect=RuntimeError("not found")):
            client = TraceClient()
            task = client.show("nonexistent-task")

            assert task is None

    def test_show_parses_parent_correctly(self):
        """Test that show parses parent field correctly."""
        mock_output = """ID:          ralph-child
Title:       Child task
Status:      open
Priority:    1
Project:     github.com/test/project
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
Parent:      ralph-parent123
"""
        with patch.object(TraceClient, '_run_command', return_value=mock_output):
            client = TraceClient()
            task = client.show("ralph-child")

            assert task.parent == "ralph-parent123"

    def test_show_handles_multiline_description(self):
        """Test that show handles multiline descriptions correctly."""
        mock_output = """ID:          ralph-test
Title:       Test
Status:      open
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z

Description:
Line 1 of description
Line 2 of description
Line 3 of description

"""
        with patch.object(TraceClient, '_run_command', return_value=mock_output):
            client = TraceClient()
            task = client.show("ralph-test")

            assert "Line 1" in task.description
            assert "Line 2" in task.description
            assert "Line 3" in task.description


class TestTraceClientReady:
    """Tests for TraceClient.ready method."""

    def test_ready_returns_list_of_tasks(self):
        """Test that ready returns a list of Task objects."""
        mock_ready_output = """○ ralph-task1 [P2] First task
○ ralph-task2 [P1] Second task
"""
        mock_show_output_1 = """ID:          ralph-task1
Title:       First task
Status:      open
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        mock_show_output_2 = """ID:          ralph-task2
Title:       Second task
Status:      open
Priority:    1
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        with patch.object(TraceClient, '_run_command') as mock_cmd:
            mock_cmd.side_effect = [
                mock_ready_output,
                mock_show_output_1,
                mock_show_output_2
            ]

            client = TraceClient()
            tasks = client.ready()

            assert len(tasks) == 2
            assert tasks[0].id == "ralph-task1"
            assert tasks[1].id == "ralph-task2"

    def test_ready_returns_empty_list_on_no_tasks(self):
        """Test that ready returns empty list when no tasks are ready."""
        with patch.object(TraceClient, '_run_command', return_value=""):
            client = TraceClient()
            tasks = client.ready()

            assert tasks == []


class TestTraceClientList:
    """Tests for TraceClient.list method."""

    def test_list_includes_closed_tasks(self):
        """Test that list includes both open and closed tasks."""
        mock_list_output = """○ ralph-open [P2] Open task
✓ ralph-closed [P2] Closed task
"""
        mock_show_open = """ID:          ralph-open
Title:       Open task
Status:      open
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        mock_show_closed = """ID:          ralph-closed
Title:       Closed task
Status:      closed
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        with patch.object(TraceClient, '_run_command') as mock_cmd:
            mock_cmd.side_effect = [
                mock_list_output,
                mock_show_open,
                mock_show_closed
            ]

            client = TraceClient()
            tasks = client.list()

            assert len(tasks) == 2


class TestTraceClientCreate:
    """Tests for TraceClient.create method."""

    def test_create_task_success(self):
        """Test successful task creation."""
        mock_create_output = "Created ralph-new123"
        mock_show_output = """ID:          ralph-new123
Title:       New task
Status:      open
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        with patch.object(TraceClient, '_run_command') as mock_cmd:
            mock_cmd.side_effect = [mock_create_output, mock_show_output]

            client = TraceClient()
            task = client.create("New task", description="Task description")

            assert task.id == "ralph-new123"
            assert task.title == "New task"
            # Verify create was called with correct args
            first_call_args = mock_cmd.call_args_list[0][0][0]
            assert "create" in first_call_args
            assert "New task" in first_call_args

    def test_create_task_with_parent(self):
        """Test creating task with parent."""
        mock_create_output = "Created ralph-child"
        mock_show_output = """ID:          ralph-child
Title:       Child task
Status:      open
Priority:    2
Project:     test
Created:     2024-01-15T10:00:00Z
Updated:     2024-01-15T10:00:00Z
"""
        with patch.object(TraceClient, '_run_command') as mock_cmd:
            mock_cmd.side_effect = [mock_create_output, mock_show_output]

            client = TraceClient()
            task = client.create("Child task", parent="ralph-parent")

            # Verify --parent flag was used
            first_call_args = mock_cmd.call_args_list[0][0][0]
            assert "--parent" in first_call_args
            assert "ralph-parent" in first_call_args

    def test_create_task_fails_if_retrieval_fails(self):
        """Test that create raises error if task retrieval fails."""
        mock_create_output = "Created ralph-new"

        with patch.object(TraceClient, '_run_command') as mock_cmd:
            mock_cmd.side_effect = [
                mock_create_output,
                RuntimeError("task not found")  # show fails
            ]

            client = TraceClient()
            with pytest.raises(RuntimeError) as exc_info:
                client.create("New task")

            assert "Failed to retrieve created task" in str(exc_info.value)


class TestTraceClientClose:
    """Tests for TraceClient.close method."""

    def test_close_task_success(self):
        """Test successful task closing."""
        with patch.object(TraceClient, '_run_command', return_value="Closed ralph-test"):
            client = TraceClient()
            client.close("ralph-test")  # Should not raise

    def test_close_nonexistent_task_raises_error(self):
        """Test that closing nonexistent task raises error."""
        with patch.object(TraceClient, '_run_command', side_effect=RuntimeError("not found")):
            client = TraceClient()
            with pytest.raises(RuntimeError):
                client.close("nonexistent-task")


class TestTraceClientComment:
    """Tests for TraceClient.comment method."""

    def test_comment_success(self):
        """Test successful comment addition."""
        with patch.object(TraceClient, '_run_command', return_value=""):
            client = TraceClient()
            client.comment("ralph-test", "This is a comment")  # Should not raise


class TestTraceClientGetTaskStateSummary:
    """Tests for TraceClient.get_task_state_summary method."""

    def test_get_task_state_summary(self):
        """Test getting task state summary."""
        # Create mock tasks
        open_task = Task(
            id="ralph-open",
            title="Open",
            status="open",
            priority=2,
            project="test",
            created="2024-01-15",
            updated="2024-01-15"
        )
        closed_task = Task(
            id="ralph-closed",
            title="Closed",
            status="closed",
            priority=2,
            project="test",
            created="2024-01-15",
            updated="2024-01-15"
        )

        with patch.object(TraceClient, 'list', return_value=[open_task, closed_task]):
            with patch.object(TraceClient, 'ready', return_value=[open_task]):
                client = TraceClient()
                summary = client.get_task_state_summary()

                assert summary['total'] == 2
                assert summary['open'] == 1
                assert summary['closed'] == 1
                assert summary['ready'] == 1
                assert len(summary['ready_tasks']) == 1
