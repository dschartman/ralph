"""Tests for Soda Git operations."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from soda.state.git import CommitInfo, GitClient, GitError


@pytest.fixture
def git_repo(tmp_path: Path):
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit so we have a valid HEAD
    (repo_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    return repo_path


class TestGetCurrentBranch:
    """Tests for GitClient.get_current_branch()."""

    def test_returns_current_branch_name(self, git_repo: Path):
        """WHEN on a branch THEN returns that branch name."""
        client = GitClient(cwd=str(git_repo))
        # Default branch could be main or master depending on git config
        branch = client.get_current_branch()
        assert branch in ("main", "master")

    def test_returns_branch_after_checkout(self, git_repo: Path):
        """WHEN checking out a different branch THEN returns new branch name."""
        client = GitClient(cwd=str(git_repo))

        # Create and checkout a new branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        assert client.get_current_branch() == "feature/test"


class TestHasUncommittedChanges:
    """Tests for GitClient.has_uncommitted_changes()."""

    def test_no_changes_returns_false(self, git_repo: Path):
        """WHEN no changes THEN returns False."""
        client = GitClient(cwd=str(git_repo))
        assert client.has_uncommitted_changes() is False

    def test_unstaged_changes_returns_true(self, git_repo: Path):
        """WHEN unstaged changes exist THEN returns True."""
        client = GitClient(cwd=str(git_repo))

        # Create unstaged changes
        (git_repo / "README.md").write_text("# Modified\n")

        assert client.has_uncommitted_changes() is True

    def test_staged_changes_returns_true(self, git_repo: Path):
        """WHEN staged changes exist THEN returns True."""
        client = GitClient(cwd=str(git_repo))

        # Create staged changes
        (git_repo / "new_file.txt").write_text("content\n")
        subprocess.run(["git", "add", "new_file.txt"], cwd=git_repo, capture_output=True)

        assert client.has_uncommitted_changes() is True

    def test_untracked_files_returns_true(self, git_repo: Path):
        """WHEN untracked files exist THEN returns True."""
        client = GitClient(cwd=str(git_repo))

        # Create untracked file
        (git_repo / "untracked.txt").write_text("content\n")

        assert client.has_uncommitted_changes() is True


class TestGetCommitsSince:
    """Tests for GitClient.get_commits_since()."""

    def test_returns_commits_since_base(self, git_repo: Path):
        """WHEN commits exist since base THEN returns list of CommitInfo."""
        client = GitClient(cwd=str(git_repo))

        # Get initial commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        base_ref = result.stdout.strip()

        # Create new commits
        (git_repo / "file1.txt").write_text("content1\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file1"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        (git_repo / "file2.txt").write_text("content2\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file2"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        commits = client.get_commits_since(base_ref)

        assert len(commits) == 2
        assert all(isinstance(c, CommitInfo) for c in commits)
        assert commits[0].message == "Add file2"  # Most recent first
        assert commits[1].message == "Add file1"

    def test_no_commits_returns_empty_list(self, git_repo: Path):
        """WHEN no commits since base THEN returns empty list."""
        client = GitClient(cwd=str(git_repo))

        # Use current HEAD as base
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        base_ref = result.stdout.strip()

        commits = client.get_commits_since(base_ref)
        assert commits == []


class TestGetDiffSummary:
    """Tests for GitClient.get_diff_summary()."""

    def test_returns_diff_summary(self, git_repo: Path):
        """WHEN changes exist since base THEN returns diff summary string."""
        client = GitClient(cwd=str(git_repo))

        # Get initial commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        base_ref = result.stdout.strip()

        # Create new commits with file changes
        (git_repo / "new_file.txt").write_text("line1\nline2\nline3\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        summary = client.get_diff_summary(base_ref)

        assert "new_file.txt" in summary
        assert isinstance(summary, str)

    def test_no_changes_returns_empty_string(self, git_repo: Path):
        """WHEN no changes since base THEN returns empty string."""
        client = GitClient(cwd=str(git_repo))

        # Use current HEAD as base
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        base_ref = result.stdout.strip()

        summary = client.get_diff_summary(base_ref)
        assert summary == ""


class TestCreateBranch:
    """Tests for GitClient.create_branch()."""

    def test_creates_branch_from_base(self, git_repo: Path):
        """WHEN creating branch THEN creates from specified base."""
        client = GitClient(cwd=str(git_repo))

        # Get current branch as base
        current_branch = client.get_current_branch()

        actual_name = client.create_branch("feature/new", current_branch)

        assert actual_name == "feature/new"

        # Verify branch exists
        result = subprocess.run(
            ["git", "branch", "--list", "feature/new"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "feature/new" in result.stdout

    def test_adds_suffix_when_branch_exists(self, git_repo: Path):
        """WHEN branch already exists THEN adds numbered suffix."""
        client = GitClient(cwd=str(git_repo))
        current_branch = client.get_current_branch()

        # Create first branch
        client.create_branch("feature/existing", current_branch)

        # Try to create same branch again
        actual_name = client.create_branch("feature/existing", current_branch)

        assert actual_name == "feature/existing-2"

        # Create again - should get -3
        actual_name = client.create_branch("feature/existing", current_branch)
        assert actual_name == "feature/existing-3"

    def test_creates_from_current_head_when_no_base(self, git_repo: Path):
        """WHEN no base ref provided THEN creates from current HEAD."""
        client = GitClient(cwd=str(git_repo))

        actual_name = client.create_branch("feature/from-head")

        assert actual_name == "feature/from-head"

        # Verify branch exists
        result = subprocess.run(
            ["git", "branch", "--list", "feature/from-head"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "feature/from-head" in result.stdout


class TestCheckoutBranch:
    """Tests for GitClient.checkout_branch()."""

    def test_switches_to_branch(self, git_repo: Path):
        """WHEN checking out branch THEN working tree switches."""
        client = GitClient(cwd=str(git_repo))

        # Create a branch first
        subprocess.run(
            ["git", "branch", "feature/checkout-test"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        client.checkout_branch("feature/checkout-test")

        assert client.get_current_branch() == "feature/checkout-test"

    def test_raises_error_for_nonexistent_branch(self, git_repo: Path):
        """WHEN branch doesn't exist THEN raises GitError."""
        client = GitClient(cwd=str(git_repo))

        with pytest.raises(GitError) as exc_info:
            client.checkout_branch("nonexistent/branch")

        assert "nonexistent/branch" in str(exc_info.value)


