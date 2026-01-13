"""Project identification and path management for Ralph.

Handles the .ralph-id file in project roots and computes paths to
~/.ralph/projects/<uuid>/ for state storage.
"""

import uuid
from pathlib import Path
from typing import Optional


RALPH_ID_FILENAME = ".ralph-id"
RALPH_HOME = Path.home() / ".ralph"
RALPH_PROJECTS_DIR = RALPH_HOME / "projects"


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the project root by looking for a Ralphfile.

    Walks up from start_path (or cwd) until it finds a Ralphfile.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to project root, or None if no Ralphfile found
    """
    current = Path(start_path or Path.cwd()).resolve()

    while current != current.parent:
        if (current / "Ralphfile").exists():
            return current
        current = current.parent

    # Check root directory too
    if (current / "Ralphfile").exists():
        return current

    return None


def get_project_id(project_root: Path) -> str:
    """
    Get or create the project ID from .ralph-id file.

    If .ralph-id exists, reads and returns its contents.
    If not, generates a new UUID v4, writes it, and returns it.

    Args:
        project_root: Path to the project root directory

    Returns:
        The project's UUID string
    """
    ralph_id_path = project_root / RALPH_ID_FILENAME

    if ralph_id_path.exists():
        project_id = ralph_id_path.read_text().strip()
        if project_id:
            return project_id

    # Generate new UUID
    project_id = str(uuid.uuid4())
    ralph_id_path.write_text(project_id + "\n")

    return project_id


def get_project_state_dir(project_id: str) -> Path:
    """
    Get the state directory for a project.

    Creates ~/.ralph/projects/<uuid>/ if it doesn't exist.

    Args:
        project_id: The project's UUID

    Returns:
        Path to the project's state directory
    """
    state_dir = RALPH_PROJECTS_DIR / project_id
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_project_db_path(project_id: str) -> Path:
    """
    Get the database path for a project.

    Args:
        project_id: The project's UUID

    Returns:
        Path to ralph.db for this project
    """
    return get_project_state_dir(project_id) / "ralph.db"


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


def ensure_ralph_id_in_gitignore(project_root: Path) -> bool:
    """
    Ensure .ralph-id is in the project's .gitignore.

    Args:
        project_root: Path to the project root directory

    Returns:
        True if .ralph-id was added, False if it was already present
    """
    gitignore_path = project_root / ".gitignore"
    ralph_id_entry = RALPH_ID_FILENAME

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        lines = content.splitlines()
    else:
        content = ""
        lines = []

    if ralph_id_entry in lines:
        return False

    # Add .ralph-id to gitignore
    if content and not content.endswith('\n'):
        content += '\n'
    content += ralph_id_entry + '\n'
    gitignore_path.write_text(content)

    return True


class ProjectContext:
    """
    Encapsulates all project-related paths and IDs.

    Use this to get consistent paths throughout Ralph.
    """

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize project context.

        Args:
            project_root: Path to project root (will search for Ralphfile if None)

        Raises:
            ValueError: If no project root found (no Ralphfile)
        """
        if project_root is None:
            project_root = find_project_root()

        if project_root is None:
            raise ValueError("No Ralphfile found in current directory or parents")

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
    def ralphfile_path(self) -> Path:
        """Path to the Ralphfile."""
        return self.project_root / "Ralphfile"

    @property
    def ralph_id_path(self) -> Path:
        """Path to the .ralph-id file."""
        return self.project_root / RALPH_ID_FILENAME
