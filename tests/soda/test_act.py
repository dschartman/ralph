"""Tests for ACT data structures and act() function."""

import pytest
from pydantic import ValidationError

from soda.act import (
    ActOutput,
    BlockedTask,
    TaskComment,
    NewTask,
)


# =============================================================================
# BlockedTask Model Tests
# =============================================================================


class TestBlockedTask:
    """Tests for BlockedTask model."""

    def test_blocked_task_creation(self):
        """BlockedTask can be created with task_id and reason."""
        blocked = BlockedTask(
            task_id="ralph-abc123",
            reason="Missing API key for external service",
        )
        assert blocked.task_id == "ralph-abc123"
        assert blocked.reason == "Missing API key for external service"

    def test_blocked_task_requires_task_id(self):
        """BlockedTask requires task_id field."""
        with pytest.raises(ValidationError):
            BlockedTask(reason="Some reason")

    def test_blocked_task_requires_reason(self):
        """BlockedTask requires reason field."""
        with pytest.raises(ValidationError):
            BlockedTask(task_id="ralph-abc123")

    def test_blocked_task_serialization(self):
        """BlockedTask can be serialized to dict."""
        blocked = BlockedTask(
            task_id="ralph-xyz789",
            reason="Tests require database connection",
        )
        data = blocked.model_dump()
        assert data["task_id"] == "ralph-xyz789"
        assert data["reason"] == "Tests require database connection"


# =============================================================================
# TaskComment Model Tests
# =============================================================================


class TestTaskComment:
    """Tests for TaskComment model (ACT-specific, simpler than sense.TaskComment)."""

    def test_task_comment_creation(self):
        """TaskComment can be created with task_id and comment."""
        comment = TaskComment(
            task_id="ralph-abc123",
            comment="Started working on implementation",
        )
        assert comment.task_id == "ralph-abc123"
        assert comment.comment == "Started working on implementation"

    def test_task_comment_requires_task_id(self):
        """TaskComment requires task_id field."""
        with pytest.raises(ValidationError):
            TaskComment(comment="Some comment")

    def test_task_comment_requires_comment(self):
        """TaskComment requires comment field."""
        with pytest.raises(ValidationError):
            TaskComment(task_id="ralph-abc123")

    def test_task_comment_serialization(self):
        """TaskComment can be serialized to dict."""
        comment = TaskComment(
            task_id="ralph-xyz789",
            comment="Completed unit tests",
        )
        data = comment.model_dump()
        assert data["task_id"] == "ralph-xyz789"
        assert data["comment"] == "Completed unit tests"


# =============================================================================
# NewTask Model Tests (imported from orient, verify it works)
# =============================================================================


class TestNewTask:
    """Tests for NewTask model (reused from orient)."""

    def test_new_task_creation_minimal(self):
        """NewTask can be created with just title and description."""
        task = NewTask(
            title="Add validation",
            description="Add input validation to the API endpoint",
        )
        assert task.title == "Add validation"
        assert task.description == "Add input validation to the API endpoint"
        assert task.priority == 1  # default

    def test_new_task_creation_full(self):
        """NewTask can be created with all fields."""
        task = NewTask(
            title="Fix bug",
            description="Fix null pointer in parser",
            priority=0,
            parent_id="ralph-abc123",
            blocked_by="ralph-xyz789",
        )
        assert task.title == "Fix bug"
        assert task.description == "Fix null pointer in parser"
        assert task.priority == 0
        assert task.parent_id == "ralph-abc123"
        assert task.blocked_by == "ralph-xyz789"

    def test_new_task_requires_title(self):
        """NewTask requires title field."""
        with pytest.raises(ValidationError):
            NewTask(description="Some description")

    def test_new_task_requires_description(self):
        """NewTask requires description field."""
        with pytest.raises(ValidationError):
            NewTask(title="Some title")

    def test_new_task_priority_validation(self):
        """NewTask priority must be 0, 1, or 2."""
        with pytest.raises(ValidationError):
            NewTask(title="Test", description="Desc", priority=3)
        with pytest.raises(ValidationError):
            NewTask(title="Test", description="Desc", priority=-1)


# =============================================================================
# ActOutput Model Tests
# =============================================================================


