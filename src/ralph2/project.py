"""Project identification and path management for Ralph2.

Handles the .ralph2-id file in project roots and computes paths to
~/.ralph2/projects/<uuid>/ for state storage.
"""

import uuid
from pathlib import Path
from typing import Optional


RALPH2_ID_FILENAME = ".ralph2-id"
RALPH2_HOME = Path.home() / ".ralph2"
RALPH2_PROJECTS_DIR = RALPH2_HOME / "projects"


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the project root by looking for a Ralph2file.

    Walks up from start_path (or cwd) until it finds a Ralph2file.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to project root, or None if no Ralph2file found
    """
    current = Path(start_path or Path.cwd()).resolve()

    while current != current.parent:
        if (current / "Ralph2file").exists():
            return current
        current = current.parent

    # Check root directory too
    if (current / "Ralph2file").exists():
        return current

    return None


def get_project_id(project_root: Path) -> str:
    """
    Get or create the project ID from .ralph2-id file.

    If .ralph2-id exists, reads and returns its contents.
    If not, generates a new UUID v4, writes it, and returns it.

    Args:
        project_root: Path to the project root directory

    Returns:
        The project's UUID string
    """
    temper_id_path = project_root / RALPH2_ID_FILENAME

    if temper_id_path.exists():
        project_id = temper_id_path.read_text().strip()
        if project_id:
            return project_id

    # Generate new UUID
    project_id = str(uuid.uuid4())
    temper_id_path.write_text(project_id + "\n")

    return project_id


def get_project_state_dir(project_id: str) -> Path:
    """
    Get the state directory for a project.

    Creates ~/.ralph2/projects/<uuid>/ if it doesn't exist.

    Args:
        project_id: The project's UUID

    Returns:
        Path to the project's state directory
    """
    state_dir = RALPH2_PROJECTS_DIR / project_id
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_project_db_path(project_id: str) -> Path:
    """
    Get the database path for a project.

    Args:
        project_id: The project's UUID

    Returns:
        Path to ralph2.db for this project
    """
    return get_project_state_dir(project_id) / "ralph2.db"


def get_project_outputs_dir(project_id: str) -> Path:
    """
    Get the outputs directory for a project.

    Creates the directory if it doesn't exist.

    Args:
        project_id: The project's UUID

    Returns:
        Path to outputs directory for this project
    """
    outputs_dir = get_project_state_dir(project_id) / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir


def get_project_summaries_dir(project_id: str) -> Path:
    """
    Get the summaries directory for a project.

    Creates the directory if it doesn't exist.

    Args:
        project_id: The project's UUID

    Returns:
        Path to summaries directory for this project
    """
    summaries_dir = get_project_state_dir(project_id) / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    return summaries_dir


def get_memory_path(project_id: str) -> Path:
    """
    Get the memory file path for a project.

    Args:
        project_id: The project's UUID

    Returns:
        Path to memory.md for this project
    """
    return get_project_state_dir(project_id) / "memory.md"


def read_memory(project_id: str) -> str:
    """
    Read the project memory file.

    If the file doesn't exist, returns an empty string.

    Args:
        project_id: The project's UUID

    Returns:
        The memory file content, or empty string if file doesn't exist
    """
    memory_path = get_memory_path(project_id)
    if not memory_path.exists():
        return ""
    return memory_path.read_text()


def write_memory(project_id: str, content: str) -> None:
    """
    Write content to the project memory file.

    Creates the directory if it doesn't exist. Overwrites existing content.

    Args:
        project_id: The project's UUID
        content: The memory content to write
    """
    memory_path = get_memory_path(project_id)
    # Ensure parent directory exists
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(content)


def ensure_ralph2_id_in_gitignore(project_root: Path) -> bool:
    """
    Ensure .ralph2-id is in the project's .gitignore.

    Args:
        project_root: Path to the project root directory

    Returns:
        True if .ralph2-id was added, False if it was already present
    """
    gitignore_path = project_root / ".gitignore"
    temper_id_entry = RALPH2_ID_FILENAME

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        lines = content.splitlines()
    else:
        content = ""
        lines = []

    if temper_id_entry in lines:
        return False

    # Add .ralph2-id to gitignore
    if content and not content.endswith('\n'):
        content += '\n'
    content += temper_id_entry + '\n'
    gitignore_path.write_text(content)

    return True


class ProjectContext:
    """
    Encapsulates all project-related paths and IDs.

    Use this to get consistent paths throughout Ralph2.
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize project context.

        Args:
            project_root: Path to project root (will search for Ralph2file if None)

        Raises:
            ValueError: If no project root found (no Ralph2file)
        """
        if project_root is None:
            project_root = find_project_root()

        if project_root is None:
            raise ValueError("No Ralph2file found in current directory or parents")

        self.project_root = project_root
        self.project_id = get_project_id(project_root)
        self.state_dir = get_project_state_dir(self.project_id)

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database."""
        return get_project_db_path(self.project_id)

    @property
    def outputs_dir(self) -> Path:
        """Path to the outputs directory."""
        return get_project_outputs_dir(self.project_id)

    @property
    def summaries_dir(self) -> Path:
        """Path to the summaries directory."""
        return get_project_summaries_dir(self.project_id)

    @property
    def ralph2file_path(self) -> Path:
        """Path to the Ralph2file."""
        return self.project_root / "Ralph2file"

    @property
    def ralph2_id_path(self) -> Path:
        """Path to the .ralph2-id file."""
        return self.project_root / RALPH2_ID_FILENAME
