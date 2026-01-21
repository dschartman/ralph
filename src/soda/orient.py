"""ORIENT phase data structures and agent function.

The ORIENT phase is where all judgment lives. It verifies claims against the
codebase, assesses spec satisfaction, updates the task breakdown, and plans
the iteration. This module contains the Pydantic models for ORIENT output
and the orient() async function that drives the phase.

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
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from soda.agents.narrow import NarrowAgent

# Import SpecSatisfied from decide.py to avoid duplication
from soda.decide import SpecSatisfied


# =============================================================================
# ORIENT System Prompt
# =============================================================================

ORIENT_SYSTEM_PROMPT = """You are the ORIENT agent in the SODA loop. Your job is to verify claims, assess spec satisfaction, update the task breakdown, and plan the iteration.

## Your Responsibilities

You receive claims from the SENSE phase and must:
1. **Verify Claims**: Check if what systems claim matches reality in the codebase
2. **Assess Spec Satisfaction**: Evaluate each acceptance criterion against the code
3. **Update Task Breakdown**: Close verified tasks, create tasks for gaps, unblock resolved tasks
4. **Plan Iteration**: Select and order tasks for the current iteration

## Verification Process

SENSE reports claims from systems (git, Trace, DB). Your job is to verify these claims against the codebase—the one source that cannot lie.

**Claim verification rules:**
- If Trace says a task is closed, verify the code actually implements it
- If a task is marked closed but code doesn't implement it, flag the discrepancy and reopen
- If Trace says a task is blocked, verify the blocker still exists
- If the blocker no longer exists, unblock the task (it becomes eligible for this iteration)
- If learnings conflict with observed reality, flag them for deprecation

## Spec Assessment

For each acceptance criterion in the spec:
1. Run tests if available (use Bash tool)
2. Read code for implementation proof (use Read, Grep, Glob tools)
3. Determine status: satisfied | not_satisfied | unverifiable

**Assessment rules:**
- Tests pass AND implementation exists → satisfied
- Tests fail OR implementation missing → not_satisfied
- Cannot verify (requires external resources) → unverifiable
- Tests pass but implementation is missing → NOT satisfied (tests may be mocked)

**Final assessment:**
- All criteria satisfied → spec_satisfied = true
- Any criterion not satisfied → spec_satisfied = false
- All criteria require external resources → spec_satisfied = unverifiable

## Task Management

Based on your verification and assessment:
- **Close tasks**: When code verifies task is complete, close with verification comment
- **Create tasks**: When gaps are identified, create new tasks in Trace
- **Unblock tasks**: When blockers are resolved, update task to unblocked
- **Update priority**: When task priority needs adjustment, update accordingly

## Iteration Planning

When spec is not satisfied:
1. Select tasks to work on based on priority (P0 > P1 > P2)
2. Exclude blocked tasks
3. Define iteration intent (what this iteration will accomplish)
4. Outline approach (how tasks will be tackled)

## Pattern Recognition

Watch for patterns that indicate problems:
- Same criterion failed 2+ iterations → create investigation task instead of retry
- Same test failed 2+ iterations → create investigation task
- Repeated intent with no progress → flag potential loop
- When loop detected, investigation becomes the actionable work

## Available Tools

You have access to:
- **Read**: Read files from the codebase
- **Glob**: Find files by pattern
- **Grep**: Search for content in files
- **Bash**: Run tests, type checkers, and other verification commands

## Output Format

Your output must be a valid OrientOutput with:
- spec_satisfied: "true" | "false" | "unverifiable"
- actionable_work_exists: boolean (is there work that can be done?)
- confidence: "high" | "medium" | "low" (confidence in assessment)
- task_updates: list of task update operations
- new_tasks: list of new tasks to create
- gaps: list of identified gaps with severity
- iteration_plan: intent, tasks, and approach (if spec not satisfied)
- learnings: efficiency knowledge to preserve or deprecate
- summary: final assessment summary (if spec satisfied)

## Guidelines

