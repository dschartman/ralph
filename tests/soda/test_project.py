"""Tests for Soda project management (project.py)."""

import logging
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from soda import project


class TestConstants:
    """Test module constants."""

    def test_soda_id_filename(self):
        """SODA_ID_FILENAME should be .soda-id."""
        assert project.SODA_ID_FILENAME == ".soda-id"

    def test_soda_home(self):
        """SODA_HOME should be ~/.soda."""
        assert project.SODA_HOME == Path.home() / ".soda"

    def test_soda_projects_dir(self):
        """SODA_PROJECTS_DIR should be ~/.soda/projects."""
        assert project.SODA_PROJECTS_DIR == Path.home() / ".soda" / "projects"


class TestFindGitRoot:
    """Tests for find_git_root function."""

    def test_find_git_root_in_repo(self, tmp_path):
        """Returns git root when in a repository."""
        # Create a git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = str(tmp_path) + "\n"
            mock_run.return_value.returncode = 0

            result = project.find_git_root(tmp_path)
            assert result == tmp_path

    def test_find_git_root_not_in_repo(self, tmp_path):
        """Returns None when not in a repository."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            result = project.find_git_root(tmp_path)
            assert result is None


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_project_root_with_sodafile(self, tmp_path):
        """Returns directory containing Sodafile."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        result = project.find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_walks_up(self, tmp_path):
        """Walks up directories to find Sodafile."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)

        result = project.find_project_root(subdir)
        assert result == tmp_path

    def test_find_project_root_no_sodafile(self, tmp_path):
        """Returns None when no Sodafile found and require_spec=True."""
        result = project.find_project_root(tmp_path)
        assert result is None

    def test_find_project_root_falls_back_to_git(self, tmp_path):
        """Falls back to git root when require_spec=False."""
        with patch.object(project, "find_git_root") as mock_git:
            mock_git.return_value = tmp_path

            result = project.find_project_root(tmp_path, require_spec=False)
            assert result == tmp_path
            mock_git.assert_called_once()


class TestGetProjectId:
    """Tests for get_project_id function."""

    def test_creates_new_id_if_not_exists(self, tmp_path):
        """Creates a new UUID if .soda-id doesn't exist."""
        result = project.get_project_id(tmp_path)

        # Should be a valid UUID
        uuid.UUID(result)

        # Should have created .soda-id
        id_path = tmp_path / ".soda-id"
        assert id_path.exists()
        assert id_path.read_text().strip() == result

    def test_reads_existing_id(self, tmp_path):
        """Reads existing .soda-id file."""
        existing_id = str(uuid.uuid4())
        id_path = tmp_path / ".soda-id"
        id_path.write_text(existing_id + "\n")

        result = project.get_project_id(tmp_path)
        assert result == existing_id

    def test_handles_empty_file(self, tmp_path):
        """Creates new ID if .soda-id exists but is empty."""
        id_path = tmp_path / ".soda-id"
        id_path.write_text("")

        result = project.get_project_id(tmp_path)

        # Should be a valid UUID
        uuid.UUID(result)


class TestGetProjectStateDir:
    """Tests for get_project_state_dir function."""

    def test_creates_state_directory(self, tmp_path):
        """Creates the state directory structure."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            result = project.get_project_state_dir(project_id)

            assert result.exists()
            assert result == tmp_path / "projects" / project_id

    def test_returns_existing_directory(self, tmp_path):
        """Returns existing directory without error."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            state_dir = tmp_path / "projects" / project_id
            state_dir.mkdir(parents=True)

            result = project.get_project_state_dir(project_id)
            assert result == state_dir


class TestGetProjectDbPath:
    """Tests for get_project_db_path function."""

    def test_returns_db_path(self, tmp_path):
        """Returns path to soda.db in state directory."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            result = project.get_project_db_path(project_id)

            assert result == tmp_path / "projects" / project_id / "soda.db"


class TestMemoryPath:
    """Tests for get_memory_path function."""

    def test_returns_memory_path(self, tmp_path):
        """Returns path to memory.md in state directory."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            result = project.get_memory_path(project_id)

            assert result == tmp_path / "projects" / project_id / "memory.md"


