"""ACT phase data structures and act() function.

The ACT phase executes the iteration plan from ORIENT, implementing tasks
through a TDD cycle. The orchestrator handles git operations (branch, commit,
merge); agents handle implementation work.

This module contains the Pydantic models for ACT input/output and will
eventually contain the act() async function that drives the phase.

ACT outputs:
- tasks_completed: list of task IDs that were completed
- tasks_blocked: list of blocked tasks with reasons
- task_comments: comments posted to tasks during work
- new_subtasks: subtasks discovered and created during work
- learnings: efficiency knowledge discovered
- commits: git commit hashes created
"""

from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Reuse NewTask from orient.py to avoid duplication
# =============================================================================

# Import NewTask from orient.py - same structure needed for subtasks
from soda.orient import NewTask


# =============================================================================
# BlockedTask Structure
# =============================================================================


class BlockedTask(BaseModel):
    """A task that was blocked during ACT execution.

    When an agent cannot complete a task (missing dependencies,
    external resources unavailable, etc.), it creates a BlockedTask
    with the reason for blocking.
    """

    task_id: str = Field(description="ID of the blocked task (e.g., 'ralph-abc123')")
    reason: str = Field(description="Reason why the task is blocked")


# =============================================================================
# TaskComment Structure (ACT-specific)
# =============================================================================


class TaskComment(BaseModel):
    """A comment posted to a task during ACT execution.

    Note: This is simpler than sense.TaskComment - ACT's TaskComment
    just captures what was posted, not the full metadata like timestamp
    and source (which are set by Trace when posting).
    """

    task_id: str = Field(description="ID of the task this comment was posted to")
    comment: str = Field(description="The comment text that was posted")


# =============================================================================
# Main ACT Output Structure
# =============================================================================


class ActOutput(BaseModel):
    """Complete output from the ACT phase.

    ACT executes the iteration plan, producing:
    - Completed tasks (by ID)
    - Blocked tasks (with reasons)
    - Comments posted to tasks
    - Subtasks discovered during work
    - Learnings for efficiency
    - Git commits created
    """

    tasks_completed: list[str] = Field(
        default_factory=list,
        description="Task IDs that were completed",
    )
    tasks_blocked: list[BlockedTask] = Field(
        default_factory=list,
        description="Tasks that were blocked with reasons",
    )
    task_comments: list[TaskComment] = Field(
        default_factory=list,
        description="Comments posted to tasks during work",
    )
    new_subtasks: list[NewTask] = Field(
        default_factory=list,
        description="Subtasks discovered and created during work",
    )
    learnings: list[str] = Field(
        default_factory=list,
        description="Efficiency knowledge discovered (actionable, project-specific)",
    )
    commits: list[str] = Field(
        default_factory=list,
        description="Git commit hashes created during ACT",
    )
