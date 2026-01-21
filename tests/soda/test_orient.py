"""Tests for ORIENT data structures and orient() function."""

from unittest.mock import AsyncMock, patch
import pytest
from pydantic import ValidationError

from soda.orient import (
    Confidence,
    Gap,
    GapSeverity,
    IterationPlan,
    Learning,
    NewTask,
    OrientContext,
    OrientOutput,
    PlannedTask,
    SpecSatisfied,
    TaskUpdate,
    TaskUpdateType,
    orient,
    ORIENT_SYSTEM_PROMPT,
)
from soda.sense import Claims, CodeStateClaims, WorkStateClaims, ProjectStateClaims


# =============================================================================
# SpecSatisfied Enum Tests
# =============================================================================


class TestSpecSatisfied:
    """Tests for SpecSatisfied enum."""

    def test_true_value(self):
        """TRUE value exists and equals 'true'."""
        assert SpecSatisfied.TRUE.value == "true"

    def test_false_value(self):
        """FALSE value exists and equals 'false'."""
        assert SpecSatisfied.FALSE.value == "false"

    def test_unverifiable_value(self):
        """UNVERIFIABLE value exists and equals 'unverifiable'."""
        assert SpecSatisfied.UNVERIFIABLE.value == "unverifiable"

    def test_spec_satisfied_is_string_enum(self):
        """SpecSatisfied is a string enum for easy comparison."""
        assert SpecSatisfied.TRUE == "true"
        assert SpecSatisfied.FALSE == "false"
        assert SpecSatisfied.UNVERIFIABLE == "unverifiable"


# =============================================================================
# Confidence Enum Tests
# =============================================================================


class TestConfidence:
    """Tests for Confidence enum."""

    def test_high_value(self):
        """HIGH value exists and equals 'high'."""
        assert Confidence.HIGH.value == "high"

    def test_medium_value(self):
        """MEDIUM value exists and equals 'medium'."""
        assert Confidence.MEDIUM.value == "medium"

    def test_low_value(self):
        """LOW value exists and equals 'low'."""
        assert Confidence.LOW.value == "low"

    def test_confidence_is_string_enum(self):
        """Confidence is a string enum for easy comparison."""
        assert Confidence.HIGH == "high"
        assert Confidence.MEDIUM == "medium"
        assert Confidence.LOW == "low"


# =============================================================================
# TaskUpdateType Enum Tests
# =============================================================================


class TestTaskUpdateType:
    """Tests for TaskUpdateType enum."""

    def test_close_value(self):
        """CLOSE value exists."""
        assert TaskUpdateType.CLOSE.value == "close"

    def test_update_value(self):
        """UPDATE value exists."""
        assert TaskUpdateType.UPDATE.value == "update"

    def test_block_value(self):
        """BLOCK value exists."""
        assert TaskUpdateType.BLOCK.value == "block"

    def test_unblock_value(self):
        """UNBLOCK value exists."""
        assert TaskUpdateType.UNBLOCK.value == "unblock"


# =============================================================================
# GapSeverity Enum Tests
# =============================================================================


class TestGapSeverity:
    """Tests for GapSeverity enum."""

    def test_critical_value(self):
        """CRITICAL value exists."""
        assert GapSeverity.CRITICAL.value == "critical"

    def test_major_value(self):
        """MAJOR value exists."""
        assert GapSeverity.MAJOR.value == "major"

    def test_minor_value(self):
        """MINOR value exists."""
        assert GapSeverity.MINOR.value == "minor"


# =============================================================================
# TaskUpdate Model Tests
# =============================================================================


