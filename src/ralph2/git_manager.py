"""Git operations management for Ralph2.

This module provides a GitBranchManager class that handles git worktree and branch
operations with guaranteed cleanup and run_id-based isolation to prevent conflicts
when multiple Ralph2 instances run in parallel.
"""

import subprocess
import os
from pathlib import Path
from typing import Optional


class GitBranchManager:
    """
    Manages git branches and worktrees for Ralph2 executor isolation.

    Features:
    - Worktree paths include run_id to prevent conflicts between parallel runs
    - Guaranteed cleanup on partial failures (branch created but worktree fails)
    - Simple interface for creating, using, and cleaning up worktrees
    """

    def __init__(self, project_root: str, run_id: str):
        """
        Initialize GitBranchManager.

        Args:
            project_root: Path to the project root (git repository)
            run_id: Unique run ID for this Ralph2 execution (e.g., "ralph2-abc123")
        """
        self.project_root = Path(project_root)
        self.run_id = run_id
        self._active_worktrees: dict[str, str] = {}  # work_item_id -> worktree_path

    def get_branch_name(self, work_item_id: str) -> str:
        """
        Generate branch name for a work item.

        Args:
            work_item_id: The work item ID

        Returns:
            Branch name including run_id for uniqueness
        """
        return f"ralph2/{self.run_id}/{work_item_id}"

    def get_worktree_path(self, work_item_id: str) -> str:
        """
        Generate worktree path for a work item.

        Args:
            work_item_id: The work item ID

        Returns:
            Absolute path to the worktree directory
        """
        # Use a sibling directory to project root with run_id in the path
        worktree_dir = self.project_root.parent / f"ralph2-executor-{self.run_id}-{work_item_id}"
        return str(worktree_dir)

    def create_worktree(self, work_item_id: str, base_branch: str = "HEAD") -> str:
        """
        Create a git worktree for isolated work on a work item.

        Args:
            work_item_id: The work item ID
            base_branch: Branch to base the new worktree on (default: HEAD)

        Returns:
            Path to the created worktree

        Raises:
            RuntimeError: If worktree creation fails (cleanup is guaranteed)
        """
        branch_name = self.get_branch_name(work_item_id)
        worktree_path = self.get_worktree_path(work_item_id)

        branch_created = False

        try:
            # First, create the branch
            result = subprocess.run(
                ["git", "branch", branch_name, base_branch],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                # Branch might already exist, try to continue
                if "already exists" not in result.stderr.lower():
                    raise RuntimeError(f"Failed to create branch {branch_name}: {result.stderr}")
            else:
                branch_created = True

            # Then, create the worktree
            result = subprocess.run(
                ["git", "worktree", "add", worktree_path, branch_name],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                # Worktree creation failed - cleanup the branch we created
                if branch_created:
                    self._delete_branch(branch_name)
                raise RuntimeError(f"Failed to create worktree at {worktree_path}: {result.stderr}")

            # Track the active worktree
            self._active_worktrees[work_item_id] = worktree_path

            return worktree_path

        except subprocess.CalledProcessError as e:
            # Cleanup on any subprocess error
            if branch_created:
                self._delete_branch(branch_name)
            raise RuntimeError(f"Git operation failed: {e.stderr}") from e

    def _delete_branch(self, branch_name: str) -> bool:
        """
        Delete a git branch (force delete).

        Args:
            branch_name: Name of the branch to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    def cleanup(self, work_item_id: str) -> bool:
        """
        Clean up worktree and branch for a work item.

        Args:
            work_item_id: The work item ID

        Returns:
            True if cleanup succeeded, False otherwise
        """
        branch_name = self.get_branch_name(work_item_id)
        worktree_path = self.get_worktree_path(work_item_id)

        worktree_removed = False
        branch_deleted = False

        # First, remove the worktree
        try:
            result = subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False
            )
            worktree_removed = result.returncode == 0 or "is not a working tree" in result.stderr.lower()
        except Exception:
            pass

        # Then, delete the branch
        branch_deleted = self._delete_branch(branch_name)

        # Remove from tracking
        self._active_worktrees.pop(work_item_id, None)

        return worktree_removed and branch_deleted

    def cleanup_all(self) -> None:
        """Clean up all active worktrees managed by this instance."""
        for work_item_id in list(self._active_worktrees.keys()):
            self.cleanup(work_item_id)

    def merge_changes(self, work_item_id: str, target_branch: str = "HEAD") -> bool:
        """
        Merge changes from a work item's branch into target branch.

        Args:
            work_item_id: The work item ID
            target_branch: Branch to merge into (default: HEAD)

        Returns:
            True if merge succeeded, False otherwise
        """
        branch_name = self.get_branch_name(work_item_id)

        try:
            # Merge the branch
            result = subprocess.run(
                ["git", "merge", branch_name, "--no-edit"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    @classmethod
    def cleanup_abandoned_worktrees(cls, project_root: str, run_id_prefix: str = "ralph2-") -> int:
        """
        Clean up abandoned worktrees from interrupted runs.

        Args:
            project_root: Path to the project root
            run_id_prefix: Prefix for run IDs to clean up

        Returns:
            Number of worktrees cleaned up
        """
        cleaned = 0

        try:
            # Get list of worktrees
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                return 0

            # Parse worktree paths
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.startswith('worktree '):
                    worktree_path = line.replace('worktree ', '').strip()
                    if f'ralph2-executor-{run_id_prefix}' in worktree_path:
                        # Remove abandoned worktree
                        subprocess.run(
                            ["git", "worktree", "remove", worktree_path, "--force"],
                            cwd=project_root,
                            capture_output=True,
                            check=False
                        )
                        cleaned += 1

            # Clean up branches too
            result = subprocess.run(
                ["git", "branch", "--list", f"ralph2/{run_id_prefix}*"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0 and result.stdout.strip():
                branches = [b.strip().replace('* ', '') for b in result.stdout.strip().split('\n')]
                for branch in branches:
                    if branch:
                        subprocess.run(
                            ["git", "branch", "-D", branch],
                            cwd=project_root,
                            capture_output=True,
                            check=False
                        )

        except Exception:
            pass

        return cleaned
