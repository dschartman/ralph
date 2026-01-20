"""ORIENT phase data structures.

The ORIENT phase is where all judgment lives. It verifies claims against the
codebase, assesses spec satisfaction, updates the task breakdown, and plans
the iteration. This module contains the Pydantic models for ORIENT output.

ORIENT outputs:
- spec_satisfied: true | false | "unverifiable"
- actionable_work_exists: boolean
- task_updates: close/update/block operations
- new_tasks: gaps to create
- gaps: identified gaps with severity
- iteration_plan: intent, tasks, approach
- learnings: efficiency knowledge to preserve or deprecate
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Import SpecSatisfied from decide.py to avoid duplication
from soda.decide import SpecSatisfied
from soda.agents.narrow import NarrowAgent


# =============================================================================
# Enums
# =============================================================================


class Confidence(str, Enum):
    """Confidence level in the ORIENT assessment.

    HIGH: Strong evidence supports the assessment
    MEDIUM: Moderate evidence, some uncertainty
    LOW: Limited evidence, high uncertainty
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskUpdateType(str, Enum):
    """Types of task updates that ORIENT can perform.

    CLOSE: Close a task (verified complete)
    UPDATE: Update task metadata (priority, description, etc.)
    BLOCK: Mark a task as blocked
    UNBLOCK: Remove blocker from a task
    """

    CLOSE = "close"
    UPDATE = "update"
    BLOCK = "block"
    UNBLOCK = "unblock"