class TestReadMemory:
    """Tests for read_memory function."""

    def test_returns_content_if_exists(self, tmp_path):
        """Returns memory content if file exists."""
        project_id = str(uuid.uuid4())
        memory_content = "# Project Memory\n\nSome notes here."

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            state_dir = tmp_path / "projects" / project_id
            state_dir.mkdir(parents=True)
            memory_path = state_dir / "memory.md"
            memory_path.write_text(memory_content)

            result = project.read_memory(project_id)
            assert result == memory_content

    def test_returns_empty_string_if_not_exists(self, tmp_path):
        """Returns empty string if memory.md doesn't exist."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            state_dir = tmp_path / "projects" / project_id
            state_dir.mkdir(parents=True)

            result = project.read_memory(project_id)
            assert result == ""


class TestWriteMemory:
    """Tests for write_memory function."""

    def test_writes_content(self, tmp_path):
        """Writes content to memory.md."""
        project_id = str(uuid.uuid4())
        content = "# Memory\n\nNew content."

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            project.write_memory(project_id, content)

            memory_path = tmp_path / "projects" / project_id / "memory.md"
            assert memory_path.exists()
            assert memory_path.read_text() == content

    def test_overwrites_existing_content(self, tmp_path):
        """Overwrites existing memory content."""
        project_id = str(uuid.uuid4())

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            state_dir = tmp_path / "projects" / project_id
            state_dir.mkdir(parents=True)
            memory_path = state_dir / "memory.md"
            memory_path.write_text("Old content")

            project.write_memory(project_id, "New content")

            assert memory_path.read_text() == "New content"

    def test_logs_warning_for_large_memory(self, tmp_path, caplog):
        """Logs warning when memory exceeds 50KB."""
        project_id = str(uuid.uuid4())
        # Create content larger than 50KB (50 * 1024 = 51200 bytes)
        large_content = "x" * 52000

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / "projects"):
            with caplog.at_level(logging.WARNING):
                project.write_memory(project_id, large_content)

            assert "memory" in caplog.text.lower()
            assert "50KB" in caplog.text or "50kb" in caplog.text.lower() or "51200" in caplog.text or "curation" in caplog.text.lower()


class TestEnsureSodaIdInGitignore:
    """Tests for ensure_soda_id_in_gitignore function."""

    def test_creates_gitignore_if_not_exists(self, tmp_path):
        """Creates .gitignore with .soda-id if it doesn't exist."""
        result = project.ensure_soda_id_in_gitignore(tmp_path)

        assert result is True
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".soda-id" in gitignore.read_text()

    def test_adds_to_existing_gitignore(self, tmp_path):
        """Adds .soda-id to existing .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")

        result = project.ensure_soda_id_in_gitignore(tmp_path)

        assert result is True
        content = gitignore.read_text()
        assert "*.pyc" in content
        assert ".soda-id" in content

    def test_does_not_duplicate(self, tmp_path):
        """Does not add .soda-id if already present."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".soda-id\n*.pyc\n")

        result = project.ensure_soda_id_in_gitignore(tmp_path)

        assert result is False
        lines = gitignore.read_text().splitlines()
        assert lines.count(".soda-id") == 1


class TestProjectContext:
    """Tests for ProjectContext class."""

    def test_initializes_with_project_root(self, tmp_path):
        """Initializes correctly with explicit project root."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.project_root == tmp_path
            # Project ID should be valid UUID
            uuid.UUID(ctx.project_id)
            assert ctx.state_dir.exists()

    def test_raises_if_no_project_root(self, tmp_path):
        """Raises ValueError if no project root found."""
        # tmp_path has no Sodafile
        with pytest.raises(ValueError, match="Sodafile"):
            project.ProjectContext(project_root=None, require_spec=True)

    def test_db_path_property(self, tmp_path):
        """db_path returns path to soda.db."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.db_path.name == "soda.db"
            assert ctx.db_path.parent == ctx.state_dir

    def test_outputs_dir_property(self, tmp_path):
        """outputs_dir returns path to outputs directory."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.outputs_dir.name == "outputs"
            assert ctx.outputs_dir.exists()

    def test_summaries_dir_property(self, tmp_path):
        """summaries_dir returns path to summaries directory."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.summaries_dir.name == "summaries"
            assert ctx.summaries_dir.exists()

    def test_sodafile_path_property(self, tmp_path):
        """sodafile_path returns path to Sodafile."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.sodafile_path == tmp_path / "Sodafile"

    def test_soda_id_path_property(self, tmp_path):
        """soda_id_path returns path to .soda-id."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.soda_id_path == tmp_path / ".soda-id"

    def test_memory_path_property(self, tmp_path):
        """memory_path returns path to memory.md."""
        sodafile = tmp_path / "Sodafile"
        sodafile.write_text("# Spec")

        with patch.object(project, "SODA_PROJECTS_DIR", tmp_path / ".soda" / "projects"):
            ctx = project.ProjectContext(tmp_path)

            assert ctx.memory_path.name == "memory.md"
            assert ctx.memory_path.parent == ctx.state_dir