1. Be thorough but efficient—don't read every file, focus on relevant ones
2. Trust tests that actually test the spec; be skeptical of mocked tests
3. When in doubt about verification, mark as unverifiable (don't guess)
4. Create specific, actionable tasks for gaps
5. Keep learnings practical and project-specific
"""


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
# OrientContext (Input Structure)
# =============================================================================


class OrientContext(BaseModel):
    """Context required for the ORIENT phase.

    Contains all the information needed to perform verification and assessment:
    - Claims from SENSE phase
    - The spec being worked on
    - Iteration history for pattern recognition
    """

    claims: Any = Field(
        description="Claims output from SENSE phase (Claims object)"
    )
    spec: str = Field(
        description="The spec content being worked on"
    )
    iteration_history: list[dict] = Field(
        default_factory=list,
        description="History of previous iterations for pattern recognition"
    )
    root_work_item_id: Optional[str] = Field(
        default=None,
        description="Root work item ID in Trace (for task operations)"
    )


# =============================================================================
# ORIENT Function
# =============================================================================

# Tools available to the ORIENT agent
ORIENT_TOOLS = ["Read", "Glob", "Grep", "Bash"]


def _build_orient_prompt(ctx: OrientContext) -> str:
    """Build the prompt for the ORIENT agent.

    Args:
        ctx: OrientContext with claims, spec, and iteration history

    Returns:
        Formatted prompt string for the ORIENT agent
    """
    prompt_parts = []

    # Add spec section
    prompt_parts.append("# Spec")
    prompt_parts.append("")
    prompt_parts.append(ctx.spec)
    prompt_parts.append("")
    prompt_parts.append("---")
    prompt_parts.append("")

    # Add claims section
    prompt_parts.append("# Claims from SENSE")
    prompt_parts.append("")
    # Serialize claims to readable format
    if hasattr(ctx.claims, "model_dump"):
        claims_data = ctx.claims.model_dump(mode="json")
        # Format key claims sections
        prompt_parts.append("## Code State")
        code_state = claims_data.get("code_state", {})
        prompt_parts.append(f"- Branch: {code_state.get('branch', 'unknown')}")
        prompt_parts.append(f"- Staged changes: {code_state.get('staged_count', 0)}")
        prompt_parts.append(f"- Unstaged changes: {code_state.get('unstaged_count', 0)}")
        if code_state.get("commits"):
            prompt_parts.append(f"- Commits since base: {len(code_state['commits'])}")
        if code_state.get("files_changed"):
            prompt_parts.append(f"- Files changed: {len(code_state['files_changed'])}")
        prompt_parts.append("")

        prompt_parts.append("## Work State")
        work_state = claims_data.get("work_state", {})
        open_tasks = work_state.get("open_tasks", [])
        blocked_tasks = work_state.get("blocked_tasks", [])
        closed_tasks = work_state.get("closed_tasks", [])
        prompt_parts.append(f"- Open tasks: {len(open_tasks)}")
        prompt_parts.append(f"- Blocked tasks: {len(blocked_tasks)}")
        prompt_parts.append(f"- Closed tasks: {len(closed_tasks)}")
        if open_tasks:
            prompt_parts.append("- Open task list:")
            for task in open_tasks:
                prompt_parts.append(f"  - [{task.get('id', 'unknown')}] {task.get('title', 'untitled')}")
        if blocked_tasks:
            prompt_parts.append("- Blocked task list:")
            for task in blocked_tasks:
                reason = task.get("blocker_reason", "unknown reason")
                prompt_parts.append(f"  - [{task.get('id', 'unknown')}] {task.get('title', 'untitled')} (blocked: {reason})")
        prompt_parts.append("")

        prompt_parts.append("## Project State")
        project_state = claims_data.get("project_state", {})
        prompt_parts.append(f"- Current iteration: {project_state.get('iteration_number', 1)}")
        prompt_parts.append(f"- First iteration: {project_state.get('first_iteration', True)}")
        if project_state.get("agent_summaries"):
            prompt_parts.append("- Recent agent summaries:")
            for summary in project_state["agent_summaries"]:
                prompt_parts.append(f"  - {summary.get('agent_type', 'unknown')}: {summary.get('summary', '')[:100]}...")
        prompt_parts.append("")

        # Add learnings if present
        learnings = claims_data.get("learnings", "")
        if learnings:
            prompt_parts.append("## Learnings (from memory)")
            prompt_parts.append(learnings)
            prompt_parts.append("")
    else:
        prompt_parts.append(str(ctx.claims))
        prompt_parts.append("")

    prompt_parts.append("---")
    prompt_parts.append("")

    # Add iteration history if present
    if ctx.iteration_history:
        prompt_parts.append("# Iteration History")
        prompt_parts.append("")
        prompt_parts.append("Review this history for patterns (repeated failures, stuck criteria):")
        prompt_parts.append("")
        for h in ctx.iteration_history:
            prompt_parts.append(f"## Iteration {h.get('number', '?')}")
            prompt_parts.append(f"- Intent: {h.get('intent', 'N/A')}")
            prompt_parts.append(f"- Outcome: {h.get('outcome', 'N/A')}")
            if h.get("executor_summary"):
                prompt_parts.append(f"- Summary: {h['executor_summary']}")
            prompt_parts.append("")
        prompt_parts.append("---")
        prompt_parts.append("")

    # Add root work item if present
    if ctx.root_work_item_id:
        prompt_parts.append(f"# Root Work Item: `{ctx.root_work_item_id}`")
        prompt_parts.append("")
        prompt_parts.append("---")
        prompt_parts.append("")

    # Add instructions
    prompt_parts.append("# Your Task")
    prompt_parts.append("")
    prompt_parts.append("1. Verify claims from SENSE against the codebase")
    prompt_parts.append("2. Assess spec satisfaction for each acceptance criterion")
    prompt_parts.append("3. Identify gaps between current state and spec satisfaction")
    prompt_parts.append("4. Determine task updates (close, unblock, create)")
    prompt_parts.append("5. Plan the iteration if spec is not satisfied")
    prompt_parts.append("6. Note any learnings to preserve or deprecate")
    prompt_parts.append("")
    prompt_parts.append("Produce a complete OrientOutput with your findings.")

    return "\n".join(prompt_parts)


async def orient(ctx: OrientContext) -> OrientOutput:
    """Execute the ORIENT phase: verify claims and assess spec satisfaction.

    The ORIENT phase verifies claims from SENSE against the codebase,
    assesses spec satisfaction, updates the task breakdown, and plans
    the iteration.

    Args:
        ctx: OrientContext with claims, spec, and iteration history

    Returns:
        OrientOutput with verification results, assessment, and iteration plan
    """
    # Build the prompt
    prompt = _build_orient_prompt(ctx)

    # Create and invoke the agent
    agent = NarrowAgent()
    result = await agent.invoke(
        prompt=prompt,
        output_schema=OrientOutput,
        tools=ORIENT_TOOLS,
        system_prompt=ORIENT_SYSTEM_PROMPT,
    )

    return result
