"""Data models for Ralph2 state management."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json


@dataclass
class Run:
    """Represents a Ralph2 run."""
    id: str
    spec_path: str
    spec_content: str
    status: str  # running, completed, stuck, paused, aborted
    config: dict
    started_at: datetime
    ended_at: Optional[datetime] = None
    root_work_item_id: Optional[str] = None
    milestone_branch: Optional[str] = None  # Feature branch for milestone isolation

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spec_path": self.spec_path,
            "spec_content": self.spec_content,
            "status": self.status,
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
    outcome: str  # continue, done, stuck
    started_at: datetime
    ended_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "number": self.number,
            "intent": self.intent,
            "outcome": self.outcome,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


@dataclass
class AgentOutput:
    """Represents output from an agent (Planner, Executor, or Verifier)."""
    id: Optional[int]
    iteration_id: int
    agent_type: str  # planner, executor, verifier
    raw_output_path: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "iteration_id": self.iteration_id,
            "agent_type": self.agent_type,
            "raw_output_path": self.raw_output_path,
            "summary": self.summary,
        }


@dataclass
class HumanInput:
    """Represents human input to influence Ralph2's behavior."""
    id: Optional[int]
    run_id: str
    input_type: str  # comment, pause, resume, abort
    content: str
    created_at: datetime
    consumed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "input_type": self.input_type,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
        }
