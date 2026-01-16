"""Tests for state module (db.py and models.py)."""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run, Iteration, AgentOutput, HumanInput


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ralph.db")
        db = Ralph2DB(db_path)
        yield db
        db.close()


@pytest.fixture
def sample_run():
    """Create a sample Run object for testing."""
    return Run(
        id="test-run-123",
        spec_path="Ralphfile",
        spec_content="# Test Spec\nImplement feature X",
        status="running",
        config={"max_iterations": 10},
        started_at=datetime(2024, 1, 15, 10, 30, 0)
    )


@pytest.fixture
def sample_iteration():
    """Create a sample Iteration object for testing."""
    return Iteration(
        id=None,
        run_id="test-run-123",
        number=1,
        intent="Work on task A",
        outcome="continue",
        started_at=datetime(2024, 1, 15, 10, 35, 0)
    )


@pytest.fixture
def sample_agent_output():
    """Create a sample AgentOutput object for testing."""
    return AgentOutput(
        id=None,
        iteration_id=1,
        agent_type="planner",
        raw_output_path=".ralph/outputs/planner_1.jsonl",
        summary="Created 3 tasks in Trace"
    )


@pytest.fixture
def sample_human_input():
    """Create a sample HumanInput object for testing."""
    return HumanInput(
        id=None,
        run_id="test-run-123",
        input_type="comment",
        content="Please focus on the authentication module first",
        created_at=datetime(2024, 1, 15, 11, 0, 0)
    )


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""

    def test_database_file_created(self):
        """Test that database file is created at specified path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            assert not os.path.exists(db_path)

            db = Ralph2DB(db_path)

            assert os.path.exists(db_path)
            db.close()

    def test_database_directory_created_if_missing(self):
        """Test that parent directories are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "nested", "path", "test.db")
            assert not os.path.exists(os.path.dirname(db_path))

            db = Ralph2DB(db_path)

            assert os.path.exists(db_path)
            assert os.path.exists(os.path.dirname(db_path))
            db.close()

    def test_schema_tables_created(self, temp_db):
        """Test that all required tables are created in the schema."""
        cursor = temp_db.conn.cursor()

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

    def test_runs_table_columns(self, temp_db):
        """Test that runs table has correct columns."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(runs)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {'id', 'spec_path', 'spec_content', 'status', 'config', 'started_at', 'ended_at', 'root_work_item_id'}
        assert columns == expected_columns

    def test_iterations_table_columns(self, temp_db):
        """Test that iterations table has correct columns."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(iterations)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {'id', 'run_id', 'number', 'intent', 'outcome', 'started_at', 'ended_at'}
        assert columns == expected_columns

    def test_agent_outputs_table_columns(self, temp_db):
        """Test that agent_outputs table has correct columns."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(agent_outputs)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {'id', 'iteration_id', 'agent_type', 'raw_output_path', 'summary'}
        assert columns == expected_columns

    def test_human_inputs_table_columns(self, temp_db):
        """Test that human_inputs table has correct columns."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(human_inputs)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {'id', 'run_id', 'input_type', 'content', 'created_at', 'consumed_at'}
        assert columns == expected_columns


