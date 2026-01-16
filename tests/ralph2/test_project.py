"""Unit tests for project.py - Project identification and path management."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import uuid

from ralph2.project import (
    RALPH2_ID_FILENAME,
    RALPH2_HOME,
    RALPH2_PROJECTS_DIR,
    find_project_root,
    get_project_id,
    get_project_state_dir,
    get_project_db_path,
    get_project_outputs_dir,
    get_project_summaries_dir,
    get_memory_path,
    read_memory,
    write_memory,
    ensure_ralph2_id_in_gitignore,
    ProjectContext,
)


class TestConstants:
    """Tests for module constants."""

    def test_ralph2_id_filename(self):
        """Test RALPH2_ID_FILENAME constant."""
        assert RALPH2_ID_FILENAME == ".ralph2-id"

    def test_ralph2_home_is_under_home_dir(self):
        """Test RALPH2_HOME points to user's home/.ralph2."""
        assert RALPH2_HOME == Path.home() / ".ralph2"

    def test_ralph2_projects_dir(self):
        """Test RALPH2_PROJECTS_DIR points to ~/.ralph2/projects."""
        assert RALPH2_PROJECTS_DIR == RALPH2_HOME / "projects"


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_project_root_with_ralph2file_in_current_dir(self):
        """Test finding project root when Ralph2file is in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            (project_root / "Ralph2file").write_text("# Test Spec")

            result = find_project_root(project_root)

            assert result.resolve() == project_root.resolve()

    def test_find_project_root_in_parent_directory(self):
        """Test finding project root in parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            (project_root / "Ralph2file").write_text("# Test Spec")

            # Create nested directory
            nested = project_root / "src" / "components"
            nested.mkdir(parents=True)

            result = find_project_root(nested)

            assert result.resolve() == project_root.resolve()

    def test_find_project_root_returns_none_when_not_found(self):
        """Test returns None when no Ralph2file found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir)

            result = find_project_root(empty_dir)

            assert result is None

    def test_find_project_root_uses_cwd_when_no_start_path(self):
        """Test uses current working directory when no start path provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            (project_root / "Ralph2file").write_text("# Test Spec")

            with patch('pathlib.Path.cwd', return_value=project_root):
                result = find_project_root()

                assert result.resolve() == project_root.resolve()


class TestGetProjectId:
    """Tests for get_project_id function."""

    def test_get_project_id_creates_new_id(self):
        """Test creating new project ID when none exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            project_id = get_project_id(project_root)

            # Should be a valid UUID format
            try:
                uuid.UUID(project_id)
            except ValueError:
                pytest.fail(f"Invalid UUID format: {project_id}")

            # Should write the ID to file
            id_file = project_root / RALPH2_ID_FILENAME
            assert id_file.exists()
            assert id_file.read_text().strip() == project_id

    def test_get_project_id_reads_existing_id(self):
        """Test reading existing project ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            expected_id = "existing-uuid-12345"
            (project_root / RALPH2_ID_FILENAME).write_text(expected_id + "\n")

            project_id = get_project_id(project_root)

            assert project_id == expected_id

    def test_get_project_id_regenerates_if_empty(self):
        """Test regenerating ID if file is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / RALPH2_ID_FILENAME).write_text("")

            project_id = get_project_id(project_root)

            # Should have generated a new valid UUID
            try:
                uuid.UUID(project_id)
            except ValueError:
                pytest.fail(f"Invalid UUID format: {project_id}")


class TestGetProjectStateDir:
    """Tests for get_project_state_dir function."""

    def test_get_project_state_dir_creates_directory(self):
        """Test that state directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock RALPH2_PROJECTS_DIR to be in temp directory
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-123"
                state_dir = get_project_state_dir(project_id)

                assert state_dir == mock_projects_dir / project_id
                assert state_dir.exists()

    def test_get_project_state_dir_is_idempotent(self):
        """Test that calling multiple times returns same path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-456"
                state_dir1 = get_project_state_dir(project_id)
                state_dir2 = get_project_state_dir(project_id)

                assert state_dir1 == state_dir2


class TestGetProjectDbPath:
    """Tests for get_project_db_path function."""

    def test_get_project_db_path_returns_correct_path(self):
        """Test correct database path is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-789"
                db_path = get_project_db_path(project_id)

                assert db_path == mock_projects_dir / project_id / "ralph2.db"


class TestGetProjectOutputsDir:
    """Tests for get_project_outputs_dir function."""

    def test_get_project_outputs_dir_creates_directory(self):
        """Test that outputs directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-outputs"
                outputs_dir = get_project_outputs_dir(project_id)

                assert outputs_dir == mock_projects_dir / project_id / "outputs"
                assert outputs_dir.exists()


class TestGetProjectSummariesDir:
    """Tests for get_project_summaries_dir function."""

    def test_get_project_summaries_dir_creates_directory(self):
        """Test that summaries directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-summaries"
                summaries_dir = get_project_summaries_dir(project_id)

                assert summaries_dir == mock_projects_dir / project_id / "summaries"
                assert summaries_dir.exists()


