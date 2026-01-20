"""Tests for ORIENT data structures."""

import pytest
from pydantic import ValidationError

from soda.orient import (
    Confidence,
    Gap,
    GapSeverity,
    IterationPlan,
    Learning,
    NewTask,
    OrientOutput,
    PlannedTask,
    SpecSatisfied,
    TaskUpdate,
    TaskUpdateType,
)


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
# orient() Function Tests
# =============================================================================


class TestOrientContext:
    """Tests for OrientContext model."""

    def test_orient_context_creation(self):
        """OrientContext can be created with all required fields."""
        from soda.orient import OrientContext

        ctx = OrientContext(
            spec_content="# Test Spec\n## Acceptance Criteria\n- [ ] Feature works",
            claims_json='{"iteration_number": 1}',
            root_work_item_id="ralph-root123",
            learnings="Test learnings",
        )
        assert ctx.spec_content is not None
        assert ctx.claims_json is not None
        assert ctx.root_work_item_id == "ralph-root123"
        assert ctx.learnings == "Test learnings"

    def test_orient_context_optional_fields(self):
        """OrientContext can be created with minimal fields."""
        from soda.orient import OrientContext

        ctx = OrientContext(
            spec_content="# Test Spec",
            claims_json="{}",
        )
        assert ctx.root_work_item_id is None
        assert ctx.learnings == ""


class TestOrientFunction:
    """Tests for orient() function."""

    @pytest.mark.asyncio
    async def test_orient_returns_orient_output(self):
        """orient() returns OrientOutput instance."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        # Create context
        ctx = OrientContext(
            spec_content="# Test Spec\n## Acceptance Criteria\n- [ ] Feature X works",
            claims_json='{"iteration_number": 1, "code_state": {}, "work_state": {}}',
            root_work_item_id="ralph-root123",
        )

        # Mock the NarrowAgent
        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            iteration_plan=IterationPlan(
                intent="Implement feature X",
                tasks=[],
                approach="TDD approach",
            ),
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            result = await orient(ctx)

            assert isinstance(result, OrientOutput)
            assert result.spec_satisfied == SpecSatisfied.FALSE
            assert result.actionable_work_exists is True

    @pytest.mark.asyncio
    async def test_orient_passes_correct_tools(self):
        """orient() configures agent with correct tools."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        ctx = OrientContext(
            spec_content="# Test Spec",
            claims_json="{}",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="Spec satisfied",
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            await orient(ctx)

            # Verify invoke was called with expected tools
            call_args = mock_agent.invoke.call_args
            tools = call_args.kwargs.get("tools")

            # Should include Read, Glob, Grep, Bash for code inspection and test running
            assert "Read" in tools
            assert "Glob" in tools
            assert "Grep" in tools
            assert "Bash" in tools

    @pytest.mark.asyncio
    async def test_orient_passes_output_schema(self):
        """orient() configures agent with OrientOutput schema."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        ctx = OrientContext(
            spec_content="# Test Spec",
            claims_json="{}",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            confidence=Confidence.LOW,
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            await orient(ctx)

            # Verify invoke was called with OrientOutput as schema
            call_args = mock_agent.invoke.call_args
            schema = call_args.kwargs.get("output_schema")
            assert schema == OrientOutput

    @pytest.mark.asyncio
    async def test_orient_builds_prompt_with_spec_and_claims(self):
        """orient() builds prompt containing spec content and claims."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        spec = "# My Spec\n## Criteria\n- [ ] Test passes"
        claims = '{"iteration_number": 5, "code_state": {"branch": "main"}}'

        ctx = OrientContext(
            spec_content=spec,
            claims_json=claims,
            root_work_item_id="ralph-abc",
            learnings="Use pytest for tests",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            await orient(ctx)

            # Verify prompt contains required sections
            call_args = mock_agent.invoke.call_args
            prompt = call_args.kwargs.get("prompt")

            assert "# My Spec" in prompt
            assert "iteration_number" in prompt
            assert "ralph-abc" in prompt
            assert "Use pytest for tests" in prompt

    @pytest.mark.asyncio
    async def test_orient_with_spec_satisfied(self):
        """orient() handles spec_satisfied=true case."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        ctx = OrientContext(
            spec_content="# Complete Spec",
            claims_json="{}",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            confidence=Confidence.HIGH,
            summary="All criteria verified",
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            result = await orient(ctx)

            assert result.spec_satisfied == SpecSatisfied.TRUE
            assert result.summary == "All criteria verified"

    @pytest.mark.asyncio
    async def test_orient_with_task_updates(self):
        """orient() returns task updates from agent."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        ctx = OrientContext(
            spec_content="# Spec",
            claims_json="{}",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.HIGH,
            task_updates=[
                TaskUpdate(
                    task_id="ralph-close1",
                    update_type=TaskUpdateType.CLOSE,
                    comment="Verified complete",
                ),
            ],
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            result = await orient(ctx)

            assert len(result.task_updates) == 1
            assert result.task_updates[0].task_id == "ralph-close1"

    @pytest.mark.asyncio
    async def test_orient_with_new_tasks(self):
        """orient() returns new tasks from agent."""
        from unittest.mock import AsyncMock, patch
        from soda.orient import orient, OrientContext

        ctx = OrientContext(
            spec_content="# Spec",
            claims_json="{}",
        )

        mock_result = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            confidence=Confidence.MEDIUM,
            new_tasks=[
                NewTask(
                    title="New gap task",
                    description="Address identified gap",
                    priority=1,
                ),
            ],
        )

        with patch("soda.orient.NarrowAgent") as MockAgent:
            mock_agent = MockAgent.return_value
            mock_agent.invoke = AsyncMock(return_value=mock_result)

            result = await orient(ctx)

            assert len(result.new_tasks) == 1
            assert result.new_tasks[0].title == "New gap task"


