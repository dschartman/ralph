"""Tests for OutputCapture module.

These tests verify the output capture functionality that saves agent outputs
to JSONL files in the outputs/ directory.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestOutputCaptureBasics:
    """Test basic OutputCapture functionality."""

    def test_import_output_capture(self):
        """WHEN importing OutputCapture THEN it should succeed."""
        from soda.outputs import OutputCapture
        assert OutputCapture is not None

    def test_output_capture_is_class(self):
        """WHEN importing OutputCapture THEN it should be a class."""
        from soda.outputs import OutputCapture
        assert isinstance(OutputCapture, type)

    def test_output_capture_has_capture_method(self):
        """WHEN creating OutputCapture instance THEN it has capture method."""
        from soda.outputs import OutputCapture
        capture = OutputCapture()
        assert hasattr(capture, 'capture')
        assert callable(capture.capture)


class TestOutputCaptureDirectory:
    """Test output directory handling."""

    def test_creates_directory_if_not_exists(self):
        """WHEN capture() called THEN outputs directory is created if needed."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            # Directory shouldn't exist yet
            assert not outputs_dir.exists()

            # Capture something
            capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            # Directory should now exist
            assert outputs_dir.exists()

    def test_uses_default_outputs_directory(self):
        """WHEN OutputCapture created without args THEN uses 'outputs/' as default."""
        from soda.outputs import OutputCapture
        capture = OutputCapture()
        assert capture.output_dir == Path("outputs")


class TestOutputCaptureFileFormat:
    """Test JSONL file format and content."""

    def test_capture_creates_jsonl_file(self):
        """WHEN capture() called THEN creates/appends to JSONL file."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            # Find the JSONL file
            jsonl_files = list(outputs_dir.glob("*.jsonl"))
            assert len(jsonl_files) == 1

    def test_capture_writes_valid_json_lines(self):
        """WHEN capture() called THEN each line is valid JSON."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                for line in f:
                    # Should not raise
                    json.loads(line)

    def test_capture_includes_timestamp(self):
        """WHEN capture() called THEN record includes ISO timestamp."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())

            assert "timestamp" in record
            # Should be ISO format
            datetime.fromisoformat(record["timestamp"])

    def test_capture_includes_agent_type(self):
        """WHEN capture() called THEN record includes agent_type."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="walked",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())

            assert record["agent_type"] == "walked"

    def test_capture_includes_prompt_summary(self):
        """WHEN capture() called THEN record includes prompt_summary."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="narrow",
                prompt_summary="This is my test prompt summary",
                output={"result": "success"}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())

            assert record["prompt_summary"] == "This is my test prompt summary"

    def test_capture_includes_output(self):
        """WHEN capture() called THEN record includes the output."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            test_output = {"result": "success", "score": 95}
            capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output=test_output
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())

            assert record["output"] == test_output


class TestOutputCaptureAppend:
    """Test that capture appends to existing files."""

    def test_capture_appends_to_file(self):
        """WHEN capture() called multiple times THEN appends to same file."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            # Capture multiple outputs
            capture.capture(
                agent_type="narrow",
                prompt_summary="First prompt",
                output={"id": 1}
            )
            capture.capture(
                agent_type="walked",
                prompt_summary="Second prompt",
                output={"id": 2}
            )
            capture.capture(
                agent_type="bookended",
                prompt_summary="Third prompt",
                output={"id": 3}
            )

            # Should still be one file
            jsonl_files = list(outputs_dir.glob("*.jsonl"))
            assert len(jsonl_files) == 1

            # Should have 3 lines
            jsonl_file = jsonl_files[0]
            with open(jsonl_file) as f:
                lines = f.readlines()

            assert len(lines) == 3

            # Verify order
            records = [json.loads(line) for line in lines]
            assert records[0]["output"]["id"] == 1
            assert records[1]["output"]["id"] == 2
            assert records[2]["output"]["id"] == 3


class TestOutputCaptureNonBlocking:
    """Test that capture is non-blocking and swallows errors."""

    def test_capture_returns_none(self):
        """WHEN capture() called THEN it returns None."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            result = capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output={"result": "success"}
            )

            assert result is None

    def test_capture_swallows_write_errors(self):
        """WHEN file write fails THEN no exception is raised."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            # Mock open to raise an error
            with patch('builtins.open', side_effect=PermissionError("Cannot write")):
                # Should not raise
                result = capture.capture(
                    agent_type="narrow",
                    prompt_summary="Test prompt",
                    output={"result": "success"}
                )

            assert result is None

    def test_capture_swallows_json_errors(self):
        """WHEN JSON serialization fails THEN no exception is raised."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            # Create an object that can't be JSON serialized
            class NonSerializable:
                pass

            # Should not raise
            result = capture.capture(
                agent_type="narrow",
                prompt_summary="Test prompt",
                output=NonSerializable()
            )

            assert result is None

    def test_capture_swallows_directory_creation_errors(self):
        """WHEN directory creation fails THEN no exception is raised."""
        from soda.outputs import OutputCapture

        # Use a path that will fail to create
        capture = OutputCapture(output_dir=Path("/nonexistent/deeply/nested/path/outputs"))

        # Should not raise
        result = capture.capture(
            agent_type="narrow",
            prompt_summary="Test prompt",
            output={"result": "success"}
        )

        assert result is None


class TestOutputCaptureAgentTypes:
    """Test that all agent types are supported."""

    def test_narrow_agent_type(self):
        """WHEN agent_type='narrow' THEN capture succeeds."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="narrow",
                prompt_summary="Test",
                output={}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())
            assert record["agent_type"] == "narrow"

    def test_walked_agent_type(self):
        """WHEN agent_type='walked' THEN capture succeeds."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="walked",
                prompt_summary="Test",
                output={}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())
            assert record["agent_type"] == "walked"

    def test_bookended_agent_type(self):
        """WHEN agent_type='bookended' THEN capture succeeds."""
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir) / "outputs"
            capture = OutputCapture(output_dir=outputs_dir)

            capture.capture(
                agent_type="bookended",
                prompt_summary="Test",
                output={}
            )

            jsonl_file = list(outputs_dir.glob("*.jsonl"))[0]
            with open(jsonl_file) as f:
                record = json.loads(f.readline())
            assert record["agent_type"] == "bookended"
