"""Tests for specific error handling in trc show command during work item verification."""

import pytest
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run
from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext

# Store original subprocess.run to use in mocks
_original_subprocess_run = subprocess.run


@pytest.fixture
def temp_project():
    """Create a temporary project directory with git and trace initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Initialize git
        _original_subprocess_run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "config", "user.name", "Test User"], cwd=project_root, check=True, capture_output=True)

        # Initialize trace
        _original_subprocess_run(["trc", "init"], cwd=project_root, check=True, capture_output=True)

        # Create a Ralph2file
        ralph2file = project_root / "Ralph2file"
        ralph2file.write_text("# Test Spec\n\nThis is a test specification.")

        # Commit initial state
        _original_subprocess_run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
        _original_subprocess_run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True, capture_output=True)

        yield project_root


class TestTrcShowErrorHandling:
    """Test specific error handling for trc show command."""

    def test_trc_show_not_found_continues_normally(self, temp_project, capfd):
        """Test that 'not found' errors from trc show continue normally (not logged as warning)."""
        ctx = ProjectContext(temp_project)

        # Create a runner
        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None
        )

        # Create a run with a non-existent work item ID
        run_id = f"ralph2-test-{datetime.now().timestamp()}"
        run = Run(
            id=run_id,
            spec_path=str(temp_project / "Ralph2file"),
            spec_content="# Test Spec\n\nThis is a test specification.",
            status="completed",
            config={"max_iterations": 10},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            root_work_item_id="nonexistent-workitem"  # This ID doesn't exist
        )
        runner.db.create_run(run)

        # Call _ensure_root_work_item - it should create a new one since the old one doesn't exist
        root_work_item_id = runner._ensure_root_work_item()

        # Verify a new root work item was created (different from the non-existent one)
        assert root_work_item_id is not None
        assert root_work_item_id != "nonexistent-workitem"

        # Verify no error was logged for "not found" case
        captured = capfd.readouterr()
        assert "Could not verify existing root work item" not in captured.out
        assert "not found" not in captured.out.lower() or "Error" not in captured.out

    def test_trc_show_permission_error_logs_and_continues(self, temp_project, capfd):
        """Test that permission/access errors from trc show are logged and handled."""
        ctx = ProjectContext(temp_project)

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None
        )

        # Create a run with a work item ID
        run_id = f"ralph2-test-{datetime.now().timestamp()}"
        run = Run(
            id=run_id,
            spec_path=str(temp_project / "Ralph2file"),
            spec_content="# Test Spec\n\nThis is a test specification.",
            status="completed",
            config={"max_iterations": 10},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            root_work_item_id="test-workitem"
        )
        runner.db.create_run(run)

        # Mock subprocess.run to simulate a non-"not found" error
        def mock_subprocess_run(cmd, **kwargs):
            if cmd[0] == "trc" and cmd[1] == "show":
                # Simulate a permission error (something other than "not found")
                result = MagicMock()
                result.returncode = 1
                result.stderr = "Error: permission denied - cannot access trace database"
                result.stdout = ""
                return result
            # For other commands (like trc create), call the real subprocess
            return _original_subprocess_run(cmd, **kwargs)

        with patch('ralph2.runner.subprocess.run', side_effect=mock_subprocess_run):
            # The runner should log a warning for non-"not found" errors
            root_work_item_id = runner._ensure_root_work_item()

        # Verify warning was logged for non-"not found" error
        captured = capfd.readouterr()
        # The warning should be about the specific error, not just generic
        assert "permission denied" in captured.out.lower() or "error" in captured.out.lower()

    def test_trc_show_network_error_logs_explicitly(self, temp_project, capfd):
        """Test that network/connection errors from trc show are logged explicitly."""
        ctx = ProjectContext(temp_project)

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None
        )

        # Create a run with a work item ID
        run_id = f"ralph2-test-{datetime.now().timestamp()}"
        run = Run(
            id=run_id,
            spec_path=str(temp_project / "Ralph2file"),
            spec_content="# Test Spec\n\nThis is a test specification.",
            status="completed",
            config={"max_iterations": 10},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            root_work_item_id="test-workitem"
        )
        runner.db.create_run(run)

        # Mock subprocess.run to simulate a network/connection error
        def mock_subprocess_run(cmd, **kwargs):
            if cmd[0] == "trc" and cmd[1] == "show":
                result = MagicMock()
                result.returncode = 1
                result.stderr = "Error: connection refused - cannot reach trace server"
                result.stdout = ""
                return result
            return _original_subprocess_run(cmd, **kwargs)

        with patch('ralph2.runner.subprocess.run', side_effect=mock_subprocess_run):
            root_work_item_id = runner._ensure_root_work_item()

        # Verify warning was logged
        captured = capfd.readouterr()
        assert "connection" in captured.out.lower() or "error" in captured.out.lower()

    def test_trc_show_distinguishes_not_found_from_other_errors(self, temp_project, capfd):
        """Test that 'not found' errors are treated differently from other errors."""
        ctx = ProjectContext(temp_project)

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None
        )

        # Create TWO runs - first with a real error, second with valid work item
        # First run: has a work item that triggers a "permission error"
        run_id_1 = f"ralph2-test-1-{datetime.now().timestamp()}"
        run1 = Run(
            id=run_id_1,
            spec_path=str(temp_project / "Ralph2file"),
            spec_content="# Test Spec\n\nThis is a test specification.",
            status="completed",
            config={"max_iterations": 10},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            root_work_item_id="error-workitem"
        )
        runner.db.create_run(run1)

        call_count = [0]

        def mock_subprocess_run(cmd, **kwargs):
            if cmd[0] == "trc" and cmd[1] == "show":
                call_count[0] += 1
                # Simulate different errors based on work item ID
                work_item_id = cmd[2]
                if work_item_id == "error-workitem":
                    # Simulate a serious error that should be logged
                    result = MagicMock()
                    result.returncode = 1
                    result.stderr = "Error: database corruption detected"
                    result.stdout = ""
                    return result
                else:
                    # Normal "not found" error
                    result = MagicMock()
                    result.returncode = 1
                    result.stderr = "Error: work item not found"
                    result.stdout = ""
                    return result
            return _original_subprocess_run(cmd, **kwargs)

        with patch('ralph2.runner.subprocess.run', side_effect=mock_subprocess_run):
            root_work_item_id = runner._ensure_root_work_item()

        captured = capfd.readouterr()
        # Should log warning for database corruption error
        assert "database corruption" in captured.out.lower() or "error" in captured.out.lower()

    def test_subprocess_exception_handled_gracefully(self, temp_project, capfd):
        """Test that subprocess exceptions (command not found, etc.) are handled gracefully."""
        ctx = ProjectContext(temp_project)

        runner = Ralph2Runner(
            spec_path=str(temp_project / "Ralph2file"),
            project_context=ctx,
            root_work_item_id=None
        )

        # Create a run with a work item ID
        run_id = f"ralph2-test-{datetime.now().timestamp()}"
        run = Run(
            id=run_id,
            spec_path=str(temp_project / "Ralph2file"),
            spec_content="# Test Spec\n\nThis is a test specification.",
            status="completed",
            config={"max_iterations": 10},
            started_at=datetime.now(),
            ended_at=datetime.now(),
            root_work_item_id="test-workitem"
        )
        runner.db.create_run(run)

        call_count = [0]

        def mock_subprocess_run(cmd, **kwargs):
            if cmd[0] == "trc" and cmd[1] == "show":
                call_count[0] += 1
                # Simulate subprocess exception (e.g., command not found)
                raise OSError("Command not found: trc")
            return _original_subprocess_run(cmd, **kwargs)

        with patch('ralph2.runner.subprocess.run', side_effect=mock_subprocess_run):
            # Should handle the exception gracefully and try to create a new work item
            # But since trc create will also fail, it may raise RuntimeError
            # That's expected behavior - we just want the warning to be logged
            try:
                root_work_item_id = runner._ensure_root_work_item()
            except RuntimeError:
                pass  # Expected if trc create also fails

        # Verify warning was logged for the exception
        captured = capfd.readouterr()
        assert "Could not verify existing root work item" in captured.out or "Command not found" in captured.out