class TestGetMemoryPath:
    """Tests for get_memory_path function."""

    def test_get_memory_path_returns_correct_path(self):
        """Test correct memory file path is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-memory"
                memory_path = get_memory_path(project_id)

                assert memory_path == mock_projects_dir / project_id / "memory.md"


class TestReadWriteMemory:
    """Tests for read_memory and write_memory functions."""

    def test_read_memory_returns_empty_string_when_no_file(self):
        """Test reading memory returns empty string when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-no-memory"
                # Create state dir but not memory file
                (mock_projects_dir / project_id).mkdir(parents=True)

                content = read_memory(project_id)

                assert content == ""

    def test_read_memory_returns_file_content(self):
        """Test reading memory returns file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-with-memory"
                state_dir = mock_projects_dir / project_id
                state_dir.mkdir(parents=True)
                (state_dir / "memory.md").write_text("# Memory Content\nSome notes.")

                content = read_memory(project_id)

                assert "# Memory Content" in content
                assert "Some notes." in content

    def test_write_memory_creates_file(self):
        """Test writing memory creates file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-write-memory"

                write_memory(project_id, "# New Memory\nNew content.")

                memory_path = mock_projects_dir / project_id / "memory.md"
                assert memory_path.exists()
                assert "# New Memory" in memory_path.read_text()

    def test_write_memory_overwrites_existing(self):
        """Test writing memory overwrites existing content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_projects_dir = Path(tmpdir) / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                project_id = "test-uuid-overwrite"
                state_dir = mock_projects_dir / project_id
                state_dir.mkdir(parents=True)
                (state_dir / "memory.md").write_text("Old content")

                write_memory(project_id, "New content")

                assert read_memory(project_id) == "New content"


class TestEnsureRalph2IdInGitignore:
    """Tests for ensure_ralph2_id_in_gitignore function."""

    def test_adds_to_empty_gitignore(self):
        """Test adding .ralph2-id to empty gitignore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gitignore = project_root / ".gitignore"
            gitignore.write_text("")

            result = ensure_ralph2_id_in_gitignore(project_root)

            assert result is True
            assert RALPH2_ID_FILENAME in gitignore.read_text()

    def test_adds_to_nonexistent_gitignore(self):
        """Test adding .ralph2-id when gitignore doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = ensure_ralph2_id_in_gitignore(project_root)

            assert result is True
            gitignore = project_root / ".gitignore"
            assert gitignore.exists()
            assert RALPH2_ID_FILENAME in gitignore.read_text()

    def test_does_not_duplicate(self):
        """Test doesn't add duplicate .ralph2-id entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gitignore = project_root / ".gitignore"
            gitignore.write_text(f"{RALPH2_ID_FILENAME}\nother_ignore\n")

            result = ensure_ralph2_id_in_gitignore(project_root)

            assert result is False
            # Should not have duplicated the entry
            content = gitignore.read_text()
            assert content.count(RALPH2_ID_FILENAME) == 1

    def test_appends_newline_if_needed(self):
        """Test appends newline before adding entry if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gitignore = project_root / ".gitignore"
            gitignore.write_text("*.log")  # No trailing newline

            ensure_ralph2_id_in_gitignore(project_root)

            content = gitignore.read_text()
            # Should have newline before .ralph2-id
            assert "*.log\n.ralph2-id" in content


class TestProjectContext:
    """Tests for ProjectContext class."""

    def test_init_with_explicit_project_root(self):
        """Test initializing with explicit project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                assert ctx.project_root == project_root
                assert ctx.project_id is not None
                assert ctx.state_dir.exists()

    def test_init_searches_for_ralph2file(self):
        """Test initialization searches for Ralph2file if no root provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                with patch('ralph2.project.find_project_root', return_value=project_root):
                    ctx = ProjectContext()

                    assert ctx.project_root == project_root

    def test_init_raises_if_no_ralph2file(self):
        """Test initialization raises ValueError if no Ralph2file found."""
        with patch('ralph2.project.find_project_root', return_value=None):
            with pytest.raises(ValueError) as exc_info:
                ProjectContext()

            assert "No Ralph2file found" in str(exc_info.value)

    def test_db_path_property(self):
        """Test db_path property returns correct path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                assert ctx.db_path == ctx.state_dir / "ralph2.db"

    def test_outputs_dir_property(self):
        """Test outputs_dir property returns correct path and creates it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                outputs_dir = ctx.outputs_dir

                assert outputs_dir == ctx.state_dir / "outputs"
                assert outputs_dir.exists()

    def test_summaries_dir_property(self):
        """Test summaries_dir property returns correct path and creates it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                summaries_dir = ctx.summaries_dir

                assert summaries_dir == ctx.state_dir / "summaries"
                assert summaries_dir.exists()

    def test_ralph2file_path_property(self):
        """Test ralph2file_path property returns correct path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                assert ctx.ralph2file_path == project_root / "Ralph2file"

    def test_ralph2_id_path_property(self):
        """Test ralph2_id_path property returns correct path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Ralph2file").write_text("# Test Spec")
            mock_projects_dir = Path(tmpdir) / ".ralph2" / "projects"

            with patch('ralph2.project.RALPH2_PROJECTS_DIR', mock_projects_dir):
                ctx = ProjectContext(project_root)

                assert ctx.ralph2_id_path == project_root / RALPH2_ID_FILENAME
