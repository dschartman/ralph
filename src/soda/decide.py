"""Data structures for DECIDE phase output.

The DECIDE phase routes based on ORIENT's structured output using
deterministic logic. It returns one of three outcomes: DONE, STUCK, or CONTINUE.

This module contains no agent logic - it's pure orchestrator code.
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