class TestActOutput:
    """Tests for ActOutput model."""

    def test_act_output_creation_empty(self):
        """ActOutput can be created with empty lists (all work blocked)."""
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=[],
        )
        assert output.tasks_completed == []
        assert output.tasks_blocked == []
        assert output.task_comments == []
        assert output.new_subtasks == []
        assert output.learnings == []
        assert output.commits == []

    def test_act_output_creation_with_completed_tasks(self):
        """ActOutput can include completed task IDs."""
        output = ActOutput(
            tasks_completed=["ralph-abc123", "ralph-def456"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["a1b2c3d"],
        )
        assert output.tasks_completed == ["ralph-abc123", "ralph-def456"]
        assert output.commits == ["a1b2c3d"]

    def test_act_output_creation_with_blocked_tasks(self):
        """ActOutput can include blocked tasks with reasons."""
        blocked = BlockedTask(
            task_id="ralph-xyz789",
            reason="External API unavailable",
        )
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[blocked],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=[],
        )
        assert len(output.tasks_blocked) == 1
        assert output.tasks_blocked[0].task_id == "ralph-xyz789"
        assert output.tasks_blocked[0].reason == "External API unavailable"

    def test_act_output_creation_with_comments(self):
        """ActOutput can include task comments."""
        comment = TaskComment(
            task_id="ralph-abc123",
            comment="Implemented feature X",
        )
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[],
            task_comments=[comment],
            new_subtasks=[],
            learnings=[],
            commits=["abc1234"],
        )
        assert len(output.task_comments) == 1
        assert output.task_comments[0].comment == "Implemented feature X"

    def test_act_output_creation_with_subtasks(self):
        """ActOutput can include new subtasks discovered during work."""
        subtask = NewTask(
            title="Handle edge case",
            description="Add handling for null input",
            parent_id="ralph-abc123",
        )
        output = ActOutput(
            tasks_completed=[],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[subtask],
            learnings=[],
            commits=[],
        )
        assert len(output.new_subtasks) == 1
        assert output.new_subtasks[0].title == "Handle edge case"
        assert output.new_subtasks[0].parent_id == "ralph-abc123"

    def test_act_output_creation_with_learnings(self):
        """ActOutput can include learnings/efficiency knowledge."""
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[
                "Run tests with `uv run pytest tests/soda/ -v`",
                "API client is in src/soda/api.py",
            ],
            commits=["abc1234"],
        )
        assert len(output.learnings) == 2
        assert "pytest" in output.learnings[0]

    def test_act_output_creation_with_multiple_commits(self):
        """ActOutput can include multiple commit hashes."""
        output = ActOutput(
            tasks_completed=["ralph-abc123", "ralph-def456"],
            tasks_blocked=[],
            task_comments=[],
            new_subtasks=[],
            learnings=[],
            commits=["a1b2c3d", "e5f6g7h", "i9j0k1l"],
        )
        assert len(output.commits) == 3

    def test_act_output_full_example(self):
        """ActOutput can hold a realistic full ACT phase output."""
        output = ActOutput(
            tasks_completed=["ralph-task1", "ralph-task2"],
            tasks_blocked=[
                BlockedTask(
                    task_id="ralph-task3",
                    reason="Requires external API key",
                ),
            ],
            task_comments=[
                TaskComment(
                    task_id="ralph-task1",
                    comment="Started implementation",
                ),
                TaskComment(
                    task_id="ralph-task1",
                    comment="Tests passing",
                ),
                TaskComment(
                    task_id="ralph-task3",
                    comment="Blocked: needs API key",
                ),
            ],
            new_subtasks=[
                NewTask(
                    title="Add error handling",
                    description="Handle timeout errors in API client",
                    parent_id="ralph-task1",
                    priority=1,
                ),
            ],
            learnings=[
                "Project uses uv for dependency management",
                "Run `trc list` to see all tasks",
            ],
            commits=["abc1234def", "567890abc"],
        )
        assert len(output.tasks_completed) == 2
        assert len(output.tasks_blocked) == 1
        assert len(output.task_comments) == 3
        assert len(output.new_subtasks) == 1
        assert len(output.learnings) == 2
        assert len(output.commits) == 2

    def test_act_output_serialization(self):
        """ActOutput can be serialized to dict (JSON-compatible)."""
        output = ActOutput(
            tasks_completed=["ralph-abc123"],
            tasks_blocked=[
                BlockedTask(task_id="ralph-xyz789", reason="Blocked reason"),
            ],
            task_comments=[
                TaskComment(task_id="ralph-abc123", comment="Done"),
            ],
            new_subtasks=[
                NewTask(title="Subtask", description="Desc"),
            ],
            learnings=["A learning"],
            commits=["abc1234"],
        )
        data = output.model_dump()
        assert data["tasks_completed"] == ["ralph-abc123"]
        assert data["tasks_blocked"][0]["task_id"] == "ralph-xyz789"
        assert data["task_comments"][0]["comment"] == "Done"
        assert data["new_subtasks"][0]["title"] == "Subtask"
        assert data["learnings"] == ["A learning"]
        assert data["commits"] == ["abc1234"]

    def test_act_output_defaults_to_empty_lists(self):
        """ActOutput uses default_factory for empty lists."""
        output = ActOutput()
        assert output.tasks_completed == []
        assert output.tasks_blocked == []
        assert output.task_comments == []
        assert output.new_subtasks == []
        assert output.learnings == []
        assert output.commits == []