class GapSeverity(str, Enum):
    """Severity levels for identified gaps.

    CRITICAL: Must be addressed before spec can be satisfied
    MAJOR: Significant gap that affects spec satisfaction
    MINOR: Small gap that should be addressed but not blocking
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


# =============================================================================
# Task Update Structures
# =============================================================================


class TaskUpdate(BaseModel):
    """A task update operation for Trace.

    Represents an operation to perform on an existing task:
    - close: Mark task as complete (with verification comment)
    - update: Update task metadata (priority, title, description)
    - block: Mark task as blocked (with blocker reason)
    - unblock: Remove blocker from task
    """

    task_id: str = Field(description="ID of the task to update (e.g., 'ralph-abc123')")
    update_type: TaskUpdateType = Field(description="Type of update operation")
    comment: Optional[str] = Field(
        default=None,
        description="Comment to add (e.g., verification note for close)",
    )
    priority: Optional[int] = Field(
        default=None,
        description="New priority (for UPDATE operations, 0-2)",
    )
    blocker_reason: Optional[str] = Field(
        default=None,
        description="Reason for blocking (for BLOCK operations)",
    )


# =============================================================================
# New Task Structure
# =============================================================================


class NewTask(BaseModel):
    """A new task to create in Trace.

    Used when ORIENT identifies a gap that requires new work.
    """

    title: str = Field(description="Task title (concise description of work)")
    description: str = Field(
        description="Detailed description of what needs to be done"
    )
    priority: int = Field(
        default=1,
        ge=0,
        le=2,
        description="Priority: 0=P0 (highest), 1=P1, 2=P2 (lowest)",
    )
    parent_id: Optional[str] = Field(
        default=None,
        description="Parent task ID if this is a subtask",
    )
    blocked_by: Optional[str] = Field(
        default=None,
        description="Task ID that blocks this task",
    )


# =============================================================================
# Gap Structure
# =============================================================================


class Gap(BaseModel):
    """An identified gap between current state and spec satisfaction.

    Gaps represent things that are missing, broken, or incomplete.
    They may or may not have corresponding tasks yet.
    """

    description: str = Field(description="Description of the gap")
    severity: GapSeverity = Field(description="Severity: critical, major, or minor")
    criterion_ref: Optional[str] = Field(
        default=None,
        description="Reference to acceptance criterion (if applicable)",
    )
    related_task_id: Optional[str] = Field(
        default=None,
        description="ID of related task (if one exists)",
    )
    suggested_action: Optional[str] = Field(
        default=None,
        description="Suggested action to address the gap",
    )


# =============================================================================
# Iteration Plan Structure
# =============================================================================


class PlannedTask(BaseModel):
    """A task selected for the iteration plan.

    Includes the task ID plus reasoning for selection.
    """

    task_id: str = Field(description="ID of the task to work on")
    title: str = Field(description="Task title (for reference)")
    rationale: str = Field(description="Why this task was selected for this iteration")


class IterationPlan(BaseModel):
    """Plan for the current iteration.

    Defines what the iteration will accomplish and how.
    """

    intent: str = Field(
        description="Summary of what this iteration will accomplish"
    )
    tasks: list[PlannedTask] = Field(
        default_factory=list,
        description="Tasks to work on in this iteration (ordered by priority)",
    )
    approach: str = Field(
        description="How the tasks will be tackled (strategy/approach)"
    )
    estimated_scope: Optional[str] = Field(
        default=None,
        description="Estimated scope/complexity of iteration (e.g., 'small', 'medium', 'large')",
    )


# =============================================================================
# Learning Structure
# =============================================================================


class Learning(BaseModel):
    """A learning or efficiency note from ORIENT.

    Learnings are efficiency knowledge to preserve in memory
    or deprecate if they conflict with observed reality.
    """

    content: str = Field(description="The learning or efficiency note")
    action: Literal["preserve", "deprecate"] = Field(
        description="Whether to preserve or deprecate this learning"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for preserving/deprecating (if deprecating)",
    )


# =============================================================================
# Main ORIENT Output Structure
# =============================================================================


class OrientOutput(BaseModel):
    """Complete output from the ORIENT phase.

    ORIENT verifies claims, assesses spec satisfaction, updates task breakdown,
    and plans the iteration. This output drives the DECIDE phase routing.
    """

    # Core routing fields (used by DECIDE)
    spec_satisfied: SpecSatisfied = Field(
        description="Whether spec is satisfied: true, false, or unverifiable"
    )
    actionable_work_exists: bool = Field(
        description="Whether there is actionable work to do"
    )
    confidence: Confidence = Field(
        description="Confidence level in this assessment: high, medium, or low"
    )

    # Task management
    task_updates: list[TaskUpdate] = Field(
        default_factory=list,
        description="Operations to perform on existing tasks",
    )
    new_tasks: list[NewTask] = Field(
        default_factory=list,
        description="New tasks to create (from identified gaps)",
    )

    # Gap analysis
    gaps: list[Gap] = Field(
        default_factory=list,
        description="Identified gaps between current state and spec",
    )

    # Iteration planning
    iteration_plan: Optional[IterationPlan] = Field(
        default=None,
        description="Plan for the current iteration (None if spec satisfied)",
    )

    # Learnings
    learnings: list[Learning] = Field(
        default_factory=list,
        description="Efficiency knowledge to preserve or deprecate",
    )

    # Summary for DECIDE (DONE case)
    summary: Optional[str] = Field(
        default=None,
        description="Final assessment summary (used when spec is satisfied)",
    )


# =============================================================================
# ORIENT Context Structure
# =============================================================================


class OrientContext(BaseModel):
    """Context required for the ORIENT phase.

    Contains all the information needed to perform claim verification,
    spec assessment, task breakdown updates, and iteration planning.
    """

    spec_content: str = Field(description="The specification content")
    claims_json: str = Field(description="JSON-serialized Claims from SENSE phase")
    root_work_item_id: Optional[str] = Field(
        default=None,
        description="Root work item ID in trace (None if not set)",
    )
    learnings: str = Field(
        default="",
        description="Accumulated learnings/efficiency knowledge",
    )


# =============================================================================
# ORIENT System Prompt
# =============================================================================


ORIENT_SYSTEM_PROMPT = """You are the ORIENT agent in the SODA loop.

## Your Role

ORIENT is where all judgment lives. You verify claims against the codebase,
assess spec satisfaction, update the task breakdown, and plan the iteration.

## Your Responsibilities

1. **Verify Claims** - Ground claims from SENSE against codebase reality
   - If a task is marked closed, verify the code actually implements it
   - If a task is blocked, verify the blocker still exists
   - If learnings conflict with observed reality, flag for deprecation

2. **Assess Spec Satisfaction** - Evaluate each acceptance criterion
   - Run tests as one verification method
   - Read code for implementation proof
   - Tests passing but implementation missing = NOT satisfied
   - Criteria requiring external resources = unverifiable

