"""Project identification and path management for Soda.

Handles the .soda-id file in project roots and computes paths to
~/.soda/projects/<uuid>/ for state storage.
"""

import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SODA_ID_FILENAME = ".soda-id"
SODA_HOME = Path.home() / ".soda"
SODA_PROJECTS_DIR = SODA_HOME / "projects"

# Warning threshold for memory size (50KB)
MEMORY_SIZE_WARNING_THRESHOLD = 50 * 1024


def find_git_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the git repository root.

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to git root, or None if not in a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=start_path or Path.cwd()
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def find_project_root(start_path: Optional[Path] = None, require_spec: bool = True) -> Optional[Path]:
    """
    Find the project root by looking for a Sodafile or git root.

    Walks up from start_path (or cwd) until it finds a Sodafile.
    If require_spec is False, falls back to git root.

    Args:
        start_path: Starting directory (defaults to cwd)
        require_spec: If True, requires Sodafile; if False, can use git root

    Returns:
        Path to project root, or None if no Sodafile found (and require_spec=True)
    """
    current = Path(start_path or Path.cwd()).resolve()

    while current != current.parent:
        if (current / "Sodafile").exists():
            return current
        current = current.parent

    # Check root directory too
    if (current / "Sodafile").exists():
        return current

    # Fall back to git root if spec not required
    if not require_spec:
        return find_git_root(start_path)

    return None


def get_project_id(project_root: Path) -> str:
    """
    Get or create the project ID from .soda-id file.

    If .soda-id exists, reads and returns its contents.
    If not, generates a new UUID v4, writes it atomically, and returns it.

    Uses atomic file operations (write to temp, rename) to prevent file
    corruption if concurrent processes try to create the ID simultaneously.
    Also handles race conditions where multiple processes attempt creation
    simultaneously by re-reading after write failure.

    Args:
        project_root: Path to the project root directory

    Returns:
        The project's UUID string
    """
    id_path = project_root / SODA_ID_FILENAME

    if id_path.exists():
        project_id = id_path.read_text().strip()
        if project_id:
            return project_id

    # Generate new UUID
    project_id = str(uuid.uuid4())

    # Write atomically: create temp file in same directory, then rename
    # This ensures the file is either fully written or not at all
    fd, temp_path = tempfile.mkstemp(dir=project_root, prefix='.soda-id-')
    try:
        os.write(fd, (project_id + "\n").encode())
        os.close(fd)
        fd = None  # Mark as closed
        # Use link + unlink pattern for exclusive creation (atomic on POSIX)
        # If another process created the file first, link will fail
        try:
            os.link(temp_path, id_path)
            os.unlink(temp_path)
            # We won the race - return our ID
            return project_id
        except FileExistsError:
            # Another process won the race - read their ID
            os.unlink(temp_path)
            existing_id = id_path.read_text().strip()
            if existing_id:
                return existing_id
            # Edge case: file exists but empty, use replace as fallback
            os.replace(temp_path, id_path) if os.path.exists(temp_path) else None
            return project_id
        except OSError:
            # link() not supported (e.g., some filesystems), fall back to replace
            os.replace(temp_path, id_path)
            # Check if we actually won or someone beat us
            final_id = id_path.read_text().strip()
            return final_id if final_id else project_id
    except Exception:
        # Clean up temp file on error
        if fd is not None:
            os.close(fd)
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def get_project_state_dir(project_id: str) -> Path:
    """
    Get the state directory for a project.

    Creates ~/.soda/projects/<uuid>/ if it doesn't exist.

    Args:
        project_id: The project's UUID

    Returns:
        Path to the project's state directory
    """
    state_dir = SODA_PROJECTS_DIR / project_id
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_project_db_path(project_id: str) -> Path:
    """
    Get the database path for a project.

    Args:
        project_id: The project's UUID

    Returns:
        Path to soda.db for this project
    """
    return get_project_state_dir(project_id) / "soda.db"


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
    Logs a warning if the content exceeds 50KB (memory may need curation).

    Args:
        project_id: The project's UUID
        content: The memory content to write
    """
    memory_path = get_memory_path(project_id)
    # Ensure parent directory exists
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    # Check size and warn if too large
    content_size = len(content.encode('utf-8'))
    if content_size > MEMORY_SIZE_WARNING_THRESHOLD:
        logger.warning(
            f"Memory content exceeds 50KB ({content_size} bytes). "
            "Memory may need curation to stay effective."
        )

    memory_path.write_text(content)


def ensure_soda_id_in_gitignore(project_root: Path) -> bool:
    """
    Ensure .soda-id is in the project's .gitignore.

    Args:
        project_root: Path to the project root directory

    Returns:
        True if .soda-id was added, False if it was already present
    """
    gitignore_path = project_root / ".gitignore"
    id_entry = SODA_ID_FILENAME

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        lines = content.splitlines()
    else:
        content = ""
        lines = []

    if id_entry in lines:
        return False

    # Add .soda-id to gitignore
    if content and not content.endswith('\n'):
        content += '\n'
    content += id_entry + '\n'
    gitignore_path.write_text(content)

    return True


class ProjectContext:
    """
    Encapsulates all project-related paths and IDs.

    Use this to get consistent paths throughout Soda.
    """

    def __init__(self, project_root: Optional[Path] = None, require_spec: bool = True):
        """
        Initialize project context.

        Args:
            project_root: Path to project root (will search for Sodafile if None)
            require_spec: If True, requires Sodafile; if False, can use git root

        Raises:
            ValueError: If no project root found
        """
        if project_root is None:
            project_root = find_project_root(require_spec=require_spec)

        if project_root is None:
            if require_spec:
                raise ValueError("No Sodafile found in current directory or parents")
            else:
                raise ValueError("No git repository found in current directory or parents")

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
    def sodafile_path(self) -> Path:
        """Path to the Sodafile."""
        return self.project_root / "Sodafile"

    @property
    def soda_id_path(self) -> Path:
        """Path to the .soda-id file."""
        return self.project_root / SODA_ID_FILENAME

    @property
    def memory_path(self) -> Path:
        """Path to the memory.md file."""
        return get_memory_path(self.project_id)