class TestTaskUpdate:
    """Tests for TaskUpdate model."""

    def test_task_update_close_operation(self):
        """TaskUpdate can represent a close operation."""
        update = TaskUpdate(
            task_id="ralph-abc123",
            update_type=TaskUpdateType.CLOSE,
            comment="Verified: code implementation matches spec",
        )
        assert update.task_id == "ralph-abc123"
        assert update.update_type == TaskUpdateType.CLOSE
        assert update.comment == "Verified: code implementation matches spec"

    def test_task_update_update_operation_with_priority(self):
        """TaskUpdate can represent an update operation with priority."""
        update = TaskUpdate(
            task_id="ralph-xyz789",
            update_type=TaskUpdateType.UPDATE,
            priority=0,  # P0 highest priority
        )
        assert update.task_id == "ralph-xyz789"
        assert update.update_type == TaskUpdateType.UPDATE
        assert update.priority == 0

    def test_task_update_block_operation(self):
        """TaskUpdate can represent a block operation."""
        update = TaskUpdate(
            task_id="ralph-def456",
            update_type=TaskUpdateType.BLOCK,
            blocker_reason="Waiting for API key configuration",
        )
        assert update.update_type == TaskUpdateType.BLOCK
        assert update.blocker_reason == "Waiting for API key configuration"

    def test_task_update_unblock_operation(self):
        """TaskUpdate can represent an unblock operation."""
        update = TaskUpdate(
            task_id="ralph-def456",
            update_type=TaskUpdateType.UNBLOCK,
            comment="Blocker resolved - API key now available",
        )
        assert update.update_type == TaskUpdateType.UNBLOCK
        assert update.comment is not None

    def test_task_update_minimal(self):
        """TaskUpdate requires only task_id and update_type."""
        update = TaskUpdate(
            task_id="ralph-min123",
            update_type=TaskUpdateType.CLOSE,
        )
        assert update.task_id == "ralph-min123"
        assert update.comment is None
        assert update.priority is None
        assert update.blocker_reason is None

    def test_task_update_json_serializable(self):
        """TaskUpdate can be serialized to JSON."""
        update = TaskUpdate(
            task_id="ralph-json123",
            update_type=TaskUpdateType.CLOSE,
            comment="Done",
        )
        data = update.model_dump(mode="json")
        assert data["task_id"] == "ralph-json123"
        assert data["update_type"] == "close"
        assert data["comment"] == "Done"

    def test_task_update_from_string_type(self):
        """TaskUpdate can be created with string update_type."""
        update = TaskUpdate(
            task_id="ralph-str123",
            update_type="block",
            blocker_reason="Test reason",
        )
        assert update.update_type == TaskUpdateType.BLOCK


# =============================================================================
# NewTask Model Tests
# =============================================================================


class TestNewTask:
    """Tests for NewTask model."""

    def test_new_task_creation(self):
        """NewTask can be created with required fields."""
        task = NewTask(
            title="Implement feature X",
            description="Add feature X to handle user authentication",
        )
        assert task.title == "Implement feature X"
        assert task.description == "Add feature X to handle user authentication"
        assert task.priority == 1  # default

    def test_new_task_with_priority(self):
        """NewTask can have custom priority."""
        task = NewTask(
            title="Critical bug fix",
            description="Fix security vulnerability",
            priority=0,  # P0
        )
        assert task.priority == 0

    def test_new_task_with_parent(self):
        """NewTask can have parent_id for subtasks."""
        task = NewTask(
            title="Subtask: Write tests",
            description="Write unit tests for feature X",
            parent_id="ralph-parent123",
        )
        assert task.parent_id == "ralph-parent123"

    def test_new_task_with_blocker(self):
        """NewTask can be blocked by another task."""
        task = NewTask(
            title="Implement API client",
            description="Need API key from task X first",
            blocked_by="ralph-prereq456",
        )
        assert task.blocked_by == "ralph-prereq456"

    def test_new_task_priority_bounds(self):
        """NewTask priority must be 0-2."""
        # Valid priorities
        NewTask(title="P0", description="desc", priority=0)
        NewTask(title="P1", description="desc", priority=1)
        NewTask(title="P2", description="desc", priority=2)

        # Invalid priority
        with pytest.raises(ValidationError):
            NewTask(title="Invalid", description="desc", priority=3)

        with pytest.raises(ValidationError):
            NewTask(title="Invalid", description="desc", priority=-1)

    def test_new_task_json_serializable(self):
        """NewTask can be serialized to JSON."""
        task = NewTask(
            title="Test task",
            description="Test description",
            priority=1,
            parent_id="ralph-parent",
        )
        data = task.model_dump(mode="json")
        assert data["title"] == "Test task"
        assert data["priority"] == 1
        assert data["parent_id"] == "ralph-parent"


# =============================================================================
# Gap Model Tests
# =============================================================================


