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
