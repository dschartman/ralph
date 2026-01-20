"""Data structures and routing logic for DECIDE phase.

The DECIDE phase routes based on ORIENT's structured output using
deterministic logic. It returns one of three outcomes: DONE, STUCK, or CONTINUE.

This module contains no agent logic - it's pure orchestrator code.

Routing rules:
- spec_satisfied=true → DONE
- spec_satisfied=false AND actionable_work_exists=true → CONTINUE
- spec_satisfied=false AND actionable_work_exists=false → STUCK
- spec_satisfied=unverifiable AND actionable_work_exists=false → STUCK
- spec_satisfied=unverifiable AND actionable_work_exists=true → CONTINUE
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class DecisionOutcome(str, Enum):
    """Possible outcomes from the DECIDE phase.

    DONE: Spec is satisfied, work is complete
    STUCK: Cannot proceed (no actionable work exists)
    CONTINUE: Work should continue (actionable work exists)
    """

    DONE = "DONE"
    STUCK = "STUCK"
    CONTINUE = "CONTINUE"


class SpecSatisfied(str, Enum):
    """Possible values for spec_satisfied in ORIENT output.

    TRUE: All acceptance criteria are satisfied
    FALSE: Some acceptance criteria are not satisfied
    UNVERIFIABLE: Cannot verify criteria (requires external resources)
    """

    TRUE = "true"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"


class OrientOutput(BaseModel):
    """Minimal ORIENT output structure needed for DECIDE routing.

    This represents the subset of ORIENT's output that DECIDE needs
    to make routing decisions. The full ORIENT output may include
    additional fields (task_updates, new_tasks, iteration_plan, etc.).
    """

    spec_satisfied: SpecSatisfied = Field(
        description="Whether spec is satisfied: true, false, or unverifiable"
    )
    actionable_work_exists: bool = Field(
        description="Whether there is actionable work to do"
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Identified gaps (used for STUCK reason)",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Final assessment summary (used for DONE)",
    )


class Decision(BaseModel):
    """Output structure from the DECIDE phase.

    Constraints:
    - outcome=DONE requires summary (final assessment)
    - outcome=STUCK requires reason (from ORIENT gaps)
    - outcome=CONTINUE has no requirements

    All fields except outcome are optional, but validation ensures
    required fields are present based on outcome.
    """

    outcome: DecisionOutcome = Field(
        description="Decision outcome: DONE (complete), STUCK (blocked), CONTINUE (work exists)"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Required for STUCK: reason from ORIENT gaps",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Required for DONE: final assessment summary",
    )

    @model_validator(mode="after")
    def validate_constraints(self) -> "Decision":
        """Validate that required fields are present based on outcome."""
        if self.outcome == DecisionOutcome.DONE and self.summary is None:
            raise ValueError("summary is required when outcome is DONE")
        if self.outcome == DecisionOutcome.STUCK and self.reason is None:
            raise ValueError("reason is required when outcome is STUCK")
        return self


def decide(orient_output: OrientOutput) -> Decision:
    """Make a deterministic routing decision based on ORIENT output.

    Routing rules:
    1. spec_satisfied=true → DONE (with summary from ORIENT)
    2. spec_satisfied=false AND actionable_work_exists=true → CONTINUE
    3. spec_satisfied=false AND actionable_work_exists=false → STUCK (with reason from gaps)
    4. spec_satisfied=unverifiable AND actionable_work_exists=false → STUCK
    5. spec_satisfied=unverifiable AND actionable_work_exists=true → CONTINUE

    Args:
        orient_output: The structured output from ORIENT phase

    Returns:
        Decision with outcome, and reason (if STUCK) or summary (if DONE)
    """
    # Rule 1: spec_satisfied=true → DONE (takes precedence)
    if orient_output.spec_satisfied == SpecSatisfied.TRUE:
        return Decision(
            outcome=DecisionOutcome.DONE,
            summary=orient_output.summary or "Spec satisfied",
        )

    # Rules 2-5: Need to check actionable_work_exists
    if orient_output.actionable_work_exists:
        # Rules 2 and 5: actionable work exists → CONTINUE
        return Decision(outcome=DecisionOutcome.CONTINUE)
    else:
        # Rules 3 and 4: no actionable work → STUCK
        # Build reason from gaps
        if orient_output.gaps:
            reason = "; ".join(orient_output.gaps)
        else:
            reason = "No actionable work exists and spec is not satisfied"
        return Decision(
            outcome=DecisionOutcome.STUCK,
            reason=reason,
        )
