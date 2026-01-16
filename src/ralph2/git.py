"""Git operations for Ralph2: Branch management with guaranteed cleanup.

This module provides the GitBranchManager class which encapsulates all git
worktree and branch operations with context manager support for guaranteed cleanup.
"""

import logging
import os
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class GitBranchManager:
    """Context manager for git worktree/branch lifecycle with guaranteed cleanup.

    This class manages the creation and cleanup of git worktrees and branches
    for isolated executor work. The worktree path includes run_id to prevent
    conflicts when multiple Ralph2 instances run in parallel.

    Usage:
        with GitBranchManager(work_item_id="ralph-abc123", run_id="run-xyz") as manager:
            # Do work in manager.worktree_path
            pass
        # Worktree and branch are automatically cleaned up

    Attributes:
        work_item_id: The work item ID (used in branch name)
        run_id: The run ID (used in worktree path for parallel execution isolation)
        worktree_path: Path to the worktree (set after __enter__)
    """

    def __init__(self, work_item_id: str, run_id: str, cwd: Optional[str] = None):
        """Initialize the GitBranchManager.

        Args:
            work_item_id: Work item ID (e.g., "ralph-abc123")
            run_id: Run ID (e.g., "ralph2-abc12345")
            cwd: Optional working directory. If not provided, uses os.getcwd()
        """
        self.work_item_id = work_item_id
        self.run_id = run_id
        self._cwd = cwd or os.getcwd()
        self._worktree_created = False
        self._worktree_path: Optional[str] = None
        self._branch_name = f"ralph2/{work_item_id}"

    @property
    def worktree_path(self) -> Optional[str]:
        """Get the worktree path (available after entering context)."""
        return self._worktree_path

    def get_worktree_path(self) -> str:
        """Calculate the worktree directory path.

        Returns:
            Absolute path to the worktree directory including run_id
        """
        # Create worktree in a sibling directory to the main repo
        # Include run_id to prevent conflicts between parallel runs
        parent_dir = os.path.dirname(self._cwd)
        worktree_path = os.path.join(
            parent_dir,
            f"ralph2-executor-{self.run_id}-{self.work_item_id}"
        )
        return worktree_path

    def _run_git(self, command: list[str]) -> subprocess.CompletedProcess:
        """Run a git command.

        Args:
            command: Git command as list of strings

        Returns:
            CompletedProcess result
        """
        return subprocess.run(command, capture_output=True, text=True, cwd=self._cwd)

    def __enter__(self) -> "GitBranchManager":
        """Create the git branch and worktree.

        Returns:
            self with worktree_path set

        Raises:
            RuntimeError: If branch or worktree creation fails
        """
        self._worktree_path = self.get_worktree_path()

        # Create the branch first (from current HEAD)
        result = self._run_git(["git", "branch", self._branch_name])
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create branch: {result.stderr}")

        # Create worktree for the branch
        branch_created = True
        try:
            result = self._run_git(["git", "worktree", "add", self._worktree_path, self._branch_name])
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create worktree: {result.stderr}")
            self._worktree_created = True
            return self
        except Exception as worktree_error:
            # Guaranteed cleanup: delete the branch if worktree creation failed
            if branch_created:
                cleanup_result = self._run_git(["git", "branch", "-D", self._branch_name])
                if cleanup_result.returncode != 0:
                    logger.warning(
                        f"Failed to cleanup branch '{self._branch_name}' after worktree creation failure: "
                        f"{cleanup_result.stderr}"
                    )
            raise

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Clean up the worktree and branch.

        This method guarantees cleanup regardless of whether an exception occurred.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised

        Returns:
            False (does not suppress exceptions)
        """
        if self._worktree_created and self._worktree_path:
            self._cleanup()
        return False  # Don't suppress exceptions

    def _cleanup(self) -> bool:
        """Remove the worktree and delete the feature branch.

        Logs warnings if cleanup operations fail but does not raise exceptions.

        Returns:
            True if all cleanup operations succeeded, False otherwise
        """
        worktree_removed = False
        branch_deleted = False

        # Remove the worktree
        try:
            result = self._run_git(["git", "worktree", "remove", self._worktree_path, "--force"])
            worktree_removed = result.returncode == 0
            if not worktree_removed:
                logger.warning(
                    f"Failed to remove worktree '{self._worktree_path}': {result.stderr}"
                )
        except Exception as e:
            logger.warning(f"Exception removing worktree '{self._worktree_path}': {e}")

        # Delete the branch (always attempt, even if worktree removal failed)
        try:
            result = self._run_git(["git", "branch", "-D", self._branch_name])
            branch_deleted = result.returncode == 0
            if not branch_deleted:
                logger.warning(
                    f"Failed to delete branch '{self._branch_name}': {result.stderr}"
                )
        except Exception as e:
            logger.warning(f"Exception deleting branch '{self._branch_name}': {e}")

        self._worktree_created = False
        return worktree_removed and branch_deleted

    def merge_to_main(self) -> Tuple[bool, str]:
        """Merge the feature branch to main.

        This should be called from the main repository (not the worktree).

        Returns:
            (success, error_message)
        """
        # Ensure we're on main branch
        result = self._run_git(["git", "checkout", "main"])
        if result.returncode != 0:
            return False, f"Failed to checkout main: {result.stderr}"

        # Merge feature branch
        result = self._run_git(["git", "merge", self._branch_name])
        if result.returncode != 0:
            return False, f"Merge conflict: {result.stderr}"

        return True, ""

    def check_merge_conflicts(self) -> Tuple[bool, str]:
        """Check if there are unresolved merge conflicts.

        Returns:
            (has_conflicts, conflict_info)
        """
        result = self._run_git(["git", "status", "--porcelain"])
        if result.returncode != 0:
            return True, "Failed to check git status"

        # Look for conflict markers (UU = both modified)
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        conflicts = [
            line for line in lines
            if line.startswith('UU ') or line.startswith('AA ') or line.startswith('DD ')
        ]

        if conflicts:
            conflict_files = [line[3:] for line in conflicts]
            return True, f"Conflicts in: {', '.join(conflict_files)}"

        return False, ""

    def cleanup(self) -> bool:
        """Manually cleanup the worktree and branch.

        This can be called explicitly if not using the context manager pattern.

        Returns:
            True if cleanup was successful
        """
        return self._cleanup()