class TestGap:
    """Tests for Gap model."""

    def test_gap_creation(self):
        """Gap can be created with required fields."""
        gap = Gap(
            description="Missing unit tests for authentication module",
            severity=GapSeverity.MAJOR,
        )
        assert gap.description == "Missing unit tests for authentication module"
        assert gap.severity == GapSeverity.MAJOR

    def test_gap_with_criterion_ref(self):
        """Gap can reference an acceptance criterion."""
        gap = Gap(
            description="Login feature not implemented",
            severity=GapSeverity.CRITICAL,
            criterion_ref="When user clicks login, then auth flow starts",
        )
        assert gap.criterion_ref is not None

    def test_gap_with_related_task(self):
        """Gap can reference a related task."""
        gap = Gap(
            description="Test coverage below threshold",
            severity=GapSeverity.MINOR,
            related_task_id="ralph-coverage123",
        )
        assert gap.related_task_id == "ralph-coverage123"

    def test_gap_with_suggested_action(self):
        """Gap can include suggested action."""
        gap = Gap(
            description="API rate limiting not implemented",
            severity=GapSeverity.MAJOR,
            suggested_action="Add rate limiter middleware before route handlers",
        )
        assert gap.suggested_action is not None

    def test_gap_all_fields(self):
        """Gap with all optional fields populated."""
        gap = Gap(
            description="Full gap example",
            severity=GapSeverity.CRITICAL,
            criterion_ref="AC-001",
            related_task_id="ralph-related",
            suggested_action="Fix immediately",
        )
        assert gap.description == "Full gap example"
        assert gap.severity == GapSeverity.CRITICAL
        assert gap.criterion_ref == "AC-001"
        assert gap.related_task_id == "ralph-related"
        assert gap.suggested_action == "Fix immediately"

    def test_gap_json_serializable(self):
        """Gap can be serialized to JSON."""
        gap = Gap(
            description="Test gap",
            severity=GapSeverity.MINOR,
        )
        data = gap.model_dump(mode="json")
        assert data["description"] == "Test gap"
        assert data["severity"] == "minor"

    def test_gap_from_string_severity(self):
        """Gap can be created with string severity."""
        gap = Gap(
            description="String severity test",
            severity="critical",
        )
        assert gap.severity == GapSeverity.CRITICAL


# =============================================================================
# PlannedTask Model Tests
# =============================================================================


class TestPlannedTask:
    """Tests for PlannedTask model."""

    def test_planned_task_creation(self):
        """PlannedTask can be created with required fields."""
        planned = PlannedTask(
            task_id="ralph-plan123",
            title="Implement feature X",
            rationale="Highest priority P0 task addressing critical gap",
        )
        assert planned.task_id == "ralph-plan123"
        assert planned.title == "Implement feature X"
        assert planned.rationale is not None

    def test_planned_task_json_serializable(self):
        """PlannedTask can be serialized to JSON."""
        planned = PlannedTask(
            task_id="ralph-ser",
            title="Serialize test",
            rationale="Testing serialization",
        )
        data = planned.model_dump(mode="json")
        assert data["task_id"] == "ralph-ser"
        assert data["title"] == "Serialize test"


# =============================================================================
# IterationPlan Model Tests
# =============================================================================


class TestIterationPlan:
    """Tests for IterationPlan model."""

    def test_iteration_plan_creation(self):
        """IterationPlan can be created with required fields."""
        plan = IterationPlan(
            intent="Complete authentication module implementation",
            tasks=[
                PlannedTask(
                    task_id="ralph-auth1",
                    title="Add login endpoint",
                    rationale="Core feature needed for auth",
                ),
            ],
            approach="Implement login first, then add tests, then integrate",
        )
        assert plan.intent is not None
        assert len(plan.tasks) == 1
        assert plan.approach is not None

    def test_iteration_plan_empty_tasks(self):
        """IterationPlan can have empty tasks list."""
        plan = IterationPlan(
            intent="No work needed this iteration",
            tasks=[],
            approach="Monitor and verify",
        )
        assert plan.tasks == []

    def test_iteration_plan_with_estimated_scope(self):
        """IterationPlan can have estimated scope."""
        plan = IterationPlan(
            intent="Large refactoring",
            tasks=[],
            approach="Incremental changes",
            estimated_scope="large",
        )
        assert plan.estimated_scope == "large"

    def test_iteration_plan_multiple_tasks(self):
        """IterationPlan can have multiple tasks ordered by priority."""
        plan = IterationPlan(
            intent="Complete milestone",
            tasks=[
                PlannedTask(
                    task_id="ralph-p0",
                    title="P0 task",
                    rationale="Highest priority",
                ),
                PlannedTask(
                    task_id="ralph-p1",
                    title="P1 task",
                    rationale="Second priority",
                ),
                PlannedTask(
                    task_id="ralph-p2",
                    title="P2 task",
                    rationale="Lowest priority",
                ),
            ],
            approach="Work through in order",
        )
        assert len(plan.tasks) == 3
        assert plan.tasks[0].task_id == "ralph-p0"

    def test_iteration_plan_json_serializable(self):
        """IterationPlan can be serialized to JSON."""
        plan = IterationPlan(
            intent="Test intent",
            tasks=[],
            approach="Test approach",
            estimated_scope="small",
        )
        data = plan.model_dump(mode="json")
        assert data["intent"] == "Test intent"
        assert data["tasks"] == []
        assert data["approach"] == "Test approach"


