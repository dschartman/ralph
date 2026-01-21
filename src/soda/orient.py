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


# =============================================================================
# Enums
# =============================================================================


class SpecSatisfied(str, Enum):
    """Possible values for spec_satisfied in ORIENT output.

    TRUE: All acceptance criteria are satisfied
    FALSE: Some acceptance criteria are not satisfied
    UNVERIFIABLE: Cannot verify criteria (requires external resources)
    """

    TRUE = "true"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"


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
This is agent work—reasoning that cannot be done deterministically.

---

## 1. Verify Claims

Ground claims from SENSE against codebase reality. The codebase cannot lie—it is
the arbiter of truth. Trace and other systems can claim things that aren't true.

### Verify Closed Tasks
WHEN claims say a task is closed:
- Read the code to verify it actually implements the task's requirements
- If implementation is present and correct → task is verified closed
- If code doesn't implement it → FLAG DISCREPANCY and reopen the task
  - Add comment explaining what's missing
  - Create TaskUpdate with update_type="update" to reopen

### Verify Blocked Tasks
WHEN claims say a task is blocked:
- Verify the blocker condition still exists
- Check if the blocking resource/dependency is now available
- If blocker resolved → UNBLOCK the task (it becomes eligible for this iteration)
  - Create TaskUpdate with update_type="unblock"
- If blocker still exists → keep task blocked

### Verify Learnings
WHEN learnings are provided:
- Check if they match observed reality
- Example: learning says "tests are in tests/" but tests/ doesn't exist
- If learning conflicts with reality → FLAG FOR DEPRECATION
  - Add to learnings output with action="deprecate" and reason

---

## 2. Assess Spec Satisfaction

Evaluate EACH acceptance criterion in the spec INDIVIDUALLY. Do not skip criteria.

### For Each Criterion:
1. Extract the criterion text (look for [ ] and [x] checkboxes in spec)
2. Determine what evidence would prove satisfaction
3. Gather evidence:
   - Run relevant tests (use Bash: `uv run pytest ...` or appropriate test command)
   - Read implementation code (use Read, Glob, Grep)
   - Check for expected behavior
4. Make a judgment: satisfied | not_satisfied | unverifiable

### Verification Standards
- **Tests as evidence**: Tests passing is ONE verification method, not the only one
- **Code verification**: Read the code to verify implementation exists
- **CRITICAL**: Tests pass BUT implementation missing = NOT SATISFIED
  - Mock tests that fake success don't prove anything
  - Stub implementations that always return true don't satisfy criteria
- **External resources**: If verification requires external APIs, credentials,
  or systems you can't access → criterion is UNVERIFIABLE

### Determining spec_satisfied
- **spec_satisfied="true"**: ALL acceptance criteria are verified satisfied
- **spec_satisfied="false"**: At least one criterion is NOT satisfied
- **spec_satisfied="unverifiable"**: Cannot determine (all remaining criteria
  require external resources to verify)

---

## 3. Update Task Breakdown

Maintain accurate task state in Trace based on your verification results.

### Close Verified Tasks
WHEN a task is verified complete:
- Use `trc close <task_id>` via Bash
- Add verification comment: `trc comment <task_id> "message" --source orient`
- Include in task_updates output with update_type="close"

### Create Gap Tasks
WHEN you identify a gap (something missing or incomplete):
- Create a new task: `trc create "title" --description "details"`
- For subtasks: `trc create "title" --description "details" --parent <parent_id>`
- Include in new_tasks output with appropriate priority
- Add to gaps output with severity (critical, major, minor)

### Unblock Tasks
WHEN a task's blocker is resolved:
- Use TaskUpdate with update_type="unblock"
- The task becomes immediately eligible for the iteration plan
- Add comment explaining what changed

### Adjust Priorities
WHEN task priority needs adjustment:
- Use TaskUpdate with update_type="update" and new priority value
- Priority scale: 0=P0 (highest/critical), 1=P1 (high), 2=P2 (medium)

### Create Subtasks
WHEN a task needs to be broken down:
- Create subtasks under the parent task
- Use `--parent <parent_id>` when creating

---

## 4. Plan Iteration

WHEN spec is NOT satisfied, create a plan for what to work on.

### Task Selection
1. Gather all unblocked tasks (including newly unblocked ones from step 1)
2. Sort by priority: P0 > P1 > P2
3. Select tasks for this iteration based on priority
4. EXCLUDE blocked tasks from the plan

### Define Iteration Plan
Your iteration_plan must include:
- **intent**: Summary of what this iteration will accomplish (1-2 sentences)
- **tasks**: List of PlannedTask with task_id, title, and rationale
- **approach**: How the tasks will be tackled (strategy/approach description)
- **estimated_scope**: Optional, e.g., "small", "medium", "large"

### No Plan Needed
WHEN spec_satisfied="true":
- Set iteration_plan=None
- Set actionable_work_exists=False
- Provide summary of completion

