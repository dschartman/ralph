"""Tests for Soda SQLite database operations."""

import pytest
import tempfile
import os
from datetime import datetime
from pathlib import Path

from soda.state.db import SodaDB
from soda.state.models import (
    Run,
    RunStatus,
    Iteration,
    IterationOutcome,
    AgentOutput,
    AgentType,
    HumanInput,
    InputType,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test_soda.db")


@pytest.fixture
def db(db_path):
    """Create a SodaDB instance."""
    database = SodaDB(db_path)
    yield database
    database.close()


class TestSodaDBInit:
    """Tests for SodaDB initialization."""

    def test_creates_database_file(self, tmp_path):
        """SodaDB creates the database file."""
        db_path = str(tmp_path / "new_soda.db")
        db = SodaDB(db_path)
        assert Path(db_path).exists()
        db.close()

    def test_creates_parent_directories(self, tmp_path):
        """SodaDB creates parent directories if they don't exist."""
        db_path = str(tmp_path / "nested" / "dir" / "soda.db")
        db = SodaDB(db_path)
        assert Path(db_path).exists()
        db.close()

    def test_creates_tables(self, db):
        """SodaDB creates the required tables."""
        cursor = db.conn.cursor()

        # Check runs table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
        assert cursor.fetchone() is not None

        # Check iterations table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='iterations'")
        assert cursor.fetchone() is not None

        # Check agent_outputs table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_outputs'")
        assert cursor.fetchone() is not None

        # Check human_inputs table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='human_inputs'")
        assert cursor.fetchone() is not None


class TestRunOperations:
    """Tests for Run CRUD operations."""

    def test_create_run(self, db):
        """Can create a run."""
        now = datetime.now()
        run = Run(
            id="run-123",
            spec_path="spec.md",
            spec_content="# Test Spec",
            status=RunStatus.RUNNING,
            config={"key": "value"},
            started_at=now,
        )

        created = db.create_run(run)

        assert created.id == "run-123"
        assert created.status == RunStatus.RUNNING

    def test_get_run(self, db):
        """Can retrieve a run by ID."""
        now = datetime.now()
        run = Run(
            id="run-456",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={"nested": {"data": 1}},
            started_at=now,
        )
        db.create_run(run)

        retrieved = db.get_run("run-456")

        assert retrieved is not None
        assert retrieved.id == "run-456"
        assert retrieved.spec_path == "spec.md"
        assert retrieved.spec_content == "# Content"
        assert retrieved.status == RunStatus.RUNNING
        assert retrieved.config == {"nested": {"data": 1}}

    def test_get_run_not_found(self, db):
        """Returns None for non-existent run."""
        result = db.get_run("nonexistent-id")
        assert result is None

    def test_update_run_status(self, db):
        """Can update run status."""
        now = datetime.now()
        ended = datetime.now()
        run = Run(
            id="run-789",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        db.update_run_status("run-789", RunStatus.DONE, ended)

        retrieved = db.get_run("run-789")
        assert retrieved.status == RunStatus.DONE
        assert retrieved.ended_at is not None

    def test_get_latest_run(self, db):
        """Can get the most recent run."""
        now1 = datetime(2026, 1, 20, 10, 0, 0)
        now2 = datetime(2026, 1, 20, 11, 0, 0)

        run1 = Run(
            id="run-first",
            spec_path="spec1.md",
            spec_content="# First",
            status=RunStatus.DONE,
            config={},
            started_at=now1,
        )
        run2 = Run(
            id="run-second",
            spec_path="spec2.md",
            spec_content="# Second",
            status=RunStatus.RUNNING,
            config={},
            started_at=now2,
        )
        db.create_run(run1)
        db.create_run(run2)

        latest = db.get_latest_run()

        assert latest.id == "run-second"

    def test_get_latest_run_empty(self, db):
        """Returns None when no runs exist."""
        result = db.get_latest_run()
        assert result is None

    def test_list_runs(self, db):
        """Can list all runs."""
        now1 = datetime(2026, 1, 20, 10, 0, 0)
        now2 = datetime(2026, 1, 20, 11, 0, 0)

        run1 = Run(
            id="run-a",
            spec_path="spec.md",
            spec_content="# A",
            status=RunStatus.DONE,
            config={},
            started_at=now1,
        )
        run2 = Run(
            id="run-b",
            spec_path="spec.md",
            spec_content="# B",
            status=RunStatus.RUNNING,
            config={},
            started_at=now2,
        )
        db.create_run(run1)
        db.create_run(run2)

        runs = db.list_runs()

        assert len(runs) == 2
        # Should be ordered by started_at DESC
        assert runs[0].id == "run-b"
        assert runs[1].id == "run-a"

    def test_run_with_optional_fields(self, db):
        """Can store and retrieve run with optional fields."""
        now = datetime.now()
        ended = datetime.now()
        run = Run(
            id="run-full",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.DONE,
            config={},
            started_at=now,
            ended_at=ended,
            root_work_item_id="work-123",
            milestone_branch="feature/test",
        )
        db.create_run(run)

        retrieved = db.get_run("run-full")

        assert retrieved.ended_at is not None
        assert retrieved.root_work_item_id == "work-123"
        assert retrieved.milestone_branch == "feature/test"


class TestIterationOperations:
    """Tests for Iteration CRUD operations."""

    def test_create_iteration(self, db):
        """Can create an iteration."""
        # First create a run
        now = datetime.now()
        run = Run(
            id="run-iter",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="run-iter",
            number=1,
            intent="Implement feature X",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )

        created = db.create_iteration(iteration)

        assert created.id is not None
        assert created.run_id == "run-iter"
        assert created.number == 1

    def test_get_iteration(self, db):
        """Can retrieve an iteration by ID."""
        now = datetime.now()
        run = Run(
            id="run-get-iter",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="run-get-iter",
            number=1,
            intent="Test intent",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        created = db.create_iteration(iteration)

        retrieved = db.get_iteration(created.id)

        assert retrieved is not None
        assert retrieved.intent == "Test intent"
        assert retrieved.outcome == IterationOutcome.CONTINUE

    def test_get_iteration_not_found(self, db):
        """Returns None for non-existent iteration."""
        result = db.get_iteration(99999)
        assert result is None

    def test_update_iteration(self, db):
        """Can update iteration outcome and end time."""
        now = datetime.now()
        ended = datetime.now()
        run = Run(
            id="run-upd-iter",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="run-upd-iter",
            number=1,
            intent="Test",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        created = db.create_iteration(iteration)

        db.update_iteration(created.id, IterationOutcome.DONE, ended)

        retrieved = db.get_iteration(created.id)
        assert retrieved.outcome == IterationOutcome.DONE
        assert retrieved.ended_at is not None

    def test_get_iterations(self, db):
        """Can list iterations for a run (alias for list_iterations)."""
        now = datetime.now()
        run = Run(
            id="run-list-iter",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iter1 = Iteration(
            id=None,
            run_id="run-list-iter",
            number=1,
            intent="First",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        iter2 = Iteration(
            id=None,
            run_id="run-list-iter",
            number=2,
            intent="Second",
            outcome=IterationOutcome.DONE,
            started_at=now,
        )
        db.create_iteration(iter1)
        db.create_iteration(iter2)

        iterations = db.get_iterations("run-list-iter")

        assert len(iterations) == 2
        assert iterations[0].number == 1
        assert iterations[1].number == 2

    def test_get_latest_iteration(self, db):
        """Can get the most recent iteration for a run."""
        now = datetime.now()
        run = Run(
            id="run-latest-iter",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iter1 = Iteration(
            id=None,
            run_id="run-latest-iter",
            number=1,
            intent="First",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        iter2 = Iteration(
            id=None,
            run_id="run-latest-iter",
            number=2,
            intent="Second",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        db.create_iteration(iter1)
        db.create_iteration(iter2)

        latest = db.get_latest_iteration("run-latest-iter")

        assert latest.number == 2

    def test_get_latest_iteration_empty(self, db):
        """Returns None when no iterations exist for a run."""
        result = db.get_latest_iteration("nonexistent-run")
        assert result is None


class TestAgentOutputOperations:
    """Tests for AgentOutput CRUD operations."""

    def test_create_agent_output(self, db):
        """Can create an agent output."""
        now = datetime.now()
        run = Run(
            id="run-output",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="run-output",
            number=1,
            intent="Test",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        created_iter = db.create_iteration(iteration)

        output = AgentOutput(
            id=None,
            iteration_id=created_iter.id,
            agent_type=AgentType.PLANNER,
            raw_output_path="outputs/planner_123.jsonl",
            summary="Planned 3 tasks",
        )

        created = db.create_agent_output(output)

        assert created.id is not None
        assert created.agent_type == AgentType.PLANNER

    def test_get_agent_outputs(self, db):
        """Can get all agent outputs for an iteration."""
        now = datetime.now()
        run = Run(
            id="run-get-outputs",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="run-get-outputs",
            number=1,
            intent="Test",
            outcome=IterationOutcome.CONTINUE,
            started_at=now,
        )
        created_iter = db.create_iteration(iteration)

        output1 = AgentOutput(
            id=None,
            iteration_id=created_iter.id,
            agent_type=AgentType.PLANNER,
            raw_output_path="outputs/planner.jsonl",
            summary="Planned tasks",
        )
        output2 = AgentOutput(
            id=None,
            iteration_id=created_iter.id,
            agent_type=AgentType.EXECUTOR,
            raw_output_path="outputs/executor.jsonl",
            summary="Executed tasks",
        )
        db.create_agent_output(output1)
        db.create_agent_output(output2)

        outputs = db.get_agent_outputs(created_iter.id)

        assert len(outputs) == 2


class TestHumanInputOperations:
    """Tests for HumanInput CRUD operations."""

    def test_create_human_input(self, db):
        """Can create a human input."""
        now = datetime.now()
        run = Run(
            id="run-input",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        human_input = HumanInput(
            id=None,
            run_id="run-input",
            input_type=InputType.COMMENT,
            content="Focus on tests",
            created_at=now,
        )

        created = db.create_human_input(human_input)

        assert created.id is not None
        assert created.input_type == InputType.COMMENT

    def test_get_unconsumed_inputs(self, db):
        """Can get unconsumed human inputs for a run."""
        now = datetime.now()
        run = Run(
            id="run-unconsumed",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        input1 = HumanInput(
            id=None,
            run_id="run-unconsumed",
            input_type=InputType.COMMENT,
            content="First comment",
            created_at=now,
        )
        input2 = HumanInput(
            id=None,
            run_id="run-unconsumed",
            input_type=InputType.PAUSE,
            content="",
            created_at=now,
            consumed_at=now,  # Already consumed
        )
        input3 = HumanInput(
            id=None,
            run_id="run-unconsumed",
            input_type=InputType.COMMENT,
            content="Second comment",
            created_at=now,
        )
        db.create_human_input(input1)
        db.create_human_input(input2)
        db.create_human_input(input3)

        unconsumed = db.get_unconsumed_inputs("run-unconsumed")

        assert len(unconsumed) == 2
        assert unconsumed[0].content == "First comment"
        assert unconsumed[1].content == "Second comment"

    def test_mark_input_consumed(self, db):
        """Can mark a human input as consumed."""
        now = datetime.now()
        consumed_time = datetime.now()
        run = Run(
            id="run-consume",
            spec_path="spec.md",
            spec_content="# Content",
            status=RunStatus.RUNNING,
            config={},
            started_at=now,
        )
        db.create_run(run)

        human_input = HumanInput(
            id=None,
            run_id="run-consume",
            input_type=InputType.COMMENT,
            content="Test",
            created_at=now,
        )
        created = db.create_human_input(human_input)

        db.mark_input_consumed(created.id, consumed_time)

        # Verify by checking unconsumed inputs
        unconsumed = db.get_unconsumed_inputs("run-consume")
        assert len(unconsumed) == 0


class TestTransactions:
    """Tests for transaction support."""

    def test_transaction_commit(self, db):
        """Transaction commits on success."""
        now = datetime.now()

        with db.transaction():
            run = Run(
                id="run-tx-commit",
                spec_path="spec.md",
                spec_content="# Content",
                status=RunStatus.RUNNING,
                config={},
                started_at=now,
            )
            db.create_run(run)

        # Should be persisted
        retrieved = db.get_run("run-tx-commit")
        assert retrieved is not None

    def test_transaction_rollback(self, db):
        """Transaction rolls back on error."""
        now = datetime.now()

        try:
            with db.transaction():
                run = Run(
                    id="run-tx-rollback",
                    spec_path="spec.md",
                    spec_content="# Content",
                    status=RunStatus.RUNNING,
                    config={},
                    started_at=now,
                )
                db.create_run(run)
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Should not be persisted
        retrieved = db.get_run("run-tx-rollback")
        assert retrieved is None


class TestClose:
    """Tests for database close behavior."""

    def test_close(self, db_path):
        """Can close the database connection."""
        db = SodaDB(db_path)
        db.close()
        # Should be able to close without error

    def test_close_multiple_times(self, db_path):
        """Can close multiple times safely."""
        db = SodaDB(db_path)
        db.close()
        db.close()  # Should not raise