# =============================================================================
# TestBaseline Model Tests
# =============================================================================


class TestTestBaseline:
    """Tests for TestBaseline model (captures test pass/fail state)."""

    def test_baseline_creation_with_counts(self):
        """TestBaseline can be created with passed/failed/total counts."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=10,
            failed=2,
            total=12,
            has_tests=True,
        )
        assert baseline.passed == 10
        assert baseline.failed == 2
        assert baseline.total == 12
        assert baseline.has_tests is True

    def test_baseline_no_tests(self):
        """TestBaseline can represent 'no tests' state."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
        )
        assert baseline.has_tests is False
        assert baseline.total == 0

    def test_baseline_with_error_message(self):
        """TestBaseline can include error message when tests fail to run."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            error="pytest not found",
        )
        assert baseline.error == "pytest not found"

    def test_baseline_serialization(self):
        """TestBaseline can be serialized to dict."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=5,
            failed=1,
            total=6,
            has_tests=True,
        )
        data = baseline.model_dump()
        assert data["passed"] == 5
        assert data["failed"] == 1
        assert data["total"] == 6
        assert data["has_tests"] is True


# =============================================================================
# Workspace Setup Tests (Orchestrator Functions)
# =============================================================================


class TestCreateWorkBranch:
    """Tests for create_work_branch() orchestrator function."""

    def test_creates_branch_with_iteration_pattern(self, git_repo):
        """WHEN creating work branch THEN uses soda/iteration-N pattern."""
        from soda.act import create_work_branch
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        branch_name = create_work_branch(client, iteration_num=1)

        assert branch_name == "soda/iteration-1"

    def test_creates_branch_from_current_head(self, git_repo):
        """WHEN creating work branch THEN creates from current HEAD."""
        import subprocess
        from soda.act import create_work_branch
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        branch_name = create_work_branch(client, iteration_num=1)

        # Verify branch was created
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert branch_name in result.stdout

    def test_creates_branch_from_milestone_branch(self, git_repo):
        """WHEN milestone_branch provided THEN creates from that branch."""
        import subprocess
        from soda.act import create_work_branch
        from soda.state.git import GitClient

        # Create milestone branch with a different commit
        subprocess.run(
            ["git", "checkout", "-b", "feature/milestone"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        (git_repo / "milestone.txt").write_text("milestone content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Milestone commit"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        client = GitClient(cwd=str(git_repo))
        branch_name = create_work_branch(
            client, iteration_num=1, milestone_branch="feature/milestone"
        )

        assert branch_name == "soda/iteration-1"

    def test_handles_existing_branch_with_suffix(self, git_repo):
        """WHEN iteration branch exists THEN adds suffix."""
        import subprocess
        from soda.act import create_work_branch
        from soda.state.git import GitClient

        # Create existing iteration-1 branch
        subprocess.run(
            ["git", "branch", "soda/iteration-1"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        client = GitClient(cwd=str(git_repo))
        branch_name = create_work_branch(client, iteration_num=1)

        assert branch_name == "soda/iteration-1-2"

    def test_checkouts_new_branch(self, git_repo):
        """WHEN creating work branch THEN checks it out."""
        from soda.act import create_work_branch
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        branch_name = create_work_branch(client, iteration_num=3)

        # Verify we're now on the new branch
        current = client.get_current_branch()
        assert current == branch_name


# =============================================================================
# Test Baseline Capture Tests
# =============================================================================


class TestCaptureTestBaseline:
    """Tests for capture_test_baseline() orchestrator function."""

    def test_captures_passing_tests(self, tmp_path):
        """WHEN tests pass THEN baseline shows passed count."""
        from soda.act import capture_test_baseline

        # Create a minimal project with passing tests
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass1():
    assert True

def test_pass2():
    assert True
"""
        )

        baseline = capture_test_baseline(cwd=str(tmp_path))

        assert baseline.has_tests is True
        assert baseline.passed == 2
        assert baseline.failed == 0
        assert baseline.total == 2

    def test_captures_failing_tests(self, tmp_path):
        """WHEN tests fail THEN baseline shows failed count."""
        from soda.act import capture_test_baseline

        # Create a minimal project with failing tests
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass():
    assert True

def test_fail():
    assert False
"""
        )

        baseline = capture_test_baseline(cwd=str(tmp_path))

        assert baseline.has_tests is True
        assert baseline.passed == 1
        assert baseline.failed == 1
        assert baseline.total == 2

    def test_no_tests_returns_no_tests_baseline(self, tmp_path):
        """WHEN no tests exist THEN baseline shows has_tests=False."""
        from soda.act import capture_test_baseline

        # Empty directory - no tests
        baseline = capture_test_baseline(cwd=str(tmp_path))

        assert baseline.has_tests is False
        assert baseline.total == 0

    def test_no_pytest_returns_no_tests_baseline(self, tmp_path, monkeypatch):
        """WHEN pytest not available THEN baseline shows has_tests=False with error."""
        import subprocess
        from soda.act import capture_test_baseline

        # Mock subprocess to simulate pytest not found
        def mock_run(*args, **kwargs):
            raise FileNotFoundError("pytest not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        baseline = capture_test_baseline(cwd=str(tmp_path))

        assert baseline.has_tests is False
        assert baseline.error is not None


# =============================================================================
# Git Repo Fixture for Workspace Tests
# =============================================================================


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository for testing."""
    import subprocess

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


# =============================================================================
# Commit Logic Tests (Orchestrator Functions)
# =============================================================================


class TestCommitTaskChanges:
    """Tests for commit_task_changes() orchestrator function."""

    def test_commits_changes_with_task_id_in_message(self, git_repo):
        """WHEN changes exist THEN commits with message referencing task ID."""
        import subprocess
        from soda.act import commit_task_changes
        from soda.state.git import GitClient

        # Create a change
        (git_repo / "new_file.py").write_text("# new file\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)

        client = GitClient(cwd=str(git_repo))
        commit_hash = commit_task_changes(client, task_id="ralph-abc123")

        # Verify commit was created
        assert commit_hash is not None
        assert len(commit_hash) > 0

        # Verify commit message contains task ID
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "ralph-abc123" in result.stdout

    def test_skips_commit_when_no_changes(self, git_repo):
        """WHEN no changes exist THEN returns None without committing."""
        from soda.act import commit_task_changes
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        commit_hash = commit_task_changes(client, task_id="ralph-xyz789")

        # No commit should be created
        assert commit_hash is None

    def test_stages_unstaged_changes_before_commit(self, git_repo):
        """WHEN unstaged changes exist THEN stages and commits them."""
        import subprocess
        from soda.act import commit_task_changes
        from soda.state.git import GitClient

        # Create unstaged changes (not added to git)
        (git_repo / "unstaged_file.txt").write_text("unstaged content\n")

        client = GitClient(cwd=str(git_repo))
        commit_hash = commit_task_changes(client, task_id="ralph-def456")

        # Verify commit was created
        assert commit_hash is not None

        # Verify the file was committed
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "unstaged_file.txt" in result.stdout

    def test_returns_commit_hash(self, git_repo):
        """WHEN changes committed THEN returns the commit hash."""
        import subprocess
        from soda.act import commit_task_changes
        from soda.state.git import GitClient

        # Create a change
        (git_repo / "another_file.py").write_text("# content\n")

        client = GitClient(cwd=str(git_repo))
        commit_hash = commit_task_changes(client, task_id="ralph-ghi789")

        # Verify hash is valid
        result = subprocess.run(
            ["git", "rev-parse", commit_hash],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0


class TestCommitOrStashUncommitted:
    """Tests for commit_or_stash_uncommitted() orchestrator function."""

    def test_commits_uncommitted_changes(self, git_repo):
        """WHEN uncommitted changes exist THEN commits them."""
        import subprocess
        from soda.act import commit_or_stash_uncommitted
        from soda.state.git import GitClient

        # Create uncommitted changes
        (git_repo / "uncommitted.txt").write_text("uncommitted content\n")

        client = GitClient(cwd=str(git_repo))
        result = commit_or_stash_uncommitted(client, task_id="ralph-task1")

        # Verify commit was created
        assert result["action"] == "committed"
        assert result["commit_hash"] is not None

        # Verify no uncommitted changes remain
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip() == ""

    def test_returns_none_when_no_changes(self, git_repo):
        """WHEN no uncommitted changes THEN returns action='none'."""
        from soda.act import commit_or_stash_uncommitted
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        result = commit_or_stash_uncommitted(client, task_id="ralph-task2")

        assert result["action"] == "none"
        assert result["commit_hash"] is None

    def test_commits_with_task_id_in_message(self, git_repo):
        """WHEN committing uncommitted changes THEN includes task ID in message."""
        import subprocess
        from soda.act import commit_or_stash_uncommitted
        from soda.state.git import GitClient

        # Create uncommitted changes
        (git_repo / "final_changes.txt").write_text("final content\n")

        client = GitClient(cwd=str(git_repo))
        commit_or_stash_uncommitted(client, task_id="ralph-task3")

        # Verify commit message
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "ralph-task3" in result.stdout


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes() helper function."""

    def test_returns_false_for_clean_repo(self, git_repo):
        """WHEN no changes exist THEN returns False."""
        from soda.state.git import GitClient

        client = GitClient(cwd=str(git_repo))
        assert client.has_uncommitted_changes() is False

    def test_returns_true_for_staged_changes(self, git_repo):
        """WHEN staged changes exist THEN returns True."""
        import subprocess
        from soda.state.git import GitClient

        # Create and stage a file
        (git_repo / "staged.txt").write_text("staged content\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)

        client = GitClient(cwd=str(git_repo))
        assert client.has_uncommitted_changes() is True

    def test_returns_true_for_unstaged_changes(self, git_repo):
        """WHEN unstaged changes exist THEN returns True."""
        from soda.state.git import GitClient

        # Create an untracked file
        (git_repo / "untracked.txt").write_text("untracked content\n")

        client = GitClient(cwd=str(git_repo))
        assert client.has_uncommitted_changes() is True

    def test_returns_true_for_modified_tracked_file(self, git_repo):
        """WHEN tracked file is modified THEN returns True."""
        from soda.state.git import GitClient

        # Modify the existing README.md
        (git_repo / "README.md").write_text("# Modified content\n")

        client = GitClient(cwd=str(git_repo))
        assert client.has_uncommitted_changes() is True


# =============================================================================
# VerifyResult Model Tests
# =============================================================================


class TestVerifyResult:
    """Tests for VerifyResult model (verification outcome)."""

    def test_verify_result_creation_all_passed(self):
        """VerifyResult can represent all tests passing."""
        from soda.act import VerifyResult

        result = VerifyResult(
            passed=True,
            new_failures=[],
            regressions=False,
        )
        assert result.passed is True
        assert result.new_failures == []
        assert result.regressions is False

    def test_verify_result_with_new_failures(self):
        """VerifyResult can include new failures not in baseline."""
        from soda.act import VerifyResult

        result = VerifyResult(
            passed=False,
            new_failures=["test_foo.py::test_new_feature", "test_bar.py::test_edge_case"],
            regressions=True,
        )
        assert result.passed is False
        assert len(result.new_failures) == 2
        assert result.regressions is True

    def test_verify_result_serialization(self):
        """VerifyResult can be serialized to dict."""
        from soda.act import VerifyResult

        result = VerifyResult(
            passed=False,
            new_failures=["test_foo.py::test_something"],
            regressions=True,
        )
        data = result.model_dump()
        assert data["passed"] is False
        assert data["new_failures"] == ["test_foo.py::test_something"]
        assert data["regressions"] is True


# =============================================================================
# TestBaseline Extended Tests (with failed_tests)
# =============================================================================


class TestTestBaselineExtended:
    """Tests for TestBaseline with failed_tests tracking."""

    def test_baseline_with_failed_tests_list(self):
        """TestBaseline can track specific test names that failed."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=8,
            failed=2,
            total=10,
            has_tests=True,
            failed_tests=["test_foo.py::test_a", "test_bar.py::test_b"],
        )
        assert len(baseline.failed_tests) == 2
        assert "test_foo.py::test_a" in baseline.failed_tests

    def test_baseline_failed_tests_defaults_empty(self):
        """TestBaseline defaults to empty failed_tests list."""
        from soda.act import TestBaseline

        baseline = TestBaseline(
            passed=5,
            failed=0,
            total=5,
            has_tests=True,
        )
        assert baseline.failed_tests == []


# =============================================================================
# verify_task Function Tests
# =============================================================================


class TestVerifyTask:
    """Tests for verify_task() function."""

    def test_verify_task_all_pass_against_clean_baseline(self, tmp_path):
        """WHEN all tests pass AND baseline was clean THEN passed=True."""
        from soda.act import TestBaseline, verify_task

        # Create passing tests
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass1():
    assert True

def test_pass2():
    assert True
"""
        )

        baseline = TestBaseline(
            passed=2,
            failed=0,
            total=2,
            has_tests=True,
            failed_tests=[],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        assert result.passed is True
        assert result.new_failures == []
        assert result.regressions is False

    def test_verify_task_detects_new_failures(self, tmp_path):
        """WHEN tests fail that weren't in baseline THEN regressions=True."""
        from soda.act import TestBaseline, verify_task

        # Create tests with a new failure
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass():
    assert True

def test_new_failure():
    assert False
"""
        )

        # Baseline had no failures
        baseline = TestBaseline(
            passed=2,
            failed=0,
            total=2,
            has_tests=True,
            failed_tests=[],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        assert result.passed is False
        assert result.regressions is True
        assert len(result.new_failures) == 1
        assert "test_new_failure" in result.new_failures[0]

    def test_verify_task_ignores_baseline_failures(self, tmp_path):
        """WHEN test fails that was already in baseline THEN not counted as new."""
        from soda.act import TestBaseline, verify_task

        # Create tests where one fails (same as baseline)
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass():
    assert True

def test_known_failure():
    assert False
"""
        )

        # Baseline already had this failure
        baseline = TestBaseline(
            passed=1,
            failed=1,
            total=2,
            has_tests=True,
            failed_tests=["test_example.py::test_known_failure"],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        # No new failures (the existing failure was in baseline)
        assert result.regressions is False
        assert result.new_failures == []
        # But passed is False because tests did fail
        assert result.passed is False

    def test_verify_task_with_mixed_failures(self, tmp_path):
        """WHEN some failures are new and some were in baseline THEN only new ones reported."""
        from soda.act import TestBaseline, verify_task

        # Create tests with both old and new failures
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass():
    assert True

def test_known_failure():
    assert False

def test_new_failure():
    assert False
"""
        )

        # Baseline had one failure
        baseline = TestBaseline(
            passed=2,
            failed=1,
            total=3,
            has_tests=True,
            failed_tests=["test_example.py::test_known_failure"],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        # Only the new failure should be reported
        assert result.passed is False
        assert result.regressions is True
        assert len(result.new_failures) == 1
        assert "test_new_failure" in result.new_failures[0]
        assert "test_known_failure" not in str(result.new_failures)

    def test_verify_task_with_no_tests_baseline(self, tmp_path):
        """WHEN baseline has_tests=False THEN verification still works."""
        from soda.act import TestBaseline, verify_task

        # Create passing tests
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """\
def test_pass():
    assert True
"""
        )

        # Baseline indicated no tests (maybe tests were added)
        baseline = TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            failed_tests=[],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        assert result.passed is True
        assert result.new_failures == []
        assert result.regressions is False

    def test_verify_task_with_no_tests_now(self, tmp_path):
        """WHEN no tests exist now THEN verification returns passed=True."""
        from soda.act import TestBaseline, verify_task

        # Empty directory - no tests
        baseline = TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            failed_tests=[],
        )

        result = verify_task(baseline, cwd=str(tmp_path))

        assert result.passed is True
        assert result.new_failures == []
        assert result.regressions is False


# =============================================================================
# Trace Integration Tests (Task Updates)
# =============================================================================


class TestPostProgressComment:
    """Tests for post_progress_comment() function."""

    def test_posts_comment_to_trace(self):
        """WHEN posting progress comment THEN calls TraceClient.post_comment."""
        from unittest.mock import MagicMock
        from soda.act import post_progress_comment

        mock_trace = MagicMock()

        result = post_progress_comment(
            mock_trace,
            task_id="ralph-abc123",
            comment="Started implementation"
        )

        mock_trace.post_comment.assert_called_once_with(
            "ralph-abc123",
            "Started implementation",
            source="executor"
        )

    def test_returns_task_comment(self):
        """WHEN posting comment THEN returns TaskComment with task_id and comment."""
        from unittest.mock import MagicMock
        from soda.act import post_progress_comment, TaskComment

        mock_trace = MagicMock()

        result = post_progress_comment(
            mock_trace,
            task_id="ralph-xyz789",
            comment="Tests passing"
        )

        assert isinstance(result, TaskComment)
        assert result.task_id == "ralph-xyz789"
        assert result.comment == "Tests passing"


class TestCloseTaskTrace:
    """Tests for close_task_in_trace() Trace integration function."""

    def test_closes_task_in_trace(self):
        """WHEN closing task THEN calls TraceClient.close_task with message."""
        from unittest.mock import MagicMock
        from soda.act import close_task_in_trace

        mock_trace = MagicMock()

        close_task_in_trace(
            mock_trace,
            task_id="ralph-abc123",
            completion_message="Task completed successfully"
        )

        mock_trace.close_task.assert_called_once_with(
            "ralph-abc123",
            message="Task completed successfully"
        )

    def test_closes_task_without_message(self):
        """WHEN no message provided THEN closes with default message."""
        from unittest.mock import MagicMock
        from soda.act import close_task_in_trace

        mock_trace = MagicMock()

        close_task_in_trace(
            mock_trace,
            task_id="ralph-abc123"
        )

        mock_trace.close_task.assert_called_once()
        # Should have been called with task_id and message
        call_args = mock_trace.close_task.call_args
        assert call_args[0][0] == "ralph-abc123"


class TestMarkTaskBlocked:
    """Tests for mark_task_blocked() function."""

    def test_posts_blocker_comment_to_trace(self):
        """WHEN marking task blocked THEN posts comment with blocker reason."""
        from unittest.mock import MagicMock
        from soda.act import mark_task_blocked

        mock_trace = MagicMock()

        mark_task_blocked(
            mock_trace,
            task_id="ralph-abc123",
            blocker_reason="Missing API key"
        )

        mock_trace.post_comment.assert_called_once()
        call_args = mock_trace.post_comment.call_args
        assert call_args[0][0] == "ralph-abc123"
        assert "BLOCKED" in call_args[0][1] or "blocked" in call_args[0][1].lower()
        assert "Missing API key" in call_args[0][1]

    def test_returns_blocked_task(self):
        """WHEN marking task blocked THEN returns BlockedTask."""
        from unittest.mock import MagicMock
        from soda.act import mark_task_blocked, BlockedTask

        mock_trace = MagicMock()

        result = mark_task_blocked(
            mock_trace,
            task_id="ralph-xyz789",
            blocker_reason="External service unavailable"
        )

        assert isinstance(result, BlockedTask)
        assert result.task_id == "ralph-xyz789"
        assert result.reason == "External service unavailable"


class TestCreateSubtask:
    """Tests for create_subtask() function."""

    def test_creates_subtask_in_trace(self):
        """WHEN creating subtask THEN calls TraceClient.create_task with parent."""
        from unittest.mock import MagicMock
        from soda.act import create_subtask

        mock_trace = MagicMock()
        mock_trace.create_task.return_value = "ralph-new123"

        result = create_subtask(
            mock_trace,
            parent_id="ralph-parent",
            title="Handle edge case",
            description="Add null check for input"
        )

        mock_trace.create_task.assert_called_once_with(
            "Handle edge case",
            "Add null check for input",
            parent="ralph-parent"
        )

    def test_returns_new_task_id(self):
        """WHEN subtask created THEN returns the new task ID."""
        from unittest.mock import MagicMock
        from soda.act import create_subtask

        mock_trace = MagicMock()
        mock_trace.create_task.return_value = "ralph-subtask456"

        result = create_subtask(
            mock_trace,
            parent_id="ralph-parent",
            title="Add validation",
            description="Validate input parameters"
        )

        assert result == "ralph-subtask456"
