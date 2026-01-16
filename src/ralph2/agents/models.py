"""Pydantic models for structured agent outputs.

These models define the exact shape of data returned by each agent.
The SDK validates agent output against these schemas, guaranteeing valid JSON.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


# =============================================================================
# Planner Output Models
# =============================================================================

class WorkItemAssignment(BaseModel):
    """A work item assigned to an executor."""
    work_item_id: str = Field(description="The work item ID from Trace (e.g., 'ralph-abc123')")
    description: str = Field(description="Brief description of what this work item involves")
    executor_number: int = Field(description="Which executor is assigned (1, 2, 3, ...)")


class IterationPlan(BaseModel):
    """Plan for parallel executor work in this iteration."""
    executor_count: int = Field(description="Number of executors to run in parallel (1-4)")
    work_items: list[WorkItemAssignment] = Field(description="Work items assigned to executors")


class PlannerResult(BaseModel):
    """Structured output from the Planner agent."""
    decision: Literal["CONTINUE", "DONE", "STUCK"] = Field(
        description="Termination decision: CONTINUE (work remaining), DONE (spec satisfied), STUCK (blocked)"
    )
    reason: str = Field(description="Brief explanation of the decision")
    blocker: Optional[str] = Field(
        default=None,
        description="What's blocking progress (required if decision is STUCK)"
    )
    iteration_intent: str = Field(
        description="1-2 sentence summary of what this iteration will accomplish"
    )
    iteration_plan: Optional[IterationPlan] = Field(
        default=None,
        description="Plan for executor work (required if decision is CONTINUE)"
    )
    memory_updates: Optional[str] = Field(
        default=None,
        description="Summary of changes made to project memory (if any)"
    )


# =============================================================================
# Executor Output Models
# =============================================================================

class ExecutorResult(BaseModel):
    """Structured output from the Executor agent."""
    status: Literal["Completed", "Blocked", "Uncertain"] = Field(
        description="Completion status: Completed (work done), Blocked (cannot proceed), Uncertain (needs guidance)"
    )
    what_was_done: str = Field(description="Brief description of work completed")
    blockers: Optional[str] = Field(
        default=None,
        description="What's blocking progress (if status is Blocked)"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Anything learned or worth mentioning"
    )
    efficiency_notes: Optional[str] = Field(
        default=None,
        description="Insights that would save time in future iterations"
    )
    work_committed: bool = Field(
        description="Have you committed all your changes to the work branch? (git add, git commit)"
    )
    traces_updated: bool = Field(
        description="Are all your traces up to date with comments and status changes?"
    )


# =============================================================================
# Verifier Output Models
# =============================================================================

class CriterionStatus(BaseModel):
    """Status of a single acceptance criterion."""
    criterion: str = Field(description="The acceptance criterion text")
    status: Literal["satisfied", "not_satisfied", "unverifiable"] = Field(
        description="Whether the criterion is satisfied, not satisfied, or unverifiable"
    )
    evidence: str = Field(description="Evidence supporting the status determination")


class VerifierResult(BaseModel):
    """Structured output from the Verifier agent."""
    outcome: Literal["DONE", "CONTINUE", "STUCK"] = Field(
        description="Verification outcome: DONE (all criteria satisfied), CONTINUE (work remaining), STUCK (blocked)"
    )
    criteria_status: list[CriterionStatus] = Field(
        description="Status of each acceptance criterion"
    )
    gaps: Optional[list[str]] = Field(
        default=None,
        description="List of unsatisfied criteria (if outcome is CONTINUE)"
    )
    blocker: Optional[str] = Field(
        default=None,
        description="What resources are needed to unblock (if outcome is STUCK)"
    )
    required_configuration: Optional[list[str]] = Field(
        default=None,
        description="Specific credentials or resources needed (if outcome is STUCK)"
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="How user should provide resources to unblock (if outcome is STUCK)"
    )
    efficiency_notes: Optional[str] = Field(
        default=None,
        description="Insights that would save time in future iterations"
    )


# =============================================================================
# Specialist Output Models
# =============================================================================

class FeedbackItem(BaseModel):
    """A single feedback item from a specialist."""
    priority: Literal["P0", "P1", "P2", "P3"] = Field(
        description="Priority: P0 (critical), P1 (high), P2 (medium), P3 (low)"
    )
    location: str = Field(description="File path and line range (e.g., 'src/auth.py:45-60')")
    issue: str = Field(description="Description of the issue")
    impact: str = Field(description="Why this matters")
    suggestion: str = Field(description="Suggested fix direction (not full implementation)")


class SpecialistResult(BaseModel):
    """Structured output from a Specialist agent."""
    specialist_name: str = Field(description="Name of the specialist (e.g., 'code_reviewer')")
    feedback_items: list[FeedbackItem] = Field(
        description="List of feedback items, sorted by priority"
    )
    summary: Optional[str] = Field(
        default=None,
        description="Overall summary of findings"
    )
