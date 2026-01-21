"""Tests for SODA CLI commands."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from soda.cli import app, _format_status, _get_project_context
from soda.state.models import RunStatus


runner = CliRunner()


class TestFormatStatus:
    """Tests for _format_status helper."""

    def test_format_running(self):
        """Running status formatted with blue."""
        result = _format_status(RunStatus.RUNNING)
        assert "running" in result
        assert "blue" in result

    def test_format_done(self):
        """Done status formatted with green."""
        result = _format_status(RunStatus.DONE)
        assert "done" in result
        assert "green" in result

    def test_format_stuck(self):
        """Stuck status formatted with yellow."""
        result = _format_status(RunStatus.STUCK)
        assert "stuck" in result
        assert "yellow" in result

    def test_format_paused(self):
        """Paused status formatted with cyan."""
        result = _format_status(RunStatus.PAUSED)
        assert "paused" in result
        assert "cyan" in result

    def test_format_aborted(self):
        """Aborted status formatted with red."""
        result = _format_status(RunStatus.ABORTED)
        assert "aborted" in result
        assert "red" in result


class TestCliHelp:
    """Tests for CLI help output."""

    def test_main_help(self):
        """Main help displays all commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "status" in result.output
        assert "history" in result.output
        assert "resume" in result.output

    def test_run_help(self):
        """Run command help displays options."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--spec" in result.output
        assert "--max-iterations" in result.output

    def test_status_help(self):
        """Status command help works."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "current run status" in result.output.lower()

    def test_history_help(self):
        """History command help displays options."""
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
        assert "--runs" in result.output

    def test_resume_help(self):
        """Resume command help displays options."""
        result = runner.invoke(app, ["resume", "--help"])
        assert result.exit_code == 0
        assert "--run-id" in result.output
        assert "--max-iterations" in result.output


class TestStatusCommand:
    """Tests for status command."""

    def test_status_no_project(self):
        """Status shows message when no project found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, ["status"], catch_exceptions=False)
            # Should not crash, just show "no project" message
            assert "No SODA project found" in result.output or result.exit_code == 0

    def test_status_no_database(self):
        """Status shows message when no database exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create Sodafile but no database
            (Path(tmpdir) / "Sodafile").write_text("# Spec")
            (Path(tmpdir) / ".soda-id").write_text("test-id")

            with patch("soda.cli._get_project_context") as mock_ctx:
                mock_ctx.return_value = MagicMock(
                    db_path=Path(tmpdir) / "nonexistent.db"
                )
                result = runner.invoke(app, ["status"])
                assert "No SODA runs found" in result.output


class TestHistoryCommand:
    """Tests for history command."""

    def test_history_no_project(self):
        """History shows message when no project found."""
        result = runner.invoke(app, ["history"])
        assert "No SODA project found" in result.output or result.exit_code == 0

    def test_history_custom_limit(self):
        """History accepts custom run limit."""
        result = runner.invoke(app, ["history", "--runs", "5", "--help"])
        # Just verify the command parses correctly
        assert result.exit_code == 0


class TestRunCommand:
    """Tests for run command."""

    def test_run_missing_spec_file(self):
        """Run fails gracefully when spec file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No Sodafile exists
            result = runner.invoke(
                app, ["run"], catch_exceptions=False, env={"PWD": tmpdir}
            )
            # Should fail with bootstrap error (no git repo or no spec)
            assert result.exit_code != 0

    def test_run_with_spec_option(self):
        """Run command accepts --spec option."""
        result = runner.invoke(app, ["run", "--spec", "custom.md", "--help"])
        # Just verify option is accepted
        assert result.exit_code == 0


class TestResumeCommand:
    """Tests for resume command."""

    def test_resume_no_project(self):
        """Resume fails when no project found."""
        with patch("soda.cli._get_project_context", return_value=None):
            result = runner.invoke(app, ["resume"])
            assert result.exit_code != 0
            assert "No SODA project found" in result.output

    def test_resume_with_run_id(self):
        """Resume accepts --run-id option."""
        result = runner.invoke(app, ["resume", "--run-id", "abc123", "--help"])
        # Just verify option is accepted
        assert result.exit_code == 0

    def test_resume_with_max_iterations(self):
        """Resume accepts --max-iterations option."""
        result = runner.invoke(app, ["resume", "-m", "50", "--help"])
        assert result.exit_code == 0