3. **Update Task Breakdown** - Maintain accurate task state
   - Close verified-complete tasks (with verification comment)
   - Create tasks for identified gaps
   - Unblock tasks where blocker resolved
   - Adjust priorities as needed

4. **Plan Iteration** - If spec not satisfied, plan what to work on
   - Select tasks based on priority (P0 > P1 > P2)
   - Exclude blocked tasks
   - Define iteration intent and approach

5. **Pattern Recognition** - Detect repeated failures
   - Same criterion failed 2+ iterations → create investigation task
   - Same test failed 2+ iterations → create investigation task
   - Repeated intent with no progress → flag potential loop

## Verification Standards

- **spec_satisfied=true**: ALL acceptance criteria are verified satisfied
- **spec_satisfied=false**: At least one criterion is not satisfied
- **spec_satisfied=unverifiable**: Cannot verify (requires external resources)

## Tools Available

You have access to:
- **Read**: Read files to verify implementation
- **Glob**: Find files by pattern
- **Grep**: Search code for patterns
- **Bash**: Run commands (tests, trc commands for Trace)

## Trace Commands (via Bash)

To update tasks:
- `trc close <id>` - Mark task complete
- `trc comment <id> "message" --source orient` - Add verification comment
- `trc create "title" --description "details"` - Create new task
- `trc create "subtask" --description "details" --parent <id>` - Create subtask

## Output Requirements

Your output must be valid OrientOutput JSON with:
- spec_satisfied: "true", "false", or "unverifiable"
- actionable_work_exists: boolean
- confidence: "high", "medium", or "low"
- task_updates: list of operations performed
- new_tasks: list of tasks created for gaps
- gaps: list of identified gaps with severity
- iteration_plan: plan for this iteration (if spec not satisfied)
- learnings: efficiency knowledge to preserve or deprecate
- summary: final assessment summary (if spec satisfied)

## Key Principles

- The codebase cannot lie - it's the arbiter of truth
- Trace claims must be verified against actual code
- Tests passing ≠ implementation correct (verify both)
- Be objective and specific in your assessment
- Hold the line on quality - that's your job
"""


# =============================================================================
# ORIENT Function
# =============================================================================


async def orient(ctx: OrientContext) -> OrientOutput:
    """Execute the ORIENT phase: verify claims and assess spec satisfaction.

    This function invokes an LLM agent to perform:
    - Claim verification (ground claims against codebase)
    - Spec satisfaction assessment (evaluate each criterion)
    - Task breakdown updates (close, create, unblock tasks)
    - Iteration planning (select tasks, define intent)
    - Pattern recognition (detect repeated failures)

    Args:
        ctx: OrientContext with spec, claims, and learnings

    Returns:
        OrientOutput with assessment, task updates, and iteration plan
    """

    # Build the prompt
    prompt_parts = [
        "# Spec",
        "",
        ctx.spec_content,
        "",
        "---",
        "",
        "# Claims from SENSE",
        "",
        "These are claims from systems (git, Trace, database). Verify them against the codebase.",
        "",
        ctx.claims_json,
        "",
        "---",
        "",
    ]

    # Add root work item if available
    if ctx.root_work_item_id:
        prompt_parts.extend([
            "# Root Work Item",
            "",
            f"Root work item ID: `{ctx.root_work_item_id}`",
            "",
            "Use this as reference for task hierarchy.",
            "",
            "---",
            "",
        ])

    # Add learnings if available
    if ctx.learnings:
        prompt_parts.extend([
            "# Learnings",
            "",
            "Verify these against observed reality. Flag if they conflict.",
            "",
            ctx.learnings,
            "",
            "---",
            "",
        ])

    prompt_parts.extend([
        "# Your Task",
        "",
        "1. Verify claims against the codebase",
        "2. Assess spec satisfaction (check each acceptance criterion)",
        "3. Update task breakdown (close verified tasks, create gap tasks)",
        "4. Plan the iteration (if spec not satisfied)",
        "5. Identify learnings to preserve or deprecate",
        "",
        "Return a complete OrientOutput.",
    ])

    prompt = "\n".join(prompt_parts)

    # Create and invoke the agent
    agent = NarrowAgent()
    result = await agent.invoke(
        prompt=prompt,
        output_schema=OrientOutput,
        tools=["Read", "Glob", "Grep", "Bash"],
    )

    return result