class TestRunOperations:
    """Test Run CRUD operations."""

    def test_create_run(self, temp_db, sample_run):
        """Test creating a new run."""
        created_run = temp_db.create_run(sample_run)

        assert created_run.id == sample_run.id
        assert created_run.spec_path == sample_run.spec_path
        assert created_run.status == sample_run.status

    def test_get_run_by_id(self, temp_db, sample_run):
        """Test retrieving a run by ID."""
        temp_db.create_run(sample_run)

        retrieved_run = temp_db.get_run(sample_run.id)

        assert retrieved_run is not None
        assert retrieved_run.id == sample_run.id
        assert retrieved_run.spec_path == sample_run.spec_path
        assert retrieved_run.spec_content == sample_run.spec_content
        assert retrieved_run.status == sample_run.status
        assert retrieved_run.config == sample_run.config
        assert retrieved_run.started_at == sample_run.started_at
        assert retrieved_run.ended_at is None

    def test_get_nonexistent_run(self, temp_db):
        """Test retrieving a run that doesn't exist."""
        retrieved_run = temp_db.get_run("nonexistent-id")

        assert retrieved_run is None

    def test_update_run_status(self, temp_db, sample_run):
        """Test updating a run's status."""
        temp_db.create_run(sample_run)
        ended_at = datetime(2024, 1, 15, 12, 0, 0)

        temp_db.update_run_status(sample_run.id, "completed", ended_at)

        updated_run = temp_db.get_run(sample_run.id)
        assert updated_run.status == "completed"
        assert updated_run.ended_at == ended_at

    def test_get_latest_run(self, temp_db):
        """Test retrieving the most recent run."""
        run1 = Run(
            id="run-1",
            spec_path="Ralphfile",
            spec_content="Spec 1",
            status="completed",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        run2 = Run(
            id="run-2",
            spec_path="Ralphfile",
            spec_content="Spec 2",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        run3 = Run(
            id="run-3",
            spec_path="Ralphfile",
            spec_content="Spec 3",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 9, 0, 0)
        )

        temp_db.create_run(run1)
        temp_db.create_run(run2)
        temp_db.create_run(run3)

        latest_run = temp_db.get_latest_run()

        assert latest_run is not None
        assert latest_run.id == "run-2"  # Most recent by started_at

    def test_get_latest_run_when_empty(self, temp_db):
        """Test retrieving latest run when no runs exist."""
        latest_run = temp_db.get_latest_run()

        assert latest_run is None

    def test_list_runs(self, temp_db):
        """Test listing all runs in descending order by started_at."""
        run1 = Run(
            id="run-1",
            spec_path="Ralphfile",
            spec_content="Spec 1",
            status="completed",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        run2 = Run(
            id="run-2",
            spec_path="Ralphfile",
            spec_content="Spec 2",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 11, 0, 0)
        )

        temp_db.create_run(run1)
        temp_db.create_run(run2)

        runs = temp_db.list_runs()

        assert len(runs) == 2
        assert runs[0].id == "run-2"  # Most recent first
        assert runs[1].id == "run-1"

    def test_list_runs_when_empty(self, temp_db):
        """Test listing runs when database is empty."""
        runs = temp_db.list_runs()

        assert len(runs) == 0

    def test_run_config_json_serialization(self, temp_db):
        """Test that run config is properly serialized and deserialized."""
        complex_config = {
            "max_iterations": 10,
            "timeout": 3600,
            "flags": ["verbose", "debug"],
            "nested": {"key": "value"}
        }
        run = Run(
            id="run-config-test",
            spec_path="Ralphfile",
            spec_content="Test",
            status="running",
            config=complex_config,
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )

        temp_db.create_run(run)
        retrieved_run = temp_db.get_run(run.id)

        assert retrieved_run.config == complex_config


class TestIterationOperations:
    """Test Iteration CRUD operations."""

    def test_create_iteration(self, temp_db, sample_run, sample_iteration):
        """Test creating a new iteration."""
        temp_db.create_run(sample_run)

        created_iteration = temp_db.create_iteration(sample_iteration)

        assert created_iteration.id is not None
        assert created_iteration.run_id == sample_iteration.run_id
        assert created_iteration.number == sample_iteration.number
        assert created_iteration.intent == sample_iteration.intent

    def test_get_iteration_by_id(self, temp_db, sample_run, sample_iteration):
        """Test retrieving an iteration by ID."""
        temp_db.create_run(sample_run)
        created = temp_db.create_iteration(sample_iteration)

        retrieved_iteration = temp_db.get_iteration(created.id)

        assert retrieved_iteration is not None
        assert retrieved_iteration.id == created.id
        assert retrieved_iteration.run_id == sample_iteration.run_id
        assert retrieved_iteration.number == sample_iteration.number
        assert retrieved_iteration.intent == sample_iteration.intent
        assert retrieved_iteration.outcome == sample_iteration.outcome
        assert retrieved_iteration.started_at == sample_iteration.started_at
        assert retrieved_iteration.ended_at is None

    def test_get_nonexistent_iteration(self, temp_db):
        """Test retrieving an iteration that doesn't exist."""
        retrieved_iteration = temp_db.get_iteration(999)

        assert retrieved_iteration is None

    def test_update_iteration(self, temp_db, sample_run, sample_iteration):
        """Test updating an iteration's outcome and end time."""
        temp_db.create_run(sample_run)
        created = temp_db.create_iteration(sample_iteration)
        ended_at = datetime(2024, 1, 15, 10, 45, 0)

        temp_db.update_iteration(created.id, "done", ended_at)

        updated_iteration = temp_db.get_iteration(created.id)
        assert updated_iteration.outcome == "done"
        assert updated_iteration.ended_at == ended_at

    def test_list_iterations_for_run(self, temp_db, sample_run):
        """Test listing all iterations for a specific run."""
        temp_db.create_run(sample_run)

        iter1 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First task",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        iter2 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=2,
            intent="Second task",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 35, 0)
        )

        temp_db.create_iteration(iter1)
        temp_db.create_iteration(iter2)

        iterations = temp_db.list_iterations(sample_run.id)

        assert len(iterations) == 2
        assert iterations[0].number == 1
        assert iterations[1].number == 2

    def test_list_iterations_for_nonexistent_run(self, temp_db):
        """Test listing iterations for a run that doesn't exist."""
        iterations = temp_db.list_iterations("nonexistent-run")

        assert len(iterations) == 0

    def test_iterations_ordered_by_number(self, temp_db, sample_run):
        """Test that iterations are returned in order by number."""
        temp_db.create_run(sample_run)

        # Create iterations out of order
        iter3 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=3,
            intent="Third",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        iter1 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 32, 0)
        )
        iter2 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=2,
            intent="Second",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 31, 0)
        )

        temp_db.create_iteration(iter3)
        temp_db.create_iteration(iter1)
        temp_db.create_iteration(iter2)

        iterations = temp_db.list_iterations(sample_run.id)

        assert iterations[0].number == 1
        assert iterations[1].number == 2
        assert iterations[2].number == 3

    def test_get_latest_iteration(self, temp_db, sample_run):
        """Test retrieving the most recent iteration for a run."""
        temp_db.create_run(sample_run)

        iter1 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        iter2 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=2,
            intent="Second iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 45, 0)
        )
        iter3 = Iteration(
            id=None,
            run_id=sample_run.id,
            number=3,
            intent="Third iteration",
            outcome="done",
            started_at=datetime(2024, 1, 15, 11, 0, 0)
        )

        temp_db.create_iteration(iter1)
        temp_db.create_iteration(iter2)
        temp_db.create_iteration(iter3)

        latest = temp_db.get_latest_iteration(sample_run.id)

        assert latest is not None
        assert latest.number == 3
        assert latest.intent == "Third iteration"
        assert latest.outcome == "done"

    def test_get_latest_iteration_when_empty(self, temp_db, sample_run):
        """Test getting latest iteration when no iterations exist."""
        temp_db.create_run(sample_run)

        latest = temp_db.get_latest_iteration(sample_run.id)

        assert latest is None


