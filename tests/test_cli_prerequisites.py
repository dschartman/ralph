"""Tests for CLI prerequisite validation."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from rich.console import Console

# Import the validation function
from ralph.cli import _validate_prerequisites


@pytest.fixture
def mock_console():
    """Mock Rich console for testing output."""
    with patch("ralph.cli.console") as mock:
        yield mock


class TestPrerequisiteValidation:
    """Test suite for _validate_prerequisites function."""

    def test_git_repository_check_fails_when_not_in_git_repo(self, mock_console, tmp_path):
        """Test that validation fails when not in a git repository."""
        # Change to a non-git directory
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("subprocess.run") as mock_run:
                # Simulate git command failing (not a git repo)
                mock_run.return_value = Mock(returncode=1, stderr="not a git repository")

                result = _validate_prerequisites()

                assert result is False
                mock_console.print.assert_any_call("[red]Error:[/red] Not in a git repository")
        finally:
            os.chdir(original_dir)

    def test_git_command_not_found(self, mock_console):
        """Test that validation fails when git is not installed."""
        with patch("subprocess.run") as mock_run:
            # Simulate git command not found
            mock_run.side_effect = FileNotFoundError()

            result = _validate_prerequisites()

            assert result is False
            mock_console.print.assert_any_call("[red]Error:[/red] git command not found")

    def test_trc_command_not_available(self, mock_console):
        """Test that validation fails when trc command is not available."""
        with patch("subprocess.run") as mock_run:
            # Mock git check to succeed
            def run_side_effect(*args, **kwargs):
                if args[0][0] == "git":
                    return Mock(returncode=0)
                elif args[0][0] == "trc":
                    raise FileNotFoundError()

            mock_run.side_effect = run_side_effect

            result = _validate_prerequisites()

            assert result is False
            mock_console.print.assert_any_call("[red]Error:[/red] trc command not found")

    def test_trc_command_fails(self, mock_console):
        """Test that validation fails when trc command returns error."""
        with patch("subprocess.run") as mock_run:
            # Mock git check to succeed, trc to fail
            def run_side_effect(*args, **kwargs):
                if args[0][0] == "git":
                    return Mock(returncode=0)
                elif args[0][0] == "trc":
                    return Mock(returncode=1)

            mock_run.side_effect = run_side_effect

            result = _validate_prerequisites()

            assert result is False
            mock_console.print.assert_any_call("[red]Error:[/red] trc command not available")

    def test_trace_initialization_when_not_exists(self, mock_console, tmp_path):
        """Test that Trace is initialized when .trace directory doesn't exist."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("subprocess.run") as mock_run:
                # Mock git and trc checks to succeed
                def run_side_effect(*args, **kwargs):
                    if args[0][0] == "git":
                        return Mock(returncode=0)
                    elif args[0] == ["trc", "--help"]:
                        return Mock(returncode=0)
                    elif args[0] == ["trc", "init"]:
                        # Create .trace directory to simulate successful init
                        (tmp_path / ".trace").mkdir()
                        return Mock(returncode=0)

                mock_run.side_effect = run_side_effect

                result = _validate_prerequisites()

                assert result is True
                mock_console.print.assert_any_call("[yellow]Trace not initialized. Initializing...[/yellow]")
                mock_console.print.assert_any_call("[green]✓[/green] Trace initialized")
        finally:
            os.chdir(original_dir)

    def test_trace_init_failure(self, mock_console, tmp_path):
        """Test that validation fails when trc init fails."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            with patch("subprocess.run") as mock_run:
                # Mock git and trc checks to succeed, but trc init to fail
                def run_side_effect(*args, **kwargs):
                    if args[0][0] == "git":
                        return Mock(returncode=0)
                    elif args[0] == ["trc", "--help"]:
                        return Mock(returncode=0)
                    elif args[0] == ["trc", "init"]:
                        return Mock(returncode=1, stderr="init failed")

                mock_run.side_effect = run_side_effect

                result = _validate_prerequisites()

                assert result is False
                assert any("Failed to initialize Trace" in str(call) for call in mock_console.print.call_args_list)
        finally:
            os.chdir(original_dir)

    def test_gitignore_created_with_ralph_id_entry(self, mock_console, tmp_path):
        """Test that .gitignore is created with .ralph-id entry when it doesn't exist."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            gitignore_path = tmp_path / ".gitignore"
            trace_dir = tmp_path / ".trace"
            trace_dir.mkdir()
            # Create Ralphfile so project root can be found
            (tmp_path / "Ralphfile").write_text("# Test spec")

            with patch("subprocess.run") as mock_run:
                # Mock all checks to succeed
                mock_run.return_value = Mock(returncode=0)

                result = _validate_prerequisites()

                assert result is True
                assert gitignore_path.exists()
                assert ".ralph-id" in gitignore_path.read_text()
                mock_console.print.assert_any_call("[green]✓[/green] Added .ralph-id to .gitignore")
        finally:
            os.chdir(original_dir)

    def test_gitignore_updated_with_ralph_id_entry(self, mock_console, tmp_path):
        """Test that .ralph-id is added to existing .gitignore if not present."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text("*.pyc\n__pycache__/\n")
            trace_dir = tmp_path / ".trace"
            trace_dir.mkdir()
            # Create Ralphfile so project root can be found
            (tmp_path / "Ralphfile").write_text("# Test spec")

            with patch("subprocess.run") as mock_run:
                # Mock all checks to succeed
                mock_run.return_value = Mock(returncode=0)

                result = _validate_prerequisites()

                assert result is True
                content = gitignore_path.read_text()
                assert ".ralph-id" in content
                assert "*.pyc" in content  # Original content preserved
                mock_console.print.assert_any_call("[green]✓[/green] Added .ralph-id to .gitignore")
        finally:
            os.chdir(original_dir)

    def test_gitignore_not_modified_when_ralph_id_already_present(self, mock_console, tmp_path):
        """Test that .gitignore is not modified if .ralph-id is already present."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            gitignore_path = tmp_path / ".gitignore"
            original_content = "*.pyc\n.ralph-id\n__pycache__/\n"
            gitignore_path.write_text(original_content)
            trace_dir = tmp_path / ".trace"
            trace_dir.mkdir()
            # Create Ralphfile so project root can be found
            (tmp_path / "Ralphfile").write_text("# Test spec")

            with patch("subprocess.run") as mock_run:
                # Mock all checks to succeed
                mock_run.return_value = Mock(returncode=0)

                result = _validate_prerequisites()

                assert result is True
                # Content should be unchanged
                assert gitignore_path.read_text() == original_content
                # Should not print the "Added" message
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert not any("Added .ralph-id to .gitignore" in call for call in calls)
        finally:
            os.chdir(original_dir)

    def test_all_prerequisites_pass(self, mock_console, tmp_path):
        """Test that validation passes when all prerequisites are met."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            gitignore_path = tmp_path / ".gitignore"
            gitignore_path.write_text(".ralph-id\n")
            trace_dir = tmp_path / ".trace"
            trace_dir.mkdir()
            # Create Ralphfile so project root can be found
            (tmp_path / "Ralphfile").write_text("# Test spec")

            with patch("subprocess.run") as mock_run:
                # Mock all checks to succeed
                mock_run.return_value = Mock(returncode=0)

                result = _validate_prerequisites()

                assert result is True
        finally:
            os.chdir(original_dir)