class TestGitError:
    """Tests for GitError exception."""

    def test_git_error_contains_message(self):
        """WHEN GitError raised THEN contains error message."""
        error = GitError("Failed to checkout branch")
        assert str(error) == "Failed to checkout branch"


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commit_info_fields(self):
        """WHEN creating CommitInfo THEN has expected fields."""
        info = CommitInfo(
            sha="abc123",
            message="Test commit",
            author="Test Author",
            timestamp="2024-01-20T12:00:00",
        )

        assert info.sha == "abc123"
        assert info.message == "Test commit"
        assert info.author == "Test Author"
        assert info.timestamp == "2024-01-20T12:00:00"


class TestMergeBranch:
    """Tests for GitClient.merge_branch()."""

    def test_merge_branch_success(self, git_repo: Path):
        """WHEN merging a branch with no conflicts THEN returns True."""
        client = GitClient(cwd=str(git_repo))

        # Create a feature branch with a new file
        subprocess.run(
            ["git", "checkout", "-b", "feature/to-merge"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "feature_file.txt").write_text("feature content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Go back to main/master
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "checkout", "-"],  # Switch back to previous branch
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        main_branch = client.get_current_branch()

        # Merge the feature branch
        result = client.merge_branch("feature/to-merge", main_branch)

        assert result is True
        # Verify the file from feature branch is now in main
        assert (git_repo / "feature_file.txt").exists()

    def test_merge_branch_with_conflict_returns_false(self, git_repo: Path):
        """WHEN merging a branch with conflicts THEN returns False."""
        client = GitClient(cwd=str(git_repo))
        main_branch = client.get_current_branch()

        # Create a feature branch and modify README.md
        subprocess.run(
            ["git", "checkout", "-b", "feature/conflict"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "README.md").write_text("# Feature changes\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature changes to README"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Go back to main and make conflicting changes
        subprocess.run(
            ["git", "checkout", main_branch],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "README.md").write_text("# Main changes\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Main changes to README"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Try to merge - should have conflict
        result = client.merge_branch("feature/conflict", main_branch)

        assert result is False

        # Clean up the failed merge
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=git_repo,
            capture_output=True,
        )

    def test_merge_branch_checks_out_target_first(self, git_repo: Path):
        """WHEN merging THEN checks out target branch before merge."""
        client = GitClient(cwd=str(git_repo))
        main_branch = client.get_current_branch()

        # Create a feature branch with a new file
        subprocess.run(
            ["git", "checkout", "-b", "feature/new-content"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "new_content.txt").write_text("new content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new content"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Stay on feature branch, but merge into main
        result = client.merge_branch("feature/new-content", main_branch)

        assert result is True
        # Should end up on target branch
        assert client.get_current_branch() == main_branch


class TestDeleteBranch:
    """Tests for GitClient.delete_branch()."""

    def test_delete_merged_branch(self, git_repo: Path):
        """WHEN deleting a merged branch THEN branch is removed."""
        client = GitClient(cwd=str(git_repo))
        main_branch = client.get_current_branch()

        # Create and merge a branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/to-delete"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "delete_test.txt").write_text("test content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Go back to main and merge
        subprocess.run(
            ["git", "checkout", main_branch],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "merge", "feature/to-delete"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Delete the branch
        client.delete_branch("feature/to-delete")

        # Verify branch is deleted
        result = subprocess.run(
            ["git", "branch", "--list", "feature/to-delete"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "feature/to-delete" not in result.stdout

    def test_delete_nonexistent_branch_raises_error(self, git_repo: Path):
        """WHEN deleting non-existent branch THEN raises GitError."""
        client = GitClient(cwd=str(git_repo))

        with pytest.raises(GitError):
            client.delete_branch("nonexistent/branch")

    def test_delete_unmerged_branch_raises_error(self, git_repo: Path):
        """WHEN deleting unmerged branch with -d THEN raises GitError."""
        client = GitClient(cwd=str(git_repo))
        main_branch = client.get_current_branch()

        # Create a branch with changes but don't merge
        subprocess.run(
            ["git", "checkout", "-b", "feature/unmerged"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "unmerged.txt").write_text("unmerged content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Unmerged changes"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Go back to main without merging
        subprocess.run(
            ["git", "checkout", main_branch],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        # Try to delete - should fail because branch is unmerged
        with pytest.raises(GitError):
            client.delete_branch("feature/unmerged")