class TestAgentOutputOperations:
    """Test AgentOutput CRUD operations."""

    def test_create_agent_output(self, temp_db, sample_run, sample_iteration, sample_agent_output):
        """Test creating a new agent output."""
        temp_db.create_run(sample_run)
        created_iteration = temp_db.create_iteration(sample_iteration)
        sample_agent_output.iteration_id = created_iteration.id

        created_output = temp_db.create_agent_output(sample_agent_output)

        assert created_output.id is not None
        assert created_output.iteration_id == created_iteration.id
        assert created_output.agent_type == sample_agent_output.agent_type
        assert created_output.raw_output_path == sample_agent_output.raw_output_path
        assert created_output.summary == sample_agent_output.summary

    def test_get_agent_outputs_for_iteration(self, temp_db, sample_run, sample_iteration):
        """Test retrieving all agent outputs for an iteration."""
        temp_db.create_run(sample_run)
        created_iteration = temp_db.create_iteration(sample_iteration)

        planner_output = AgentOutput(
            id=None,
            iteration_id=created_iteration.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_1.jsonl",
            summary="Planned 3 tasks"
        )
        executor_output = AgentOutput(
            id=None,
            iteration_id=created_iteration.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_1.jsonl",
            summary="Completed task A"
        )
        verifier_output = AgentOutput(
            id=None,
            iteration_id=created_iteration.id,
            agent_type="verifier",
            raw_output_path=".ralph/outputs/verifier_1.jsonl",
            summary="CONTINUE - 2 items remaining"
        )

        temp_db.create_agent_output(planner_output)
        temp_db.create_agent_output(executor_output)
        temp_db.create_agent_output(verifier_output)

        outputs = temp_db.get_agent_outputs(created_iteration.id)

        assert len(outputs) == 3
        agent_types = {output.agent_type for output in outputs}
        assert agent_types == {"planner", "executor", "verifier"}

    def test_get_agent_outputs_for_nonexistent_iteration(self, temp_db):
        """Test retrieving agent outputs for an iteration that doesn't exist."""
        outputs = temp_db.get_agent_outputs(999)

        assert len(outputs) == 0

    def test_agent_output_all_fields_preserved(self, temp_db, sample_run, sample_iteration):
        """Test that all agent output fields are correctly stored and retrieved."""
        temp_db.create_run(sample_run)
        created_iteration = temp_db.create_iteration(sample_iteration)

        output = AgentOutput(
            id=None,
            iteration_id=created_iteration.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_1.jsonl",
            summary="Status: Completed\nWhat was done: Implemented feature X\nBlockers: None"
        )

        created = temp_db.create_agent_output(output)
        retrieved_outputs = temp_db.get_agent_outputs(created_iteration.id)
        retrieved = retrieved_outputs[0]

        assert retrieved.agent_type == "executor"
        assert retrieved.raw_output_path == ".ralph/outputs/executor_1.jsonl"
        assert "Status: Completed" in retrieved.summary
        assert "Implemented feature X" in retrieved.summary


