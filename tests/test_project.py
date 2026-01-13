"""Tests for project identification and path management."""

import os
import uuid
from pathlib import Path
import pytest

from ralph.project import (
    RALPH_ID_FILENAME,
    RALPH_HOME,
    RALPH_PROJECTS_DIR,
    find_project_root,
    get_project_id,
    get_project_state_dir,
    get_project_db_path,
    get_project_outputs_dir,
    get_project_summaries_dir,
    ensure_ralph_id_in_gitignore,
    ProjectContext,
)


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_finds_ralphfile_in_current_dir(self, tmp_path):
        """Test that project root is found when Ralphfile is in current dir."""
        (tmp_path / "Ralphfile").write_text("# spec")

        result = find_project_root(tmp_path)

        assert result == tmp_path

    def test_finds_ralphfile_in_parent_dir(self, tmp_path):
        """Test that project root is found when Ralphfile is in parent dir."""
        (tmp_path / "Ralphfile").write_text("# spec")
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)

        result = find_project_root(subdir)

        assert result == tmp_path

    def test_returns_none_when_no_ralphfile(self, tmp_path):
        """Test that None is returned when no Ralphfile exists."""
        result = find_project_root(tmp_path)

        assert result is None

    def test_uses_cwd_when_no_start_path(self, tmp_path):
        """Test that cwd is used when no start_path is provided."""
        (tmp_path / "Ralphfile").write_text("# spec")
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_project_root()
            assert result == tmp_path
        finally:
            os.chdir(original_dir)


class TestGetProjectId:
    """Tests for get_project_id function."""

    def test_creates_ralph_id_file_when_missing(self, tmp_path):
        """Test that .ralph-id file is created when it doesn't exist."""
        ralph_id_path = tmp_path / RALPH_ID_FILENAME

        project_id = get_project_id(tmp_path)

        assert ralph_id_path.exists()
        assert ralph_id_path.read_text().strip() == project_id

    def test_returns_valid_uuid(self, tmp_path):
        """Test that the generated ID is a valid UUID."""
        project_id = get_project_id(tmp_path)

        # Should not raise
        uuid.UUID(project_id)

    def test_reads_existing_ralph_id(self, tmp_path):
        """Test that existing .ralph-id is read and returned."""
        ralph_id_path = tmp_path / RALPH_ID_FILENAME
        existing_id = "existing-test-id-12345"
        ralph_id_path.write_text(existing_id + "\n")

        project_id = get_project_id(tmp_path)

        assert project_id == existing_id

    def test_regenerates_if_file_empty(self, tmp_path):
        """Test that ID is regenerated if file exists but is empty."""
        ralph_id_path = tmp_path / RALPH_ID_FILENAME
        ralph_id_path.write_text("")

        project_id = get_project_id(tmp_path)

        assert project_id  # Should have generated a new one
        uuid.UUID(project_id)  # Should be valid UUID


class TestPathFunctions:
    """Tests for path computation functions."""

    def test_get_project_state_dir_creates_directory(self, tmp_path, monkeypatch):
        """Test that state directory is created."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        state_dir = get_project_state_dir("test-uuid")

        assert state_dir.exists()
        assert state_dir == tmp_path / "projects" / "test-uuid"

    def test_get_project_db_path(self, tmp_path, monkeypatch):
        """Test database path computation."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        db_path = get_project_db_path("test-uuid")

        assert db_path == tmp_path / "projects" / "test-uuid" / "ralph.db"

    def test_get_project_outputs_dir_creates_directory(self, tmp_path, monkeypatch):
        """Test that outputs directory is created."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        outputs_dir = get_project_outputs_dir("test-uuid")

        assert outputs_dir.exists()
        assert outputs_dir == tmp_path / "projects" / "test-uuid" / "outputs"

    def test_get_project_summaries_dir_creates_directory(self, tmp_path, monkeypatch):
        """Test that summaries directory is created."""
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / "projects")

        summaries_dir = get_project_summaries_dir("test-uuid")

        assert summaries_dir.exists()
        assert summaries_dir == tmp_path / "projects" / "test-uuid" / "summaries"


class TestEnsureRalphIdInGitignore:
    """Tests for ensure_ralph_id_in_gitignore function."""

    def test_creates_gitignore_with_ralph_id(self, tmp_path):
        """Test that .gitignore is created with .ralph-id if it doesn't exist."""
        result = ensure_ralph_id_in_gitignore(tmp_path)

        assert result is True
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert RALPH_ID_FILENAME in gitignore.read_text()

    def test_adds_to_existing_gitignore(self, tmp_path):
        """Test that .ralph-id is added to existing .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")

        result = ensure_ralph_id_in_gitignore(tmp_path)

        assert result is True
        content = gitignore.read_text()
        assert RALPH_ID_FILENAME in content
        assert "*.pyc" in content

    def test_returns_false_when_already_present(self, tmp_path):
        """Test that False is returned when .ralph-id is already in .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(f"*.pyc\n{RALPH_ID_FILENAME}\n")

        result = ensure_ralph_id_in_gitignore(tmp_path)

        assert result is False


class TestProjectContext:
    """Tests for ProjectContext class."""

    def test_initializes_with_project_root(self, tmp_path, monkeypatch):
        """Test that ProjectContext initializes with given project root."""
        (tmp_path / "Ralphfile").write_text("# spec")
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / ".ralph-test" / "projects")

        ctx = ProjectContext(tmp_path)

        assert ctx.project_root == tmp_path
        assert ctx.project_id  # Should have generated an ID
        assert ctx.state_dir.exists()

    def test_finds_project_root_when_not_provided(self, tmp_path, monkeypatch):
        """Test that ProjectContext finds project root via Ralphfile."""
        (tmp_path / "Ralphfile").write_text("# spec")
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", tmp_path / ".ralph-test" / "projects")
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = ProjectContext()
            assert ctx.project_root == tmp_path
        finally:
            os.chdir(original_dir)

    def test_raises_when_no_ralphfile(self, tmp_path):
        """Test that ValueError is raised when no Ralphfile found."""
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(ValueError, match="No Ralphfile found"):
                ProjectContext()
        finally:
            os.chdir(original_dir)

    def test_path_properties(self, tmp_path, monkeypatch):
        """Test that path properties return correct values."""
        (tmp_path / "Ralphfile").write_text("# spec")
        test_projects_dir = tmp_path / ".ralph-test" / "projects"
        monkeypatch.setattr("ralph.project.RALPH_PROJECTS_DIR", test_projects_dir)

        ctx = ProjectContext(tmp_path)

        assert ctx.db_path == test_projects_dir / ctx.project_id / "ralph.db"
        assert ctx.outputs_dir == test_projects_dir / ctx.project_id / "outputs"
        assert ctx.summaries_dir == test_projects_dir / ctx.project_id / "summaries"
        assert ctx.ralphfile_path == tmp_path / "Ralphfile"
        assert ctx.ralph_id_path == tmp_path / RALPH_ID_FILENAME
