"""Tests for project memory management."""

import pytest
from pathlib import Path

from ralph.project import (
    get_memory_path,
    read_memory,
    write_memory,
)


class TestGetMemoryPath:
    """Tests for get_memory_path function."""

    def test_returns_correct_path(self, tmp_path, monkeypatch):
        """Test that memory path is computed correctly."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        memory_path = get_memory_path("test-uuid")

        assert memory_path == tmp_path / "projects" / "test-uuid" / "memory.md"


class TestReadMemory:
    """Tests for read_memory function."""

    def test_returns_empty_string_when_file_missing(self, tmp_path, monkeypatch):
        """Test that empty string is returned when memory file doesn't exist."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        result = read_memory("test-uuid")

        assert result == ""

    def test_reads_existing_memory_file(self, tmp_path, monkeypatch):
        """Test that memory content is read when file exists."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        # Create the memory file
        memory_dir = tmp_path / "projects" / "test-uuid"
        memory_dir.mkdir(parents=True)
        memory_file = memory_dir / "memory.md"
        test_content = "# Project Memory\n\n- Use UV for packages\n- Tests live in tests/\n"
        memory_file.write_text(test_content)

        result = read_memory("test-uuid")

        assert result == test_content


class TestWriteMemory:
    """Tests for write_memory function."""

    def test_creates_directory_and_writes_file(self, tmp_path, monkeypatch):
        """Test that directory is created and memory is written."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")
        test_content = "# Project Memory\n\n- New insight\n"

        write_memory("test-uuid", test_content)

        memory_file = tmp_path / "projects" / "test-uuid" / "memory.md"
        assert memory_file.exists()
        assert memory_file.read_text() == test_content

    def test_overwrites_existing_memory(self, tmp_path, monkeypatch):
        """Test that existing memory file is overwritten."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        # Create existing memory file
        memory_dir = tmp_path / "projects" / "test-uuid"
        memory_dir.mkdir(parents=True)
        memory_file = memory_dir / "memory.md"
        memory_file.write_text("# Old content\n")

        # Write new content
        new_content = "# Project Memory\n\n- Updated insight\n"
        write_memory("test-uuid", new_content)

        assert memory_file.read_text() == new_content
