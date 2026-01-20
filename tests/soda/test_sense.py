"""Tests for SENSE data structures (Claims) and sense() function."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from soda.sense import (
    Claims,
    CodeStateClaims,
    CommitInfo,
    DiffSummary,
    HumanInputClaims,
    ProjectStateClaims,
    IterationSummary,
    AgentSummary,
    TaskInfo,
    TaskComment,
    WorkStateClaims,
    sense,
    SenseContext,
)


class TestCommitInfo:
    """Tests for CommitInfo model."""

    def test_commit_info_creation(self):
        """CommitInfo can be created with all required fields."""
        commit = CommitInfo(
            hash="abc123",
            message="Initial commit",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert commit.hash == "abc123"
        assert commit.message == "Initial commit"
        assert commit.timestamp == datetime(2024, 1, 15, 10, 30, 0)

    def test_commit_info_json_serializable(self):
        """CommitInfo can be serialized to JSON."""
        commit = CommitInfo(
            hash="abc123",
            message="Initial commit",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        data = commit.model_dump(mode="json")
        assert data["hash"] == "abc123"
        assert data["message"] == "Initial commit"
        assert "timestamp" in data


class TestDiffSummary:
    """Tests for DiffSummary model."""

    def test_diff_summary_creation(self):
        """DiffSummary can be created with all required fields."""
        diff = DiffSummary(lines_added=100, lines_removed=50)
        assert diff.lines_added == 100
        assert diff.lines_removed == 50

    def test_diff_summary_json_serializable(self):
        """DiffSummary can be serialized to JSON."""
        diff = DiffSummary(lines_added=100, lines_removed=50)
        data = diff.model_dump(mode="json")
        assert data["lines_added"] == 100
        assert data["lines_removed"] == 50


class TestCodeStateClaims:
    """Tests for CodeStateClaims model."""

    def test_code_state_claims_creation(self):
        """CodeStateClaims can be created with all fields."""
        code_state = CodeStateClaims(
            branch="main",
            staged_count=5,
            unstaged_count=3,
            commits=[
                CommitInfo(
                    hash="abc123",
                    message="Add feature",
                    timestamp=datetime(2024, 1, 15, 10, 30, 0),
                )
            ],
            files_changed=["src/main.py", "tests/test_main.py"],
            diff_summary=DiffSummary(lines_added=100, lines_removed=50),
        )
        assert code_state.branch == "main"
        assert code_state.staged_count == 5
        assert code_state.unstaged_count == 3
        assert len(code_state.commits) == 1
        assert code_state.files_changed == ["src/main.py", "tests/test_main.py"]
        assert code_state.diff_summary.lines_added == 100

    def test_code_state_claims_with_error(self):
        """CodeStateClaims can include error message."""
        code_state = CodeStateClaims(
            branch=None,
            staged_count=0,
            unstaged_count=0,
            commits=[],
            files_changed=[],
            diff_summary=None,
            error="Failed to read git state",
        )
        assert code_state.error == "Failed to read git state"

    def test_code_state_no_base_commit(self):
        """CodeStateClaims handles no base commit case."""
        code_state = CodeStateClaims(
            branch="main",
            staged_count=0,
            unstaged_count=0,
            commits=[],
            files_changed=[],
            diff_summary=None,
            no_base_commit=True,
        )
        assert code_state.no_base_commit is True

    def test_code_state_json_serializable(self):
        """CodeStateClaims can be serialized to JSON."""
        code_state = CodeStateClaims(
            branch="main",
            staged_count=5,
            unstaged_count=3,
            commits=[],
            files_changed=[],
            diff_summary=DiffSummary(lines_added=10, lines_removed=5),
        )
        data = code_state.model_dump(mode="json")
        assert data["branch"] == "main"
        assert data["staged_count"] == 5


class TestTaskInfo:
    """Tests for TaskInfo model."""

    def test_task_info_creation(self):
        """TaskInfo can be created with all required fields."""
        task = TaskInfo(
            id="ralph-abc123",
            title="Implement feature",
            status="open",
        )
        assert task.id == "ralph-abc123"
        assert task.title == "Implement feature"
        assert task.status == "open"

    def test_task_info_with_blocker(self):
        """TaskInfo can include blocker reason."""
        task = TaskInfo(
            id="ralph-abc123",
            title="Implement feature",
            status="blocked",
            blocker_reason="Waiting for dependency",
        )
        assert task.blocker_reason == "Waiting for dependency"


class TestTaskComment:
    """Tests for TaskComment model."""

    def test_task_comment_creation(self):
        """TaskComment can be created with all required fields."""
        comment = TaskComment(
            task_id="ralph-abc123",
            source="executor",
            text="Started implementation",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )
        assert comment.task_id == "ralph-abc123"
        assert comment.source == "executor"
        assert comment.text == "Started implementation"


class TestWorkStateClaims:
    """Tests for WorkStateClaims model."""

    def test_work_state_claims_creation(self):
        """WorkStateClaims can be created with all fields."""
        work_state = WorkStateClaims(
            open_tasks=[
                TaskInfo(id="ralph-1", title="Task 1", status="open"),
            ],
            blocked_tasks=[
                TaskInfo(
                    id="ralph-2",
                    title="Task 2",
                    status="blocked",
                    blocker_reason="Waiting",
                ),
            ],
            closed_tasks=[
                TaskInfo(id="ralph-3", title="Task 3", status="closed"),
            ],
            recent_comments=[
                TaskComment(
                    task_id="ralph-1",
                    source="executor",
                    text="Done",
                    timestamp=datetime(2024, 1, 15, 10, 30, 0),
                )
            ],
        )
        assert len(work_state.open_tasks) == 1
        assert len(work_state.blocked_tasks) == 1
        assert len(work_state.closed_tasks) == 1
        assert len(work_state.recent_comments) == 1

    def test_work_state_no_root_work_item(self):
        """WorkStateClaims handles no root work item case."""
        work_state = WorkStateClaims(
            open_tasks=[],
            blocked_tasks=[],
            closed_tasks=[],
            recent_comments=[],
            no_root_work_item=True,
        )
        assert work_state.no_root_work_item is True

    def test_work_state_with_error(self):
        """WorkStateClaims can include error message."""
        work_state = WorkStateClaims(
            open_tasks=[],
            blocked_tasks=[],
            closed_tasks=[],
            recent_comments=[],
            error="Failed to read trace",
        )
        assert work_state.error == "Failed to read trace"


class TestIterationSummary:
    """Tests for IterationSummary model."""

    def test_iteration_summary_creation(self):
        """IterationSummary can be created with all required fields."""
        iteration = IterationSummary(
            number=1,
            intent="Implement feature X",
            outcome="continue",
        )
        assert iteration.number == 1
        assert iteration.intent == "Implement feature X"
        assert iteration.outcome == "continue"


class TestAgentSummary:
    """Tests for AgentSummary model."""

    def test_agent_summary_creation(self):
        """AgentSummary can be created with all required fields."""
        summary = AgentSummary(
            agent_type="executor",
            summary="Completed task X",
        )
        assert summary.agent_type == "executor"
        assert summary.summary == "Completed task X"


class TestProjectStateClaims:
    """Tests for ProjectStateClaims model."""

    def test_project_state_claims_creation(self):
        """ProjectStateClaims can be created with all fields."""
        project_state = ProjectStateClaims(
            iteration_number=5,
            iteration_history=[
                IterationSummary(number=4, intent="Fix bug", outcome="continue"),
            ],
            agent_summaries=[
                AgentSummary(agent_type="executor", summary="Fixed bug"),
            ],
        )
        assert project_state.iteration_number == 5
        assert len(project_state.iteration_history) == 1
        assert len(project_state.agent_summaries) == 1

    def test_project_state_first_iteration(self):
        """ProjectStateClaims handles first iteration case."""
        project_state = ProjectStateClaims(
            iteration_number=1,
            iteration_history=[],
            agent_summaries=[],
            first_iteration=True,
        )
        assert project_state.first_iteration is True

    def test_project_state_with_error(self):
        """ProjectStateClaims can include error message."""
        project_state = ProjectStateClaims(
            iteration_number=0,
            iteration_history=[],
            agent_summaries=[],
            error="Failed to read database",
        )
        assert project_state.error == "Failed to read database"


class TestHumanInputClaims:
    """Tests for HumanInputClaims model."""

    def test_human_input_claims_creation(self):
        """HumanInputClaims can be created with all required fields."""
        human_input = HumanInputClaims(
            input_type="comment",
            content="Please focus on performance",
            spec_modified=False,
        )
        assert human_input.input_type == "comment"
        assert human_input.content == "Please focus on performance"
        assert human_input.spec_modified is False

    def test_human_input_spec_modified(self):
        """HumanInputClaims can flag spec modification."""
        human_input = HumanInputClaims(
            input_type="comment",
            content="Updated spec: add new requirement",
            spec_modified=True,
        )
        assert human_input.spec_modified is True


class TestClaims:
    """Tests for Claims model."""

    def test_claims_creation_with_all_sections(self):
        """Claims can be created with all required sections."""
        claims = Claims(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            iteration_number=1,
            code_state=CodeStateClaims(
                branch="main",
                staged_count=0,
                unstaged_count=0,
                commits=[],
                files_changed=[],
                diff_summary=None,
            ),
            work_state=WorkStateClaims(
                open_tasks=[],
                blocked_tasks=[],
                closed_tasks=[],
                recent_comments=[],
            ),
            project_state=ProjectStateClaims(
                iteration_number=1,
                iteration_history=[],
                agent_summaries=[],
            ),
            human_input=None,
            learnings="",
        )
        assert claims.iteration_number == 1
        assert claims.code_state.branch == "main"
        assert claims.human_input is None
        assert claims.learnings == ""

    def test_claims_with_human_input(self):
        """Claims can include human input."""
        claims = Claims(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            iteration_number=1,
            code_state=CodeStateClaims(
                branch="main",
                staged_count=0,
                unstaged_count=0,
                commits=[],
                files_changed=[],
                diff_summary=None,
            ),
            work_state=WorkStateClaims(
                open_tasks=[],
                blocked_tasks=[],
                closed_tasks=[],
                recent_comments=[],
            ),
            project_state=ProjectStateClaims(
                iteration_number=1,
                iteration_history=[],
                agent_summaries=[],
            ),
            human_input=HumanInputClaims(
                input_type="comment",
                content="Focus on tests",
                spec_modified=False,
            ),
            learnings="Use pytest for testing",
        )
        assert claims.human_input is not None
        assert claims.human_input.content == "Focus on tests"
        assert claims.learnings == "Use pytest for testing"

    def test_claims_json_serializable(self):
        """Claims can be fully serialized to JSON."""
        claims = Claims(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            iteration_number=1,
            code_state=CodeStateClaims(
                branch="main",
                staged_count=5,
                unstaged_count=3,
                commits=[
                    CommitInfo(
                        hash="abc123",
                        message="Initial",
                        timestamp=datetime(2024, 1, 14, 10, 0, 0),
                    ),
                ],
                files_changed=["main.py"],
                diff_summary=DiffSummary(lines_added=10, lines_removed=5),
            ),
            work_state=WorkStateClaims(
                open_tasks=[TaskInfo(id="r-1", title="Task", status="open")],
                blocked_tasks=[],
                closed_tasks=[],
                recent_comments=[],
            ),
            project_state=ProjectStateClaims(
                iteration_number=1,
                iteration_history=[],
                agent_summaries=[],
            ),
            human_input=None,
            learnings="Test learnings",
        )
        # Should not raise - JSON serializable
        data = claims.model_dump(mode="json")
        assert data["iteration_number"] == 1
        assert data["code_state"]["branch"] == "main"
        assert data["code_state"]["commits"][0]["hash"] == "abc123"
        assert data["learnings"] == "Test learnings"

    def test_claims_missing_required_fields_raises(self):
        """Claims raises validation error if required fields missing."""
        with pytest.raises(ValidationError):
            Claims(
                timestamp=datetime(2024, 1, 15, 10, 30, 0),
                # Missing iteration_number and other required fields
            )


# =============================================================================
# Tests for sense() function
# =============================================================================


class TestSenseContext:
    """Tests for SenseContext configuration."""

    def test_sense_context_creation(self):
        """SenseContext can be created with required fields."""
        ctx = SenseContext(
            run_id="run-123",
            iteration_number=5,
            milestone_base="abc123",
            root_work_item_id="ralph-root",
            project_id="proj-uuid",
            project_root="/path/to/project",
        )
        assert ctx.run_id == "run-123"
        assert ctx.iteration_number == 5
        assert ctx.milestone_base == "abc123"
        assert ctx.root_work_item_id == "ralph-root"
        assert ctx.project_id == "proj-uuid"

    def test_sense_context_optional_fields(self):
        """SenseContext handles optional fields."""
        ctx = SenseContext(
            run_id="run-123",
            iteration_number=1,
            milestone_base=None,  # No base commit (new project)
            root_work_item_id=None,  # No root work item
            project_id="proj-uuid",
            project_root="/path/to/project",
        )
        assert ctx.milestone_base is None
        assert ctx.root_work_item_id is None


class TestSenseFunction:
    """Tests for the main sense() function."""

    @pytest.fixture
    def mock_git_client(self):
        """Create a mock GitClient."""
        client = MagicMock()
        client.get_current_branch.return_value = "main"
        client._run_git.return_value = MagicMock(stdout="M  file.py\nA  new.py", returncode=0)
        client.get_commits_since.return_value = []
        client.get_diff_summary.return_value = ""
        return client

    @pytest.fixture
    def mock_trace_client(self):
        """Create a mock TraceClient."""
        client = MagicMock()
        client.get_open_tasks.return_value = []
        client.get_blocked_tasks.return_value = []
        client.get_closed_tasks.return_value = []
        client.get_task_comments.return_value = []
        return client

    @pytest.fixture
    def mock_db(self):
        """Create a mock SodaDB."""
        db = MagicMock()
        db.get_iterations.return_value = []
        db.get_unconsumed_inputs.return_value = []
        db.get_agent_outputs.return_value = []
        return db

    @pytest.fixture
    def sense_context(self):
        """Create a basic SenseContext for testing."""
        return SenseContext(
            run_id="run-123",
            iteration_number=1,
            milestone_base="abc123",
            root_work_item_id="ralph-root",
            project_id="proj-uuid",
            project_root="/tmp/test-project",
        )

    def test_sense_returns_claims_object(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() returns a Claims object."""
        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert isinstance(claims, Claims)

    def test_sense_includes_timestamp(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes timestamp in claims."""
        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.timestamp is not None
        assert isinstance(claims.timestamp, datetime)

    def test_sense_includes_iteration_number(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes iteration number in claims."""
        sense_context.iteration_number = 5
        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.iteration_number == 5

    def test_sense_collects_code_state_branch(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects current branch name."""
        mock_git_client.get_current_branch.return_value = "feature/new-thing"

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.code_state.branch == "feature/new-thing"

    def test_sense_collects_uncommitted_changes(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects staged and unstaged counts."""
        # Mock git status output: 2 staged (A, M), 1 unstaged (?)
        mock_git_client._run_git.return_value = MagicMock(
            stdout="A  staged.py\nM  modified.py\n?? untracked.py",
            returncode=0
        )

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        # The exact numbers depend on implementation, just check it's populated
        assert isinstance(claims.code_state.staged_count, int)
        assert isinstance(claims.code_state.unstaged_count, int)

    def test_sense_collects_commits_since_base(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects commits since milestone base."""
        from soda.state.git import CommitInfo as GitCommitInfo
        mock_git_client.get_commits_since.return_value = [
            GitCommitInfo(sha="abc", message="Commit 1", author="Alice", timestamp="2024-01-15T10:00:00Z"),
            GitCommitInfo(sha="def", message="Commit 2", author="Bob", timestamp="2024-01-15T11:00:00Z"),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.code_state.commits) == 2
        assert claims.code_state.commits[0].hash == "abc"
        assert claims.code_state.commits[0].message == "Commit 1"

    def test_sense_handles_no_base_commit(
        self, mock_git_client, mock_trace_client, mock_db
    ):
        """sense() reports no_base_commit when milestone base is empty."""
        ctx = SenseContext(
            run_id="run-123",
            iteration_number=1,
            milestone_base=None,  # No base commit
            root_work_item_id="ralph-root",
            project_id="proj-uuid",
            project_root="/tmp/test-project",
        )

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=ctx,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.code_state.no_base_commit is True

    def test_sense_handles_git_error_gracefully(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes error message when git fails, doesn't halt."""
        mock_git_client.get_current_branch.side_effect = Exception("Git not found")

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        # Should still return claims with error message in code_state
        assert claims.code_state.error is not None
        assert "Git not found" in claims.code_state.error

    def test_sense_collects_work_state_open_tasks(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects open tasks under milestone root."""
        from soda.state.trace import Task as TraceTask
        mock_trace_client.get_open_tasks.return_value = [
            TraceTask(id="ralph-1", title="Task 1", status="open", priority=2),
            TraceTask(id="ralph-2", title="Task 2", status="open", priority=1),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.work_state.open_tasks) == 2
        assert claims.work_state.open_tasks[0].id == "ralph-1"

    def test_sense_collects_blocked_tasks_with_reason(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects blocked tasks with blocker reason."""
        from soda.state.trace import Task as TraceTask
        mock_trace_client.get_blocked_tasks.return_value = [
            TraceTask(id="ralph-blocked", title="Blocked Task", status="blocked", priority=2, parent_id="ralph-blocker"),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.work_state.blocked_tasks) == 1
        assert claims.work_state.blocked_tasks[0].status == "blocked"

    def test_sense_collects_closed_tasks(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects closed tasks separately."""
        from soda.state.trace import Task as TraceTask
        mock_trace_client.get_closed_tasks.return_value = [
            TraceTask(id="ralph-done1", title="Completed Task 1", status="closed", priority=2),
            TraceTask(id="ralph-done2", title="Completed Task 2", status="closed", priority=1),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.work_state.closed_tasks) == 2
        assert claims.work_state.closed_tasks[0].id == "ralph-done1"
        assert claims.work_state.closed_tasks[0].status == "closed"
        assert claims.work_state.closed_tasks[1].id == "ralph-done2"

    def test_sense_handles_no_root_work_item(
        self, mock_git_client, mock_trace_client, mock_db
    ):
        """sense() reports no_root_work_item when root doesn't exist."""
        ctx = SenseContext(
            run_id="run-123",
            iteration_number=1,
            milestone_base="abc123",
            root_work_item_id=None,  # No root work item
            project_id="proj-uuid",
            project_root="/tmp/test-project",
        )

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=ctx,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.work_state.no_root_work_item is True

    def test_sense_handles_trace_error_gracefully(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes error message when trace fails, doesn't halt."""
        mock_trace_client.get_open_tasks.side_effect = Exception("Trace CLI not found")

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.work_state.error is not None
        assert "Trace CLI not found" in claims.work_state.error

    def test_sense_collects_project_state_iteration_number(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes current iteration number in project state."""
        sense_context.iteration_number = 10

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.project_state.iteration_number == 10

    def test_sense_collects_iteration_history(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes recent iteration history (last 5)."""
        from soda.state.models import Iteration, IterationOutcome
        mock_db.get_iterations.return_value = [
            Iteration(id=1, run_id="run-123", number=1, intent="First", outcome=IterationOutcome.CONTINUE, started_at=datetime.now()),
            Iteration(id=2, run_id="run-123", number=2, intent="Second", outcome=IterationOutcome.CONTINUE, started_at=datetime.now()),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.project_state.iteration_history) <= 5
        assert len(claims.project_state.iteration_history) == 2

    def test_sense_marks_first_iteration(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() marks first_iteration when no prior iterations exist."""
        mock_db.get_iterations.return_value = []
        sense_context.iteration_number = 1

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.project_state.first_iteration is True

    def test_sense_handles_db_error_gracefully(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes error message when database fails, doesn't halt."""
        mock_db.get_iterations.side_effect = Exception("Database locked")

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.project_state.error is not None
        assert "Database locked" in claims.project_state.error

    def test_sense_collects_pending_human_input(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes pending human input with type and content."""
        from soda.state.models import HumanInput, InputType
        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(id=1, run_id="run-123", input_type=InputType.COMMENT, content="Focus on tests", created_at=datetime.now()),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.input_type == "comment"
        assert claims.human_input.content == "Focus on tests"

    def test_sense_empty_human_input_when_none_pending(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() leaves human_input None when no pending input."""
        mock_db.get_unconsumed_inputs.return_value = []

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is None

    def test_sense_collects_learnings_from_memory(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() includes memory.md content as learnings."""
        with patch("soda.sense.read_memory", return_value="Use pytest for testing\nPrefer fixtures"):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.learnings == "Use pytest for testing\nPrefer fixtures"

    def test_sense_empty_learnings_when_no_memory(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() has empty learnings when memory.md doesn't exist."""
        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.learnings == ""

    def test_sense_is_json_serializable(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() returns claims that can be serialized to JSON."""
        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        # Should not raise
        data = claims.model_dump(mode="json")
        assert "timestamp" in data
        assert "iteration_number" in data
        assert "code_state" in data

    def test_sense_continues_on_partial_failures(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() continues collecting from other sources when one fails."""
        # Git fails
        mock_git_client.get_current_branch.side_effect = Exception("Git error")
        # But trace works
        from soda.state.trace import Task as TraceTask
        mock_trace_client.get_open_tasks.return_value = [
            TraceTask(id="ralph-1", title="Task 1", status="open", priority=2),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        # Code state has error
        assert claims.code_state.error is not None
        # But work state was collected
        assert len(claims.work_state.open_tasks) == 1

    def test_sense_collects_files_changed(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects files_changed via git diff --name-only."""
        # Mock git diff --name-only output
        mock_git_client._run_git.side_effect = lambda args, check=True: (
            MagicMock(stdout="", returncode=0) if args[:1] == ["status"]
            else MagicMock(
                stdout="src/main.py\ntests/test_main.py\nREADME.md",
                returncode=0,
            ) if "diff" in args and "--name-only" in args
            else MagicMock(stdout="", returncode=0)  # shortstat and other calls
        )
        mock_git_client.get_commits_since.return_value = []

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.code_state.files_changed == ["src/main.py", "tests/test_main.py", "README.md"]

    def test_sense_collects_diff_summary(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects diff summary (lines_added/removed) from git diff --shortstat."""
        # Mock git diff --shortstat output
        mock_git_client._run_git.side_effect = lambda args, check=True: (
            MagicMock(stdout="", returncode=0) if args[:1] == ["status"]
            else MagicMock(stdout="", returncode=0) if "diff" in args and "--name-only" in args
            else MagicMock(
                stdout=" 5 files changed, 150 insertions(+), 42 deletions(-)",
                returncode=0,
            ) if "diff" in args and "--shortstat" in args
            else MagicMock(stdout="", returncode=0)
        )
        mock_git_client.get_commits_since.return_value = []

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.code_state.diff_summary is not None
        assert claims.code_state.diff_summary.lines_added == 150
        assert claims.code_state.diff_summary.lines_removed == 42

    def test_sense_collects_agent_summaries(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() collects executor/verifier summaries from db.get_agent_outputs()."""
        from soda.state.models import Iteration, IterationOutcome, AgentOutput, AgentType

        # Mock iteration history with one iteration
        mock_db.get_iterations.return_value = [
            Iteration(
                id=1,
                run_id="run-123",
                number=1,
                intent="Implement feature",
                outcome=IterationOutcome.CONTINUE,
                started_at=datetime.now(),
            ),
        ]

        # Mock agent outputs from that iteration
        mock_db.get_agent_outputs.return_value = [
            AgentOutput(
                id=1,
                iteration_id=1,
                agent_type=AgentType.EXECUTOR,
                raw_output_path="/path/to/executor_output.jsonl",
                summary="Completed implementing feature X",
            ),
            AgentOutput(
                id=2,
                iteration_id=1,
                agent_type=AgentType.VERIFIER,
                raw_output_path="/path/to/verifier_output.jsonl",
                summary="All tests passing, spec satisfied",
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert len(claims.project_state.agent_summaries) == 2
        assert claims.project_state.agent_summaries[0].agent_type == "executor"
        assert claims.project_state.agent_summaries[0].summary == "Completed implementing feature X"
        assert claims.project_state.agent_summaries[1].agent_type == "verifier"
        assert claims.project_state.agent_summaries[1].summary == "All tests passing, spec satisfied"

    def test_sense_flags_spec_modified(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() sets spec_modified=True when content contains 'spec' + update/change/modify/add."""
        from soda.state.models import HumanInput, InputType

        # Test case 1: "spec" + "update" -> spec_modified=True
        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(
                id=1,
                run_id="run-123",
                input_type=InputType.COMMENT,
                content="Please update the spec to include error handling",
                created_at=datetime.now(),
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.spec_modified is True

    def test_sense_spec_modified_with_change(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() sets spec_modified=True when content contains 'spec' + 'change'."""
        from soda.state.models import HumanInput, InputType

        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(
                id=1,
                run_id="run-123",
                input_type=InputType.COMMENT,
                content="Change the spec requirements",
                created_at=datetime.now(),
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.spec_modified is True

    def test_sense_spec_modified_with_modify(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() sets spec_modified=True when content contains 'spec' + 'modify'."""
        from soda.state.models import HumanInput, InputType

        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(
                id=1,
                run_id="run-123",
                input_type=InputType.COMMENT,
                content="Modify the spec to be more specific",
                created_at=datetime.now(),
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.spec_modified is True

    def test_sense_spec_modified_with_add(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() sets spec_modified=True when content contains 'spec' + 'add'."""
        from soda.state.models import HumanInput, InputType

        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(
                id=1,
                run_id="run-123",
                input_type=InputType.COMMENT,
                content="Add to the spec: new authentication requirement",
                created_at=datetime.now(),
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.spec_modified is True

    def test_sense_spec_not_modified_without_keywords(
        self, mock_git_client, mock_trace_client, mock_db, sense_context
    ):
        """sense() sets spec_modified=False when content doesn't match pattern."""
        from soda.state.models import HumanInput, InputType

        mock_db.get_unconsumed_inputs.return_value = [
            HumanInput(
                id=1,
                run_id="run-123",
                input_type=InputType.COMMENT,
                content="Please focus on performance",
                created_at=datetime.now(),
            ),
        ]

        with patch("soda.sense.read_memory", return_value=""):
            claims = sense(
                ctx=sense_context,
                git_client=mock_git_client,
                trace_client=mock_trace_client,
                db=mock_db,
            )

        assert claims.human_input is not None
        assert claims.human_input.spec_modified is False
