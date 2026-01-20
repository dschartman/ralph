"""Data structures for SENSE phase output.

The SENSE phase gathers claims from various sources (git, trace, database)
without judgment. These Pydantic models define the structured output that
gets passed to the ORIENT phase for analysis.

All structures must be JSON-serializable for passing to ORIENT.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Code State Claims
# =============================================================================


class CommitInfo(BaseModel):
    """Information about a single commit."""

    hash: str = Field(description="Git commit hash (short or full)")
    message: str = Field(description="Commit message")
    timestamp: datetime = Field(description="Commit timestamp")


class DiffSummary(BaseModel):
    """Summary of lines added/removed in a diff."""

    lines_added: int = Field(description="Number of lines added")
    lines_removed: int = Field(description="Number of lines removed")


class CodeStateClaims(BaseModel):
    """Claims about the current code state.

    Gathered from git: branch, uncommitted changes, commits since milestone base.
    """

    branch: Optional[str] = Field(
        default=None,
        description="Current branch name",
    )
    staged_count: int = Field(
        default=0,
        description="Number of staged changes",
    )
    unstaged_count: int = Field(
        default=0,
        description="Number of unstaged changes",
    )
    commits: list[CommitInfo] = Field(
        default_factory=list,
        description="Commits since milestone base (hash, message, timestamp)",
    )
    files_changed: list[str] = Field(
        default_factory=list,
        description="Files changed since milestone base",
    )
    diff_summary: Optional[DiffSummary] = Field(
        default=None,
        description="Summary of lines added/removed",
    )
    no_base_commit: bool = Field(
        default=False,
        description="True if milestone base is empty (new project)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading code state failed",
    )


# =============================================================================
# Work State Claims
# =============================================================================


class TaskInfo(BaseModel):
    """Information about a single task."""

    id: str = Field(description="Task ID (e.g., 'ralph-abc123')")
    title: str = Field(description="Task title")
    status: str = Field(description="Task status (open, blocked, closed, etc.)")
    blocker_reason: Optional[str] = Field(
        default=None,
        description="Reason for blocking (if status is blocked)",
    )


class TaskComment(BaseModel):
    """A comment on a task."""

    task_id: str = Field(description="ID of the task this comment belongs to")
    source: str = Field(description="Source of the comment (executor, planner, etc.)")
    text: str = Field(description="Comment text")
    timestamp: datetime = Field(description="When the comment was made")


class WorkStateClaims(BaseModel):
    """Claims about the current work state.

    Gathered from trace: open tasks, blocked tasks, closed tasks, comments.
    """

    open_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Open tasks under milestone root",
    )
    blocked_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Blocked tasks with blocker reasons",
    )
    closed_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Closed tasks",
    )
    recent_comments: list[TaskComment] = Field(
        default_factory=list,
        description="Recent comments (last 10) on milestone tasks",
    )
    no_root_work_item: bool = Field(
        default=False,
        description="True if no milestone root exists",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading work state failed",
    )


# =============================================================================
# Project State Claims
# =============================================================================


class IterationSummary(BaseModel):
    """Summary of a past iteration."""

    number: int = Field(description="Iteration number")
    intent: str = Field(description="Intent/goal of the iteration")
    outcome: str = Field(description="Outcome (continue, done, stuck)")


class AgentSummary(BaseModel):
    """Summary from an agent's output."""

    agent_type: str = Field(description="Type of agent (executor, verifier, etc.)")
    summary: str = Field(description="Agent's output summary")


class ProjectStateClaims(BaseModel):
    """Claims about the project state.

    Gathered from database: iteration history, agent summaries.
    """

    iteration_number: int = Field(
        description="Current iteration number",
    )
    iteration_history: list[IterationSummary] = Field(
        default_factory=list,
        description="Recent iteration history (last 5)",
    )
    agent_summaries: list[AgentSummary] = Field(
        default_factory=list,
        description="Last agent summaries (executor, verifier)",
    )
    first_iteration: bool = Field(
        default=False,
        description="True if this is the first iteration",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading project state failed",
    )


# =============================================================================
# Human Input Claims
# =============================================================================


class HumanInputClaims(BaseModel):
    """Claims about pending human input.

    Includes type, content, and whether it modifies the spec.
    """

    input_type: str = Field(
        description="Type of input (comment, pause, resume, abort)",
    )
    content: str = Field(
        description="Content of the human input",
    )
    spec_modified: bool = Field(
        default=False,
        description="True if this input modifies the spec",
    )


# =============================================================================
# Main Claims Structure
# =============================================================================


class Claims(BaseModel):
    """Complete claims output from SENSE phase.

    Contains all gathered information from code, work, project,
    human input, and learnings sources.
    """

    timestamp: datetime = Field(
        description="When SENSE was executed",
    )
    iteration_number: int = Field(
        description="Current iteration number",
    )
    code_state: CodeStateClaims = Field(
        description="Claims about code state (git)",
    )
    work_state: WorkStateClaims = Field(
        description="Claims about work state (trace)",
    )
    project_state: ProjectStateClaims = Field(
        description="Claims about project state (database)",
    )
    human_input: Optional[HumanInputClaims] = Field(
        default=None,
        description="Pending human input (if any)",
    )
    learnings: str = Field(
        default="",
        description="Content from memory.md (learnings)",
    )