# =============================================================================
# ORIENT System Prompt Tests
# =============================================================================


class TestOrientSystemPrompt:
    """Tests for ORIENT_SYSTEM_PROMPT content requirements from spec."""

    def test_prompt_exists_and_is_string(self):
        """ORIENT_SYSTEM_PROMPT is defined and is a non-empty string."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert isinstance(ORIENT_SYSTEM_PROMPT, str)
        assert len(ORIENT_SYSTEM_PROMPT) > 0

    # --- Verify Claims Section ---

    def test_prompt_covers_verify_claims(self):
        """Prompt covers claim verification responsibility."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert "Verify Claims" in ORIENT_SYSTEM_PROMPT
        assert "codebase" in ORIENT_SYSTEM_PROMPT.lower()
        assert "arbiter of truth" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_verify_closed_tasks(self):
        """Prompt explains verifying closed tasks have actual code implementation."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN claims say a task is closed, THEN ORIENT verifies code actually implements it
        assert "closed" in ORIENT_SYSTEM_PROMPT.lower()
        assert "verify" in ORIENT_SYSTEM_PROMPT.lower()
        assert "implement" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_flag_discrepancy(self):
        """Prompt explains flagging discrepancy when code doesn't match closed task."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN task marked closed but code doesn't implement it, THEN flag discrepancy and reopen
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "discrepancy" in prompt_lower or "reopen" in prompt_lower

    def test_prompt_covers_verify_blocked_tasks(self):
        """Prompt explains verifying blocker still exists."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN claims say task blocked, THEN verify blocker still exists
        assert "blocked" in ORIENT_SYSTEM_PROMPT.lower()
        assert "blocker" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_unblock_tasks(self):
        """Prompt explains unblocking tasks when blocker resolved."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN blocker no longer exists, THEN task is unblocked
        assert "unblock" in ORIENT_SYSTEM_PROMPT.lower()
        assert "eligible" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_verify_learnings(self):
        """Prompt explains verifying learnings against reality."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN learnings conflict with observed reality, THEN flag for deprecation
        assert "learning" in ORIENT_SYSTEM_PROMPT.lower()
        assert "deprecat" in ORIENT_SYSTEM_PROMPT.lower()

    # --- Assess Spec Satisfaction Section ---

    def test_prompt_covers_spec_assessment(self):
        """Prompt covers spec satisfaction assessment."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert "Assess" in ORIENT_SYSTEM_PROMPT or "assess" in ORIENT_SYSTEM_PROMPT
        assert "Spec Satisfaction" in ORIENT_SYSTEM_PROMPT or "spec satisfaction" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_evaluate_each_criterion(self):
        """Prompt explains evaluating each criterion individually."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN assessing spec, THEN each acceptance criterion is evaluated individually
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "each" in prompt_lower and "criterion" in prompt_lower
        assert "individual" in prompt_lower

    def test_prompt_covers_spec_satisfied_values(self):
        """Prompt explains all three spec_satisfied values."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: spec_satisfied can be true, false, or unverifiable
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "spec_satisfied" in prompt_lower or "spec satisfied" in prompt_lower
        assert "true" in prompt_lower
        assert "false" in prompt_lower
        assert "unverifiable" in prompt_lower

    def test_prompt_covers_run_tests(self):
        """Prompt mentions running tests as verification method."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN assessing criteria, THEN tests are run as one verification method
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "run" in prompt_lower and "test" in prompt_lower
        assert "pytest" in prompt_lower or "test command" in prompt_lower

    def test_prompt_covers_read_code(self):
        """Prompt mentions reading code for implementation proof."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN assessing criteria, THEN code is read for implementation proof
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "read" in prompt_lower and "code" in prompt_lower

    def test_prompt_covers_tests_pass_but_implementation_missing(self):
        """Prompt explains tests passing but implementation missing = not satisfied."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN tests pass but implementation is missing, THEN criterion is not satisfied
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "test" in prompt_lower and "pass" in prompt_lower
        assert "implementation" in prompt_lower and "missing" in prompt_lower
        assert "not satisfied" in prompt_lower

    # --- Update Task Breakdown Section ---

    def test_prompt_covers_task_breakdown(self):
        """Prompt covers task breakdown updates."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert "Task Breakdown" in ORIENT_SYSTEM_PROMPT or "task breakdown" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_close_verified_tasks(self):
        """Prompt explains closing verified-complete tasks with comment."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN task verified complete, THEN closed in Trace with verification comment
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "close" in prompt_lower and "verified" in prompt_lower
        assert "comment" in prompt_lower

    def test_prompt_covers_create_gap_tasks(self):
        """Prompt explains creating tasks for identified gaps."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN gap identified, THEN new task created in Trace
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "gap" in prompt_lower
        assert "create" in prompt_lower and "task" in prompt_lower

    def test_prompt_covers_subtasks(self):
        """Prompt explains creating subtasks under parent."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN subtasks are needed, THEN they are created under parent task
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "subtask" in prompt_lower
        assert "parent" in prompt_lower

    # --- Plan Iteration Section ---

    def test_prompt_covers_plan_iteration(self):
        """Prompt covers iteration planning."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert "Plan Iteration" in ORIENT_SYSTEM_PROMPT or "iteration plan" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_priority_selection(self):
        """Prompt explains selecting tasks by priority P0 > P1 > P2."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN planning iteration, THEN tasks selected based on priority (P0 > P1 > P2)
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "priority" in prompt_lower
        assert "p0" in prompt_lower and "p1" in prompt_lower and "p2" in prompt_lower

    def test_prompt_covers_exclude_blocked(self):
        """Prompt explains excluding blocked tasks from plan."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN planning iteration, THEN blocked tasks are excluded
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "exclude" in prompt_lower and "blocked" in prompt_lower

    def test_prompt_covers_iteration_intent(self):
        """Prompt explains defining iteration intent."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN planning iteration, THEN iteration intent is defined
        assert "intent" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_approach(self):
        """Prompt explains outlining approach for iteration."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN planning iteration, THEN approach is outlined
        assert "approach" in ORIENT_SYSTEM_PROMPT.lower()

    # --- Pattern Recognition Section ---

    def test_prompt_covers_pattern_recognition(self):
        """Prompt covers pattern recognition."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        assert "Pattern Recognition" in ORIENT_SYSTEM_PROMPT or "pattern" in ORIENT_SYSTEM_PROMPT.lower()

    def test_prompt_covers_repeated_criterion_failure(self):
        """Prompt explains creating investigation task for repeated criterion failure."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN same criterion failed 2+ iterations, THEN investigation task created
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "investigation" in prompt_lower
        assert "2+" in prompt_lower or "2 iteration" in prompt_lower or "repeated" in prompt_lower

    def test_prompt_covers_repeated_test_failure(self):
        """Prompt explains creating investigation task for repeated test failure."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN same test failed 2+ iterations, THEN investigation task created
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "test" in prompt_lower and "fail" in prompt_lower
        assert "investigation" in prompt_lower

    def test_prompt_covers_loop_detection(self):
        """Prompt explains detecting potential loops."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: WHEN iteration history shows repeated intent with no progress, THEN flag potential loop
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "loop" in prompt_lower
        assert "repeated" in prompt_lower or "no progress" in prompt_lower

    # --- Output Structure Section ---

    def test_prompt_covers_output_structure(self):
        """Prompt explains the complete output structure."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: ORIENT output includes all required fields
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "spec_satisfied" in prompt_lower
        assert "actionable_work_exists" in prompt_lower
        assert "task_updates" in prompt_lower
        assert "new_tasks" in prompt_lower
        assert "gaps" in prompt_lower
        assert "iteration_plan" in prompt_lower
        assert "learnings" in prompt_lower

    def test_prompt_covers_confidence_levels(self):
        """Prompt explains confidence levels."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: Output includes confidence (high, medium, low)
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "confidence" in prompt_lower
        assert "high" in prompt_lower
        assert "medium" in prompt_lower
        assert "low" in prompt_lower

    # --- Tools Section ---

    def test_prompt_covers_available_tools(self):
        """Prompt lists available tools."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        # Spec: ORIENT agent has Read, Glob, Grep, Bash for tests, plus Trace update capability
        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "read" in prompt_lower
        assert "glob" in prompt_lower
        assert "grep" in prompt_lower
        assert "bash" in prompt_lower

    def test_prompt_covers_trace_commands(self):
        """Prompt includes trace commands."""
        from soda.orient import ORIENT_SYSTEM_PROMPT

        prompt_lower = ORIENT_SYSTEM_PROMPT.lower()
        assert "trc close" in prompt_lower
        assert "trc comment" in prompt_lower
        assert "trc create" in prompt_lower