# =============================================================================
# Learning Model Tests
# =============================================================================


class TestLearning:
    """Tests for Learning model."""

    def test_learning_preserve(self):
        """Learning can be created with preserve action."""
        learning = Learning(
            content="Run tests with: uv run pytest tests/ -v",
            action="preserve",
        )
        assert learning.content is not None
        assert learning.action == "preserve"
        assert learning.reason is None

    def test_learning_deprecate_with_reason(self):
        """Learning deprecate should have reason."""
        learning = Learning(
            content="Outdated API endpoint",
            action="deprecate",
            reason="API v1 deprecated, now using v2",
        )
        assert learning.action == "deprecate"
        assert learning.reason is not None

    def test_learning_action_literal(self):
        """Learning action must be preserve or deprecate."""
        Learning(content="Valid", action="preserve")
        Learning(content="Valid", action="deprecate")

        with pytest.raises(ValidationError):
            Learning(content="Invalid", action="invalid")

    def test_learning_json_serializable(self):
        """Learning can be serialized to JSON."""
        learning = Learning(
            content="Test content",
            action="preserve",
        )
        data = learning.model_dump(mode="json")
        assert data["content"] == "Test content"
        assert data["action"] == "preserve"


# =============================================================================
# OrientOutput Model Tests
# =============================================================================