---

## 5. Pattern Recognition

Detect repeated failures and loops to avoid wasting iterations.

### Repeated Criterion Failure
WHEN the same acceptance criterion has failed 2+ iterations:
- Do NOT retry the same fix approach
- Create an INVESTIGATION task instead:
  - Title: "Investigate: why does <criterion> keep failing?"
  - Description: Include previous attempts and their outcomes
  - Priority: P0 or P1
- Include in new_tasks output

### Repeated Test Failure
WHEN the same test has failed 2+ iterations:
- Create investigation task: "Investigate: <test_name> repeated failures"
- Include previous error messages if available

### Loop Detection
WHEN iteration history shows repeated intent with no progress:
- Flag the potential loop in gaps output with severity="critical"
- Set actionable_work_exists based on whether investigation is actionable
- Investigation IS actionable work—it counts as progress

---

## Tools Available

You have read-only codebase access plus Trace update capability:

- **Read**: Read files to verify implementation
- **Glob**: Find files by pattern (e.g., "**/*.py", "src/**/*.ts")
- **Grep**: Search code for patterns (class names, function names, imports)
- **Bash**: Run commands:
  - Run tests: `uv run pytest tests/ -v` (or project-specific command)
  - Trace operations: `trc close`, `trc comment`, `trc create`

### Trace Commands (via Bash)
```bash
# Close a task
trc close <task_id>

# Add comment
trc comment <task_id> "message" --source orient

# Create new task (--description is required)
trc create "title" --description "detailed description"

# Create subtask
trc create "subtask title" --description "details" --parent <parent_id>

# View task details
trc show <task_id>

# List tasks
trc list
trc ready  # show unblocked tasks
```

---

## Output Requirements

Your output must be valid OrientOutput JSON matching this schema:

```json
{
  "spec_satisfied": "true" | "false" | "unverifiable",
  "actionable_work_exists": boolean,
  "confidence": "high" | "medium" | "low",
  "task_updates": [
    {
      "task_id": "ralph-xxx",
      "update_type": "close" | "update" | "block" | "unblock",
      "comment": "optional verification comment",
      "priority": null | 0 | 1 | 2,
      "blocker_reason": "optional reason for blocking"
    }
  ],
  "new_tasks": [
    {
      "title": "Task title",
      "description": "What needs to be done",
      "priority": 0 | 1 | 2,
      "parent_id": null | "ralph-xxx",
      "blocked_by": null | "ralph-xxx"
    }
  ],
  "gaps": [
    {
      "description": "What's missing or incomplete",
      "severity": "critical" | "major" | "minor",
      "criterion_ref": "optional: which acceptance criterion",
      "related_task_id": null | "ralph-xxx",
      "suggested_action": "optional: how to fix"
    }
  ],
  "iteration_plan": {
    "intent": "What this iteration will accomplish",
    "tasks": [
      {
        "task_id": "ralph-xxx",
        "title": "Task title",
        "rationale": "Why this task was selected"
      }
    ],
    "approach": "How tasks will be tackled",
    "estimated_scope": "small" | "medium" | "large"
  },
  "learnings": [
    {
      "content": "The learning or efficiency note",
      "action": "preserve" | "deprecate",
      "reason": "optional: why deprecating"
    }
  ],
  "summary": "Final assessment summary (required when spec_satisfied='true')"
}
```

---

## Confidence Levels

Set confidence based on your verification certainty:

- **high**: Strong evidence supports assessment. Tests ran successfully, code
  was read and understood, clear conclusions drawn.
- **medium**: Moderate evidence, some uncertainty. Most verification succeeded
  but some areas less clear.
- **low**: Limited evidence, high uncertainty. Couldn't verify some aspects,
  making inferences.

---

## Key Principles

1. **The codebase cannot lie** — It's the arbiter of truth. Trace can claim
   things that aren't true; the code proves what's real.

2. **Tests passing ≠ implementation correct** — Always verify both. A mock
   test that passes proves nothing about actual behavior.

3. **Each criterion evaluated individually** — Don't batch assessments. Go
   through each acceptance criterion one by one.

4. **Blocked tasks excluded from planning** — Only unblocked tasks go in
   the iteration plan.

5. **Investigation over retry** — When something fails repeatedly (2+
   iterations), investigate rather than trying the same thing again.

6. **Hold the line on quality** — Your job is to be objective and stubborn.
   "Good enough" is not "satisfied." Only evidence-based satisfaction counts.

7. **Complete within token budget** — Be efficient. Don't exhaustively read
   every file. Use Glob/Grep to find relevant code, then Read targeted files.

---

## CRITICAL: Output Format

Your FINAL response must be ONLY the OrientOutput JSON object. Do not include:
- Explanatory text before or after the JSON
- Markdown code fences (no ```json)
- Commentary about what you're doing

After using tools to verify claims and assess the spec, output ONLY the raw JSON object.
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