class TestHumanInputOperations:
    """Test HumanInput CRUD operations."""

    def test_create_human_input(self, temp_db, sample_run, sample_human_input):
        """Test creating a new human input."""
        temp_db.create_run(sample_run)

        created_input = temp_db.create_human_input(sample_human_input)

        assert created_input.id is not None
        assert created_input.run_id == sample_human_input.run_id
        assert created_input.input_type == sample_human_input.input_type
        assert created_input.content == sample_human_input.content
        assert created_input.consumed_at is None

    def test_get_unconsumed_inputs(self, temp_db, sample_run):
        """Test retrieving unconsumed human inputs for a run."""
        temp_db.create_run(sample_run)

        input1 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Focus on authentication",
            created_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        input2 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Add unit tests",
            created_at=datetime(2024, 1, 15, 11, 5, 0)
        )

        temp_db.create_human_input(input1)
        temp_db.create_human_input(input2)

        unconsumed = temp_db.get_unconsumed_inputs(sample_run.id)

        assert len(unconsumed) == 2
        assert unconsumed[0].content == "Focus on authentication"
        assert unconsumed[1].content == "Add unit tests"

    def test_get_unconsumed_inputs_excludes_consumed(self, temp_db, sample_run):
        """Test that consumed inputs are not returned."""
        temp_db.create_run(sample_run)

        input1 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Unconsumed",
            created_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        input2 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Consumed",
            created_at=datetime(2024, 1, 15, 11, 5, 0)
        )

        created1 = temp_db.create_human_input(input1)
        created2 = temp_db.create_human_input(input2)

        # Mark input2 as consumed
        temp_db.mark_input_consumed(created2.id, datetime(2024, 1, 15, 11, 10, 0))

        unconsumed = temp_db.get_unconsumed_inputs(sample_run.id)

        assert len(unconsumed) == 1
        assert unconsumed[0].content == "Unconsumed"

    def test_mark_input_consumed(self, temp_db, sample_run, sample_human_input):
        """Test marking a human input as consumed."""
        temp_db.create_run(sample_run)
        created = temp_db.create_human_input(sample_human_input)
        consumed_at = datetime(2024, 1, 15, 11, 10, 0)

        temp_db.mark_input_consumed(created.id, consumed_at)

        unconsumed = temp_db.get_unconsumed_inputs(sample_run.id)
        assert len(unconsumed) == 0

    def test_human_input_types(self, temp_db, sample_run):
        """Test that different input types are stored correctly."""
        temp_db.create_run(sample_run)

        comment = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Please add tests",
            created_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        pause = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="pause",
            content="",
            created_at=datetime(2024, 1, 15, 11, 5, 0)
        )

        temp_db.create_human_input(comment)
        temp_db.create_human_input(pause)

        inputs = temp_db.get_unconsumed_inputs(sample_run.id)

        input_types = {inp.input_type for inp in inputs}
        assert input_types == {"comment", "pause"}

    def test_unconsumed_inputs_ordered_by_created_at(self, temp_db, sample_run):
        """Test that unconsumed inputs are returned in order by created_at."""
        temp_db.create_run(sample_run)

        input3 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Third",
            created_at=datetime(2024, 1, 15, 11, 10, 0)
        )
        input1 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="First",
            created_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        input2 = HumanInput(
            id=None,
            run_id=sample_run.id,
            input_type="comment",
            content="Second",
            created_at=datetime(2024, 1, 15, 11, 5, 0)
        )

        temp_db.create_human_input(input3)
        temp_db.create_human_input(input1)
        temp_db.create_human_input(input2)

        inputs = temp_db.get_unconsumed_inputs(sample_run.id)

        assert inputs[0].content == "First"
        assert inputs[1].content == "Second"
        assert inputs[2].content == "Third"