class TestOrientOutput:
    """Tests for OrientOutput model."""

    def test_orient_output_spec_satisfied_true(self):
        """OrientOutput with spec_satisfied=true."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All acceptance criteria verified",
        )
        assert output.spec_satisfied == SpecSatisfied.TRUE
        assert output.actionable_work_exists is False
        assert output.confidence == Confidence.HIGH
        assert output.summary is not None

    def test_orient_output_spec_satisfied_false_with_work(self):
        """OrientOutput with spec_satisfied=false and actionable work."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
            gaps=[
                Gap(
                    description="Missing tests",
                    severity=GapSeverity.MAJOR,
                )
            ],
            iteration_plan=IterationPlan(
                intent="Add missing tests",
                tasks=[],
                approach="TDD approach",
            ),
        )
        assert output.spec_satisfied == SpecSatisfied.FALSE
        assert output.actionable_work_exists is True
        assert len(output.gaps) == 1

    def test_orient_output_spec_unverifiable(self):
        """OrientOutput with spec_satisfied=unverifiable."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.UNVERIFIABLE,
            actionable_work_exists=False,
            confidence=Confidence.LOW,
            gaps=[
                Gap(
                    description="Requires external API",
                    severity=GapSeverity.CRITICAL,
                )
            ],
        )
        assert output.spec_satisfied == SpecSatisfied.UNVERIFIABLE

    def test_orient_output_with_task_updates(self):
        """OrientOutput with task updates."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            task_updates=[
                TaskUpdate(
                    task_id="ralph-done1",
                    update_type=TaskUpdateType.CLOSE,
                    comment="Verified complete",
                ),
                TaskUpdate(
                    task_id="ralph-unblock1",
                    update_type=TaskUpdateType.UNBLOCK,
                ),
            ],
        )
        assert len(output.task_updates) == 2

    def test_orient_output_with_new_tasks(self):
        """OrientOutput with new tasks to create."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
            new_tasks=[
                NewTask(
                    title="Add error handling",
                    description="Handle network errors gracefully",
                    priority=1,
                ),
            ],
        )
        assert len(output.new_tasks) == 1

    def test_orient_output_with_learnings(self):
        """OrientOutput with learnings."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="Complete",
            learnings=[
                Learning(content="New pattern discovered", action="preserve"),
                Learning(
                    content="Outdated info",
                    action="deprecate",
                    reason="No longer accurate",
                ),
            ],
        )
        assert len(output.learnings) == 2

    def test_orient_output_minimal(self):
        """OrientOutput with only required fields."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.LOW,
        )
        assert output.task_updates == []
        assert output.new_tasks == []
        assert output.gaps == []
        assert output.iteration_plan is None
        assert output.learnings == []
        assert output.summary is None

    def test_orient_output_from_string_enums(self):
        """OrientOutput can be created with string enum values."""
        output = OrientOutput(
            spec_satisfied="false",
            actionable_work_exists=True,
            confidence="medium",
        )
        assert output.spec_satisfied == SpecSatisfied.FALSE
        assert output.confidence == Confidence.MEDIUM

    def test_orient_output_json_serializable(self):
        """OrientOutput can be serialized to JSON."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All done",
            gaps=[
                Gap(description="Minor issue", severity=GapSeverity.MINOR),
            ],
            learnings=[
                Learning(content="Useful tip", action="preserve"),
            ],
        )
        data = output.model_dump(mode="json")
        assert data["spec_satisfied"] == "true"
        assert data["actionable_work_exists"] is False
        assert data["confidence"] == "high"
        assert data["summary"] == "All done"
        assert len(data["gaps"]) == 1
        assert data["gaps"][0]["severity"] == "minor"

    def test_orient_output_full_example(self):
        """OrientOutput with all fields populated (realistic example)."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            task_updates=[
                TaskUpdate(
                    task_id="ralph-verify1",
                    update_type=TaskUpdateType.CLOSE,
                    comment="Code verified - implements spec correctly",
                ),
            ],
            new_tasks=[
                NewTask(
                    title="Add integration tests",
                    description="Integration tests needed for API endpoints",
                    priority=1,
                ),
            ],
            gaps=[
                Gap(
                    description="Missing integration tests",
                    severity=GapSeverity.MAJOR,
                    criterion_ref="All acceptance criteria have passing tests",
                    suggested_action="Add integration test suite",
                ),
            ],
            iteration_plan=IterationPlan(
                intent="Add missing integration tests for API",
                tasks=[
                    PlannedTask(
                        task_id="ralph-new1",
                        title="Add integration tests",
                        rationale="Addresses major gap in test coverage",
                    ),
                ],
                approach="Create test fixtures, then write tests for each endpoint",
                estimated_scope="medium",
            ),
            learnings=[
                Learning(
                    content="API tests require test database setup",
                    action="preserve",
                ),
            ],
            summary=None,  # Not satisfied yet
        )
        assert output.spec_satisfied == SpecSatisfied.FALSE
        assert output.actionable_work_exists is True
        assert len(output.task_updates) == 1
        assert len(output.new_tasks) == 1
        assert len(output.gaps) == 1
        assert output.iteration_plan is not None
        assert len(output.iteration_plan.tasks) == 1

    def test_orient_output_invalid_spec_satisfied_raises(self):
        """OrientOutput with invalid spec_satisfied raises error."""
        with pytest.raises(ValidationError):
            OrientOutput(
                spec_satisfied="invalid",
                actionable_work_exists=True,
                confidence=Confidence.HIGH,
            )

    def test_orient_output_invalid_confidence_raises(self):
        """OrientOutput with invalid confidence raises error."""
        with pytest.raises(ValidationError):
            OrientOutput(
                spec_satisfied=SpecSatisfied.FALSE,
                actionable_work_exists=True,
                confidence="invalid",
            )


# =============================================================================
# OrientContext Model Tests
# =============================================================================


class TestOrientContext:
    """Tests for OrientContext model."""

    def test_orient_context_creation(self):
        """OrientContext can be created with required fields."""
        from datetime import datetime

        claims = Claims(
            timestamp=datetime.now(),
            iteration_number=1,
            code_state=CodeStateClaims(),
            work_state=WorkStateClaims(),
            project_state=ProjectStateClaims(iteration_number=1),
        )
        ctx = OrientContext(
            claims=claims,
            spec="Test spec content",
            iteration_history=[],
        )
        assert ctx.claims == claims
        assert ctx.spec == "Test spec content"
        assert ctx.iteration_history == []

    def test_orient_context_with_iteration_history(self):
        """OrientContext can include iteration history."""
        from datetime import datetime

        claims = Claims(
            timestamp=datetime.now(),
            iteration_number=3,
            code_state=CodeStateClaims(),
            work_state=WorkStateClaims(),
            project_state=ProjectStateClaims(iteration_number=3),
        )
        history = [
            {"number": 1, "intent": "Setup project", "outcome": "CONTINUE"},
            {"number": 2, "intent": "Implement feature X", "outcome": "CONTINUE"},
        ]
        ctx = OrientContext(
            claims=claims,
            spec="Test spec",
            iteration_history=history,
        )
        assert len(ctx.iteration_history) == 2
        assert ctx.iteration_history[0]["intent"] == "Setup project"

    def test_orient_context_with_root_work_item(self):
        """OrientContext can include root work item ID."""
        from datetime import datetime

        claims = Claims(
            timestamp=datetime.now(),
            iteration_number=1,
            code_state=CodeStateClaims(),
            work_state=WorkStateClaims(),
            project_state=ProjectStateClaims(iteration_number=1),
        )
        ctx = OrientContext(
            claims=claims,
            spec="Test spec",
            iteration_history=[],
            root_work_item_id="ralph-abc123",
        )
        assert ctx.root_work_item_id == "ralph-abc123"

    def test_orient_context_json_serializable(self):
        """OrientContext can be serialized to JSON."""
        from datetime import datetime

        claims = Claims(
            timestamp=datetime.now(),
            iteration_number=1,
            code_state=CodeStateClaims(),
            work_state=WorkStateClaims(),
            project_state=ProjectStateClaims(iteration_number=1),
        )
        ctx = OrientContext(
            claims=claims,
            spec="Test spec",
            iteration_history=[],
        )
        data = ctx.model_dump(mode="json")
        assert data["spec"] == "Test spec"
        assert "claims" in data


# =============================================================================
# ORIENT_SYSTEM_PROMPT Tests
# =============================================================================


class TestOrientSystemPrompt:
    """Tests for ORIENT_SYSTEM_PROMPT."""

    def test_orient_system_prompt_exists(self):
        """ORIENT_SYSTEM_PROMPT is defined."""
        assert ORIENT_SYSTEM_PROMPT is not None
        assert isinstance(ORIENT_SYSTEM_PROMPT, str)

    def test_orient_system_prompt_includes_verification_guidance(self):
        """ORIENT_SYSTEM_PROMPT includes guidance for claim verification."""
        assert "verify" in ORIENT_SYSTEM_PROMPT.lower() or "claim" in ORIENT_SYSTEM_PROMPT.lower()

    def test_orient_system_prompt_includes_spec_assessment(self):
        """ORIENT_SYSTEM_PROMPT includes guidance for spec assessment."""
        assert "spec" in ORIENT_SYSTEM_PROMPT.lower()
        assert "criterion" in ORIENT_SYSTEM_PROMPT.lower() or "criteria" in ORIENT_SYSTEM_PROMPT.lower()

    def test_orient_system_prompt_includes_task_management(self):
        """ORIENT_SYSTEM_PROMPT includes guidance for task management."""
        assert "task" in ORIENT_SYSTEM_PROMPT.lower()

    def test_orient_system_prompt_includes_iteration_planning(self):
        """ORIENT_SYSTEM_PROMPT includes guidance for iteration planning."""
        assert "plan" in ORIENT_SYSTEM_PROMPT.lower() or "iteration" in ORIENT_SYSTEM_PROMPT.lower()


# =============================================================================
# orient() Function Tests
# =============================================================================


class TestOrientFunction:
    """Tests for orient() async function."""

    @pytest.fixture
    def sample_claims(self):
        """Create sample claims for testing."""
        from datetime import datetime

        return Claims(
            timestamp=datetime.now(),
            iteration_number=1,
            code_state=CodeStateClaims(
                branch="feature/test",
                staged_count=0,
                unstaged_count=0,
            ),
            work_state=WorkStateClaims(
                open_tasks=[],
                blocked_tasks=[],
                closed_tasks=[],
            ),
            project_state=ProjectStateClaims(
                iteration_number=1,
                first_iteration=True,
            ),
        )

    @pytest.fixture
    def sample_context(self, sample_claims):
        """Create sample OrientContext for testing."""
        return OrientContext(
            claims=sample_claims,
            spec="# Test Spec\n\n## Acceptance Criteria\n- [ ] Feature X implemented",
            iteration_history=[],
        )

    @pytest.fixture
    def mock_orient_output(self):
        """Create a mock OrientOutput for testing."""
        return OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            task_updates=[],
            new_tasks=[],
            gaps=[
                Gap(
                    description="Feature X not implemented",
                    severity=GapSeverity.MAJOR,
                )
            ],
            iteration_plan=IterationPlan(
                intent="Implement Feature X",
                tasks=[],
                approach="TDD approach",
            ),
            learnings=[],
        )

    @pytest.mark.asyncio
    async def test_orient_returns_orient_output(self, sample_context, mock_orient_output):
        """orient() returns an OrientOutput."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            result = await orient(sample_context)

            assert isinstance(result, OrientOutput)

    @pytest.mark.asyncio
    async def test_orient_uses_narrow_agent(self, sample_context, mock_orient_output):
        """orient() uses NarrowAgent for agent invocation."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            mock_agent_class.assert_called_once()
            mock_agent.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_orient_passes_system_prompt_to_agent(self, sample_context, mock_orient_output):
        """orient() passes ORIENT_SYSTEM_PROMPT to NarrowAgent."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            # Check that invoke was called with system_prompt
            call_kwargs = mock_agent.invoke.call_args.kwargs
            assert "system_prompt" in call_kwargs
            assert call_kwargs["system_prompt"] == ORIENT_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_orient_uses_orient_output_schema(self, sample_context, mock_orient_output):
        """orient() passes OrientOutput as output_schema to NarrowAgent."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            call_kwargs = mock_agent.invoke.call_args.kwargs
            assert "output_schema" in call_kwargs
            assert call_kwargs["output_schema"] == OrientOutput

    @pytest.mark.asyncio
    async def test_orient_includes_claims_in_prompt(self, sample_context, mock_orient_output):
        """orient() includes claims information in the prompt."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            call_kwargs = mock_agent.invoke.call_args.kwargs
            prompt = call_kwargs.get("prompt", "")
            # The prompt should contain claims information
            assert "Claims" in prompt or "claims" in prompt or "iteration" in prompt.lower()

    @pytest.mark.asyncio
    async def test_orient_includes_spec_in_prompt(self, sample_context, mock_orient_output):
        """orient() includes spec in the prompt."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            call_kwargs = mock_agent.invoke.call_args.kwargs
            prompt = call_kwargs.get("prompt", "")
            # The prompt should contain the spec
            assert "Test Spec" in prompt or "Feature X" in prompt

    @pytest.mark.asyncio
    async def test_orient_with_allowed_tools(self, sample_context, mock_orient_output):
        """orient() specifies allowed tools for the agent."""
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=mock_orient_output)
            mock_agent_class.return_value = mock_agent

            await orient(sample_context)

            call_kwargs = mock_agent.invoke.call_args.kwargs
            # ORIENT should have read-only tools plus Bash for tests
            assert "tools" in call_kwargs
            tools = call_kwargs["tools"]
            # Should include read-only codebase access
            assert "Read" in tools or "Glob" in tools or "Grep" in tools

    @pytest.mark.asyncio
    async def test_orient_spec_satisfied_true(self, sample_context):
        """orient() can return spec_satisfied=true."""
        satisfied_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All acceptance criteria verified",
        )
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=satisfied_output)
            mock_agent_class.return_value = mock_agent

            result = await orient(sample_context)

            assert result.spec_satisfied == SpecSatisfied.TRUE
            assert result.actionable_work_exists is False

    @pytest.mark.asyncio
    async def test_orient_spec_satisfied_unverifiable(self, sample_context):
        """orient() can return spec_satisfied=unverifiable."""
        unverifiable_output = OrientOutput(
            spec_satisfied=SpecSatisfied.UNVERIFIABLE,
            actionable_work_exists=False,
            confidence=Confidence.LOW,
            gaps=[
                Gap(
                    description="Requires external API access",
                    severity=GapSeverity.CRITICAL,
                )
            ],
        )
        with patch("soda.orient.NarrowAgent") as mock_agent_class:
            mock_agent = AsyncMock()
            mock_agent.invoke = AsyncMock(return_value=unverifiable_output)
            mock_agent_class.return_value = mock_agent

            result = await orient(sample_context)

            assert result.spec_satisfied == SpecSatisfied.UNVERIFIABLE
