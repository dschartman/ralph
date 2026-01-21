"""Git operations for Soda state layer.

This module provides the GitClient class for interacting with git repositories,
including reading repository state and managing branches.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Error raised when git operations fail."""

    pass


@dataclass
class CommitInfo:
    """Information about a git commit."""

    sha: str
    message: str
    author: str
    timestamp: str


class GitClient:
    """Client for git operations.

    This client wraps git CLI commands for reading repository state
    and managing branches.

    Attributes:
        cwd: Working directory for git commands (defaults to current directory)
    """

    def __init__(self, cwd: Optional[str] = None):
        """Initialize GitClient.

        Args:
            cwd: Working directory for git commands. If not provided,
                 uses the current working directory.
        """
        self._cwd = cwd

    def _run_git(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command.

        Args:
            args: Git command arguments (without 'git' prefix)
            check: If True, raise GitError on non-zero exit code

        Returns:
            CompletedProcess result

        Raises:
            GitError: If check=True and command fails
        """
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self._cwd,
        )

        if check and result.returncode != 0:
            raise GitError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")

        return result

    def get_current_branch(self) -> str:
        """Get the name of the current branch.

        Returns:
            Current branch name

        Raises:
            GitError: If unable to determine current branch
        """
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes.

        This detects:
        - Staged changes
        - Unstaged changes
        - Untracked files

        Returns:
            True if any uncommitted changes exist, False otherwise
        """
        # Use git status --porcelain to detect any changes
        result = self._run_git(["status", "--porcelain"])
        return bool(result.stdout.strip())

    def get_commits_since(self, base_ref: str) -> list[CommitInfo]:
        """Get list of commits since a base reference.

        Args:
            base_ref: Base commit reference (SHA, branch name, tag, etc.)

        Returns:
            List of CommitInfo objects, most recent first
        """
        # Format: sha|message|author|timestamp
        format_str = "%H|%s|%an|%aI"
        result = self._run_git(
            ["log", f"{base_ref}..HEAD", f"--format={format_str}"],
            check=False,  # Don't raise if no commits
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append(
                    CommitInfo(
                        sha=parts[0],
                        message=parts[1],
                        author=parts[2],
                        timestamp=parts[3],
                    )
                )

        return commits

    def get_diff_summary(self, base_ref: str) -> str:
        """Get a summary of changes since a base reference.

        Returns a stat-style summary showing files changed and lines added/removed.

        Args:
            base_ref: Base commit reference (SHA, branch name, tag, etc.)

        Returns:
            Diff summary string, or empty string if no changes
        """
        result = self._run_git(
            ["diff", "--stat", f"{base_ref}..HEAD"],
            check=False,  # Don't raise if no changes
        )

        if result.returncode != 0:
            return ""

        return result.stdout.strip()

    def create_branch(self, name: str, base_ref: Optional[str] = None) -> str:
        """Create a new branch.

        If a branch with the given name already exists, a numbered suffix
        is added (e.g., feature/name-2, feature/name-3).

        Args:
            name: Desired branch name
            base_ref: Base reference to create branch from. If None, uses HEAD.

        Returns:
            Actual branch name (may have suffix if original existed)

        Raises:
            GitError: If branch creation fails for reasons other than existence
        """
        actual_name = name
        suffix = 1

        while True:
            # Check if branch already exists
            result = self._run_git(
                ["rev-parse", "--verify", f"refs/heads/{actual_name}"],
                check=False,
            )

            if result.returncode != 0:
                # Branch doesn't exist, create it
                if base_ref:
                    self._run_git(["branch", actual_name, base_ref])
                else:
                    self._run_git(["branch", actual_name])
                return actual_name

            # Branch exists, try with suffix
            suffix += 1
            actual_name = f"{name}-{suffix}"

    def checkout_branch(self, name: str) -> None:
        """Checkout a branch.

        Args:
            name: Branch name to checkout

        Raises:
            GitError: If branch doesn't exist or checkout fails
        """
        try:
            self._run_git(["checkout", name])
        except GitError as e:
            if "did not match any file" in str(e) or "pathspec" in str(e):
                raise GitError(f"Branch '{name}' does not exist") from e
            raise

    def merge_branch(self, source_branch: str, target_branch: str) -> bool:
        """Merge source branch into target branch.

        Checks out the target branch first, then merges the source branch into it.

        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge into

        Returns:
            True if merge succeeded, False if there was a conflict
        """
        # Checkout target branch first
        self.checkout_branch(target_branch)

        # Attempt the merge
        result = self._run_git(["merge", source_branch], check=False)

        if result.returncode != 0:
            # Merge failed (likely conflict)
            return False

        return True

    def delete_branch(self, branch_name: str) -> None:
        """Delete a local branch.

        Uses 'git branch -d' which only deletes merged branches.

        Args:
            branch_name: Name of the branch to delete

        Raises:
            GitError: If branch doesn't exist or is not merged
        """
        self._run_git(["branch", "-d", branch_name])

    def stage_all_changes(self) -> None:
        """Stage all changes including untracked files.

        Equivalent to 'git add -A'.

        Raises:
            GitError: If staging fails
        """
        self._run_git(["add", "-A"])

    def create_commit(self, message: str) -> str:
        """Create a commit with the given message.

        Commits all staged changes with the provided message and
        returns the resulting commit hash.

        Args:
            message: The commit message

        Returns:
            The commit hash of the new commit

        Raises:
            GitError: If commit fails (e.g., nothing staged)
        """
        self._run_git(["commit", "-m", message])
        return self.get_head_commit_hash()

    def get_head_commit_hash(self) -> str:
        """Get the commit hash of HEAD.

        Returns:
            The full commit hash of the current HEAD

        Raises:
            GitError: If unable to get HEAD commit hash
        """
        result = self._run_git(["rev-parse", "HEAD"])
        return result.stdout.strip()
