"""Git operations for Ralph2: Branch management with guaranteed cleanup.

This module provides the GitBranchManager class which encapsulates all git
worktree and branch operations with context manager support for guaranteed cleanup.
"""

import logging
import os
import subprocess
import sys
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _warn(message: str) -> None:
    """Print warning to stderr AND log it.

    Cleanup failures need to be highly visible to users, not silently discarded.
    We use both print (always visible) and logging (for structured logging if configured).
    """
    print(f"\033[33m⚠️  {message}\033[0m", file=sys.stderr)
    logger.warning(message)


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

    def __init__(
        self,
        work_item_id: str,
        run_id: str,
        cwd: Optional[str] = None,
        base_branch: Optional[str] = None
    ):
        """Initialize the GitBranchManager.

        Args:
            work_item_id: Work item ID (e.g., "ralph-abc123")
            run_id: Run ID (e.g., "ralph2-abc12345")
            cwd: Optional working directory. If not provided, uses os.getcwd()
            base_branch: Optional branch to create the new branch from.
                        If not provided, branches from current HEAD.
        """
        self.work_item_id = work_item_id
        self.run_id = run_id
        self._cwd = cwd or os.getcwd()
        self._worktree_created = False
        self._worktree_path: Optional[str] = None
        self._branch_name = f"ralph2/{work_item_id}"
        self._base_branch = base_branch

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

        # Create the branch first (from base_branch if specified, otherwise current HEAD)
        if self._base_branch:
            result = self._run_git(["git", "branch", self._branch_name, self._base_branch])
        else:
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
                    _warn(
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
                _warn(
                    f"Failed to remove worktree '{self._worktree_path}': {result.stderr}"
                )
        except Exception as e:
            _warn(f"Exception removing worktree '{self._worktree_path}': {e}")

        # Delete the branch (always attempt, even if worktree removal failed)
        try:
            result = self._run_git(["git", "branch", "-D", self._branch_name])
            branch_deleted = result.returncode == 0
            if not branch_deleted:
                _warn(
                    f"Failed to delete branch '{self._branch_name}': {result.stderr}"
                )
        except Exception as e:
            _warn(f"Exception deleting branch '{self._branch_name}': {e}")

        self._worktree_created = False
        return worktree_removed and branch_deleted

    def merge_to_target(self, target_branch: str = "main") -> Tuple[bool, str]:
        """Merge the feature branch to a target branch.

        This should be called from the main repository (not the worktree).

        Args:
            target_branch: The branch to merge into (default: "main")

        Returns:
            (success, error_message)
        """
        # Ensure we're on the target branch
        result = self._run_git(["git", "checkout", target_branch])
        if result.returncode != 0:
            return False, f"Failed to checkout {target_branch}: {result.stderr}"

        # Merge feature branch
        result = self._run_git(["git", "merge", self._branch_name])
        if result.returncode != 0:
            return False, f"Merge conflict: {result.stderr}"

        return True, ""

    def merge_to_main(self) -> Tuple[bool, str]:
        """Merge the feature branch to main.

        This should be called from the main repository (not the worktree).
        This is a convenience method that calls merge_to_target(target_branch="main").

        Returns:
            (success, error_message)
        """
        return self.merge_to_target(target_branch="main")

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


# =============================================================================
# Standalone functions for orchestrator-managed worktree lifecycle
# =============================================================================
#
# These functions are used by the orchestrator (runner.py) to manage worktrees
# externally to the executors. This allows:
# - Creating all worktrees BEFORE launching parallel executors
# - Merging completed worktrees SERIALLY after all executors finish
# - Guaranteed cleanup even if executors fail
#
# The GitBranchManager class is kept for backward compatibility with
# single-executor mode where the executor manages its own worktree.
# =============================================================================


def _get_worktree_path(work_item_id: str, run_id: str, cwd: str) -> str:
    """Calculate the worktree directory path.

    Args:
        work_item_id: Work item ID (e.g., "ralph-abc123")
        run_id: Run ID (e.g., "ralph2-abc12345")
        cwd: Working directory (project root)

    Returns:
        Absolute path to the worktree directory
    """
    parent_dir = os.path.dirname(cwd)
    return os.path.join(parent_dir, f"ralph2-executor-{run_id}-{work_item_id}")


def _get_branch_name(work_item_id: str) -> str:
    """Get the branch name for a work item.

    Args:
        work_item_id: Work item ID

    Returns:
        Branch name
    """
    return f"ralph2/{work_item_id}"


def _run_git_command(command: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory.

    Args:
        command: Git command as list of strings
        cwd: Working directory

    Returns:
        CompletedProcess result
    """
    return subprocess.run(command, capture_output=True, text=True, cwd=cwd)


def create_worktree(
    work_item_id: str,
    run_id: str,
    cwd: str,
    base_branch: Optional[str] = None
) -> Tuple[str, str]:
    """Create a git worktree and branch for executor work.

    This function is used by the orchestrator to create worktrees BEFORE
    launching parallel executors, ensuring no race conditions.

    Args:
        work_item_id: Work item ID (e.g., "ralph-abc123")
        run_id: Run ID (e.g., "ralph2-abc12345")
        cwd: Working directory (project root)
        base_branch: Optional branch to create the new branch from.
                    If not provided, branches from current HEAD.

    Returns:
        (worktree_path, branch_name)

    Raises:
        RuntimeError: If branch or worktree creation fails
    """
    worktree_path = _get_worktree_path(work_item_id, run_id, cwd)
    branch_name = _get_branch_name(work_item_id)

    # Create the branch first (from base_branch if specified, otherwise current HEAD)
    if base_branch:
        result = _run_git_command(["git", "branch", branch_name, base_branch], cwd)
    else:
        result = _run_git_command(["git", "branch", branch_name], cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create branch '{branch_name}': {result.stderr}")

    # Create worktree for the branch
    try:
        result = _run_git_command(
            ["git", "worktree", "add", worktree_path, branch_name], cwd
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")
        return worktree_path, branch_name
    except Exception as e:
        # Cleanup: delete the branch if worktree creation failed
        cleanup_result = _run_git_command(["git", "branch", "-D", branch_name], cwd)
        if cleanup_result.returncode != 0:
            _warn(
                f"Failed to cleanup branch '{branch_name}' after worktree creation failure: "
                f"{cleanup_result.stderr}"
            )
        raise


def merge_branch(
    branch_name: str,
    cwd: str,
    target_branch: str = "main"
) -> Tuple[bool, str]:
    """Merge a feature branch to a target branch.

    This function is used by the orchestrator to merge completed worktrees
    SERIALLY after all executors finish, preventing race conditions.

    IMPORTANT: This uses `git merge --no-ff` to ensure the merge happens
    even when the target branch has moved forward, creating a merge commit.

    Args:
        branch_name: The branch to merge (e.g., "ralph2/work-item-123")
        cwd: Working directory (project root, NOT the worktree)
        target_branch: The branch to merge into (default: "main")

    Returns:
        (success, error_message) - error_message is empty on success
    """
    # Ensure we're on the target branch
    result = _run_git_command(["git", "checkout", target_branch], cwd)
    if result.returncode != 0:
        return False, f"Failed to checkout {target_branch}: {result.stderr}"

    # Merge feature branch
    result = _run_git_command(["git", "merge", branch_name, "--no-ff", "-m", f"Merge {branch_name}"], cwd)
    if result.returncode != 0:
        # Check for merge conflict
        status_result = _run_git_command(["git", "status", "--porcelain"], cwd)
        conflicts = [
            line for line in (status_result.stdout.strip().split('\n') if status_result.stdout.strip() else [])
            if line.startswith('UU ') or line.startswith('AA ') or line.startswith('DD ')
        ]
        if conflicts:
            return False, f"Merge conflict in files: {', '.join(line[3:] for line in conflicts)}"
        return False, f"Merge failed: {result.stderr}"

    return True, ""


def merge_branch_to_main(branch_name: str, cwd: str) -> Tuple[bool, str]:
    """Merge a feature branch to main.

    This is a convenience function that calls merge_branch(target_branch="main").
    Kept for backward compatibility.

    This function is used by the orchestrator to merge completed worktrees
    SERIALLY after all executors finish, preventing race conditions.

    IMPORTANT: This uses `git merge --no-ff` to ensure the merge happens
    even when main has moved forward, creating a merge commit.

    Args:
        branch_name: The branch to merge (e.g., "ralph2/work-item-123")
        cwd: Working directory (project root, NOT the worktree)

    Returns:
        (success, error_message) - error_message is empty on success
    """
    return merge_branch(branch_name, cwd, target_branch="main")


def abort_merge(cwd: str) -> bool:
    """Abort an in-progress merge.

    Args:
        cwd: Working directory

    Returns:
        True if abort succeeded
    """
    result = _run_git_command(["git", "merge", "--abort"], cwd)
    return result.returncode == 0


def remove_worktree(worktree_path: str, branch_name: str, cwd: str) -> bool:
    """Remove a worktree and delete its branch.

    This function is used by the orchestrator for guaranteed cleanup.
    It attempts both operations and logs warnings on failure but does not raise.

    Args:
        worktree_path: Path to the worktree to remove
        branch_name: Branch name to delete
        cwd: Working directory (project root)

    Returns:
        True if all cleanup succeeded, False otherwise
    """
    worktree_removed = False
    branch_deleted = False

    # Remove the worktree
    try:
        result = _run_git_command(
            ["git", "worktree", "remove", worktree_path, "--force"], cwd
        )
        worktree_removed = result.returncode == 0
        if not worktree_removed:
            _warn(f"Failed to remove worktree '{worktree_path}': {result.stderr}")
    except Exception as e:
        _warn(f"Exception removing worktree '{worktree_path}': {e}")

    # Delete the branch (always attempt, even if worktree removal failed)
    try:
        result = _run_git_command(["git", "branch", "-D", branch_name], cwd)
        branch_deleted = result.returncode == 0
        if not branch_deleted:
            _warn(f"Failed to delete branch '{branch_name}': {result.stderr}")
    except Exception as e:
        _warn(f"Exception deleting branch '{branch_name}': {e}")

    return worktree_removed and branch_deleted