class TestDatabaseIsolation:
    """Test that temporary databases provide proper isolation."""

    def test_multiple_temp_databases_are_isolated(self):
        """Test that multiple temporary databases don't interfere with each other."""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            db1 = Ralph2DB(os.path.join(tmpdir1, "db1.db"))
            db2 = Ralph2DB(os.path.join(tmpdir2, "db2.db"))

            run1 = Run(
                id="run-1",
                spec_path="Ralphfile",
                spec_content="Spec 1",
                status="running",
                config={},
                started_at=datetime(2024, 1, 15, 10, 0, 0)
            )
            run2 = Run(
                id="run-2",
                spec_path="Ralphfile",
                spec_content="Spec 2",
                status="running",
                config={},
                started_at=datetime(2024, 1, 15, 11, 0, 0)
            )

            db1.create_run(run1)
            db2.create_run(run2)

            # Each database should only see its own data
            assert db1.get_run("run-1") is not None
            assert db1.get_run("run-2") is None
            assert db2.get_run("run-1") is None
            assert db2.get_run("run-2") is not None

            db1.close()
            db2.close()

    def test_temp_database_cleanup(self):
        """Test that temporary database files can be cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Ralph2DB(db_path)

            run = Run(
                id="test-run",
                spec_path="Ralphfile",
                spec_content="Test",
                status="running",
                config={},
                started_at=datetime(2024, 1, 15, 10, 0, 0)
            )
            db.create_run(run)

            assert os.path.exists(db_path)
            db.close()

            # File still exists after close, but can be deleted
            assert os.path.exists(db_path)
            os.remove(db_path)
            assert not os.path.exists(db_path)


class TestModelToDict:
    """Test model to_dict() methods for serialization."""

    def test_run_to_dict(self):
        """Test Run.to_dict() serialization."""
        run = Run(
            id="run-123",
            spec_path="Ralphfile",
            spec_content="Test spec",
            status="running",
            config={"key": "value"},
            started_at=datetime(2024, 1, 15, 10, 0, 0),
            ended_at=datetime(2024, 1, 15, 12, 0, 0)
        )

        run_dict = run.to_dict()

        assert run_dict["id"] == "run-123"
        assert run_dict["spec_path"] == "Ralphfile"
        assert run_dict["spec_content"] == "Test spec"
        assert run_dict["status"] == "running"
        assert run_dict["config"] == '{"key": "value"}'
        assert run_dict["started_at"] == "2024-01-15T10:00:00"
        assert run_dict["ended_at"] == "2024-01-15T12:00:00"

    def test_run_to_dict_with_none_ended_at(self):
        """Test Run.to_dict() with None ended_at."""
        run = Run(
            id="run-123",
            spec_path="Ralphfile",
            spec_content="Test spec",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )

        run_dict = run.to_dict()

        assert run_dict["ended_at"] is None

    def test_iteration_to_dict(self):
        """Test Iteration.to_dict() serialization."""
        iteration = Iteration(
            id=1,
            run_id="run-123",
            number=1,
            intent="Work on task A",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            ended_at=datetime(2024, 1, 15, 10, 45, 0)
        )

        iter_dict = iteration.to_dict()

        assert iter_dict["id"] == 1
        assert iter_dict["run_id"] == "run-123"
        assert iter_dict["number"] == 1
        assert iter_dict["intent"] == "Work on task A"
        assert iter_dict["outcome"] == "continue"
        assert iter_dict["started_at"] == "2024-01-15T10:30:00"
        assert iter_dict["ended_at"] == "2024-01-15T10:45:00"

    def test_agent_output_to_dict(self):
        """Test AgentOutput.to_dict() serialization."""
        output = AgentOutput(
            id=1,
            iteration_id=1,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_1.jsonl",
            summary="Created 3 tasks"
        )

        output_dict = output.to_dict()

        assert output_dict["id"] == 1
        assert output_dict["iteration_id"] == 1
        assert output_dict["agent_type"] == "planner"
        assert output_dict["raw_output_path"] == ".ralph/outputs/planner_1.jsonl"
        assert output_dict["summary"] == "Created 3 tasks"

    def test_human_input_to_dict(self):
        """Test HumanInput.to_dict() serialization."""
        human_input = HumanInput(
            id=1,
            run_id="run-123",
            input_type="comment",
            content="Please add tests",
            created_at=datetime(2024, 1, 15, 11, 0, 0),
            consumed_at=datetime(2024, 1, 15, 11, 10, 0)
        )

        input_dict = human_input.to_dict()

        assert input_dict["id"] == 1
        assert input_dict["run_id"] == "run-123"
        assert input_dict["input_type"] == "comment"
        assert input_dict["content"] == "Please add tests"
        assert input_dict["created_at"] == "2024-01-15T11:00:00"
        assert input_dict["consumed_at"] == "2024-01-15T11:10:00"


class TestAgentOutputQuerying:
    """Test querying agent outputs by iteration, type, and content."""

    def test_query_outputs_by_agent_type(self, temp_db, sample_run):
        """Test querying agent outputs by agent type."""
        temp_db.create_run(sample_run)

        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        ))

        iter2 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=2,
            intent="Second iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 45, 0)
        ))

        # Create outputs for different agents across iterations
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_1.jsonl",
            summary="Planned 3 tasks"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_1.jsonl",
            summary="Implemented feature X"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter2.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_2.jsonl",
            summary="Planned 2 more tasks"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter2.id,
            agent_type="verifier",
            raw_output_path=".ralph/outputs/verifier_2.jsonl",
            summary="Spec not met - 3 gaps remaining"
        ))

        # Query for planner outputs
        planner_outputs = temp_db.query_agent_outputs(agent_type="planner")
        assert len(planner_outputs) == 2
        assert all(o.agent_type == "planner" for o in planner_outputs)

        # Query for executor outputs
        executor_outputs = temp_db.query_agent_outputs(agent_type="executor")
        assert len(executor_outputs) == 1
        assert executor_outputs[0].agent_type == "executor"

    def test_query_outputs_by_run_id(self, temp_db):
        """Test querying agent outputs by run_id."""
        run1 = Run(
            id="run-1",
            spec_path="Ralphfile",
            spec_content="Spec 1",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        run2 = Run(
            id="run-2",
            spec_path="Ralphfile",
            spec_content="Spec 2",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 11, 0, 0)
        )

        temp_db.create_run(run1)
        temp_db.create_run(run2)

        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=run1.id,
            number=1,
            intent="Run 1 iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        ))

        iter2 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=run2.id,
            number=1,
            intent="Run 2 iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 11, 30, 0)
        ))

        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_r1_1.jsonl",
            summary="Run 1 planning"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter2.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_r2_1.jsonl",
            summary="Run 2 planning"
        ))

        # Query for run 1 outputs
        run1_outputs = temp_db.query_agent_outputs(run_id="run-1")
        assert len(run1_outputs) == 1
        assert "Run 1" in run1_outputs[0].summary

        # Query for run 2 outputs
        run2_outputs = temp_db.query_agent_outputs(run_id="run-2")
        assert len(run2_outputs) == 1
        assert "Run 2" in run2_outputs[0].summary

    def test_query_outputs_by_content(self, temp_db, sample_run):
        """Test querying agent outputs by content search."""
        temp_db.create_run(sample_run)

        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        ))

        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_1.jsonl",
            summary="Completed authentication module with JWT tokens"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_2.jsonl",
            summary="Implemented database migrations for user table"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="verifier",
            raw_output_path=".ralph/outputs/verifier_1.jsonl",
            summary="Spec not met - authentication tests missing"
        ))

        # Query for outputs containing "authentication"
        auth_outputs = temp_db.query_agent_outputs(content_search="authentication")
        assert len(auth_outputs) == 2
        assert all("authentication" in o.summary.lower() for o in auth_outputs)

        # Query for outputs containing "database"
        db_outputs = temp_db.query_agent_outputs(content_search="database")
        assert len(db_outputs) == 1
        assert "database" in db_outputs[0].summary.lower()

    def test_query_outputs_with_multiple_filters(self, temp_db, sample_run):
        """Test querying agent outputs with multiple filters combined."""
        temp_db.create_run(sample_run)

        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        ))

        iter2 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=2,
            intent="Second iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 45, 0)
        ))

        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_1.jsonl",
            summary="Completed task with authentication"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="verifier",
            raw_output_path=".ralph/outputs/verifier_1.jsonl",
            summary="Verified authentication works"
        ))
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter2.id,
            agent_type="executor",
            raw_output_path=".ralph/outputs/executor_2.jsonl",
            summary="Completed task with database"
        ))

        # Query for executor outputs containing "authentication"
        results = temp_db.query_agent_outputs(
            agent_type="executor",
            content_search="authentication"
        )
        assert len(results) == 1
        assert results[0].agent_type == "executor"
        assert "authentication" in results[0].summary.lower()

    def test_query_outputs_returns_empty_when_no_match(self, temp_db, sample_run):
        """Test that querying returns empty list when no outputs match."""
        temp_db.create_run(sample_run)

        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=sample_run.id,
            number=1,
            intent="First iteration",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0)
        ))

        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="planner",
            raw_output_path=".ralph/outputs/planner_1.jsonl",
            summary="Planned some tasks"
        ))

        # Query for non-existent agent type
        results = temp_db.query_agent_outputs(agent_type="nonexistent")
        assert len(results) == 0

        # Query for non-existent content
        results = temp_db.query_agent_outputs(content_search="xyz123notfound")
        assert len(results) == 0


class TestResumability:
    """Test that the state persistence supports resumability."""

    def test_resume_from_interrupted_run(self, temp_db):
        """Test that we can resume a run from where it left off."""
        # Create a run
        run = Run(
            id="resumable-run",
            spec_path="Ralphfile",
            spec_content="# Test Spec\nImplement feature X",
            status="running",
            config={"max_iterations": 10},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        temp_db.create_run(run)

        # Create some completed iterations
        iter1 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=run.id,
            number=1,
            intent="First task",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            ended_at=datetime(2024, 1, 15, 10, 45, 0)
        ))

        iter2 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=run.id,
            number=2,
            intent="Second task",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 45, 0),
            ended_at=datetime(2024, 1, 15, 11, 0, 0)
        ))

        # Add some agent outputs
        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter1.id,
            agent_type="executor",
            raw_output_path=".ralph2/outputs/executor_1.jsonl",
            summary="Completed task 1"
        ))

        temp_db.create_agent_output(AgentOutput(
            id=None,
            iteration_id=iter2.id,
            agent_type="executor",
            raw_output_path=".ralph2/outputs/executor_2.jsonl",
            summary="Completed task 2"
        ))

        # Now simulate resuming: we should be able to:
        # 1. Get the latest run
        latest_run = temp_db.get_latest_run()
        assert latest_run is not None
        assert latest_run.id == run.id
        assert latest_run.status == "running"

        # 2. Get the latest iteration to know where to continue from
        latest_iteration = temp_db.get_latest_iteration(run.id)
        assert latest_iteration is not None
        assert latest_iteration.number == 2
        assert latest_iteration.outcome == "continue"

        # 3. Get all iterations to see history
        all_iterations = temp_db.list_iterations(run.id)
        assert len(all_iterations) == 2

        # 4. Query agent outputs to see what was done
        all_outputs = temp_db.query_agent_outputs(run_id=run.id)
        assert len(all_outputs) == 2

        # 5. Continue with iteration 3
        iter3 = temp_db.create_iteration(Iteration(
            id=None,
            run_id=run.id,
            number=3,
            intent="Third task (resumed)",
            outcome="done",
            started_at=datetime(2024, 1, 15, 12, 0, 0),
            ended_at=datetime(2024, 1, 15, 12, 15, 0)
        ))

        # 6. Update run status to completed
        temp_db.update_run_status(run.id, "completed", datetime(2024, 1, 15, 12, 15, 0))

        # Verify the run is now complete
        completed_run = temp_db.get_run(run.id)
        assert completed_run.status == "completed"
        assert completed_run.ended_at is not None

        # Verify we have 3 iterations total
        final_iterations = temp_db.list_iterations(run.id)
        assert len(final_iterations) == 3
        assert final_iterations[2].intent == "Third task (resumed)"

    def test_paused_run_can_be_resumed(self, temp_db):
        """Test that a paused run can be identified and resumed."""
        run = Run(
            id="paused-run",
            spec_path="Ralphfile",
            spec_content="# Test Spec",
            status="paused",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        temp_db.create_run(run)

        # Create an iteration before pausing
        temp_db.create_iteration(Iteration(
            id=None,
            run_id=run.id,
            number=1,
            intent="Work before pause",
            outcome="continue",
            started_at=datetime(2024, 1, 15, 10, 30, 0),
            ended_at=datetime(2024, 1, 15, 10, 45, 0)
        ))

        # Get the latest run and check it's paused
        latest_run = temp_db.get_latest_run()
        assert latest_run.status == "paused"

        # Resume by updating status
        temp_db.update_run_status(run.id, "running")

        # Verify status changed
        resumed_run = temp_db.get_run(run.id)
        assert resumed_run.status == "running"

    def test_human_input_persists_for_next_iteration(self, temp_db):
        """Test that human input is stored and available for the next iteration."""
        run = Run(
            id="input-run",
            spec_path="Ralphfile",
            spec_content="# Test Spec",
            status="running",
            config={},
            started_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        temp_db.create_run(run)

        # User provides input
        human_input = HumanInput(
            id=None,
            run_id=run.id,
            input_type="comment",
            content="Please focus on authentication first",
            created_at=datetime(2024, 1, 15, 11, 0, 0)
        )
        temp_db.create_human_input(human_input)

        # Get unconsumed inputs (would be read by Planner in next iteration)
        unconsumed = temp_db.get_unconsumed_inputs(run.id)
        assert len(unconsumed) == 1
        assert unconsumed[0].content == "Please focus on authentication first"

        # After Planner reads it, mark as consumed
        temp_db.mark_input_consumed(unconsumed[0].id, datetime(2024, 1, 15, 11, 5, 0))

        # Verify it's no longer unconsumed
        still_unconsumed = temp_db.get_unconsumed_inputs(run.id)
        assert len(still_unconsumed) == 0
