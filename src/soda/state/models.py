"""Data models for Soda state management."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import json


class RunStatus(Enum):
    """Status of a Soda run."""

    RUNNING = "running"
    DONE = "done"
    STUCK = "stuck"
    PAUSED = "paused"
    ABORTED = "aborted"


class IterationOutcome(Enum):
    """Outcome of an iteration."""

    CONTINUE = "continue"
    DONE = "done"
    STUCK = "stuck"


class AgentType(Enum):
    """Type of agent."""

    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"


class InputType(Enum):
    """Type of human input."""

    COMMENT = "comment"
    PAUSE = "pause"
    RESUME = "resume"
    ABORT = "abort"


@dataclass
class Run:
    """Represents a Soda run."""

    id: str
    spec_path: str
    spec_content: str
    status: RunStatus
    config: dict
    started_at: datetime
    ended_at: Optional[datetime] = None
    root_work_item_id: Optional[str] = None
    milestone_branch: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "spec_path": self.spec_path,
            "spec_content": self.spec_content,
            "status": self.status.value,
            "config": json.dumps(self.config),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "root_work_item_id": self.root_work_item_id,
            "milestone_branch": self.milestone_branch,
        }


@dataclass
class Iteration:
    """Represents an iteration within a run."""

    id: Optional[int]
    run_id: str
    number: int
    intent: str
    outcome: IterationOutcome
    started_at: datetime
    ended_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "number": self.number,
            "intent": self.intent,
            "outcome": self.outcome.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


@dataclass
class AgentOutput:
    """Represents output from an agent (Planner, Executor, or Verifier)."""

    id: Optional[int]
    iteration_id: int
    agent_type: AgentType
    raw_output_path: str
    summary: str

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "iteration_id": self.iteration_id,
            "agent_type": self.agent_type.value,
            "raw_output_path": self.raw_output_path,
            "summary": self.summary,
        }


@dataclass
class HumanInput:
    """Represents human input to influence Soda's behavior."""

    id: Optional[int]
    run_id: str
    input_type: InputType
    content: str
    created_at: datetime
    consumed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "input_type": self.input_type.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
        }
