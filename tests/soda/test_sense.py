"""Tests for SENSE data structures (Claims)."""

from datetime import datetime

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
