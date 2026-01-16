"""Unit tests for state/models.py - Data models for Ralph2 state management."""

import pytest
from datetime import datetime
import json

from ralph2.state.models import Run, Iteration, AgentOutput, HumanInput


class TestRunDataclass:
    """Tests for the Run dataclass."""

    def test_run_creation_with_required_fields(self):
        """Test creating a Run with required fields."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-test123",
            spec_path="/path/to/spec.md",
            spec_content="# Test Spec\n\nThis is a test.",
            status="running",
            config={"max_iterations": 10},
            started_at=started,
        )

        assert run.id == "ralph2-test123"
        assert run.spec_path == "/path/to/spec.md"
        assert run.spec_content == "# Test Spec\n\nThis is a test."
        assert run.status == "running"
        assert run.config == {"max_iterations": 10}
        assert run.started_at == started
        assert run.ended_at is None
        assert run.root_work_item_id is None

    def test_run_creation_with_optional_fields(self):
        """Test creating a Run with optional fields."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        ended = datetime(2024, 1, 15, 11, 0, 0)
        run = Run(
            id="ralph2-test456",
            spec_path="/path/to/spec.md",
            spec_content="# Spec",
            status="completed",
            config={"max_iterations": 20},
            started_at=started,
            ended_at=ended,
            root_work_item_id="ralph-root789",
        )

        assert run.ended_at == ended
        assert run.root_work_item_id == "ralph-root789"

    def test_run_to_dict(self):
        """Test Run.to_dict serialization."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        ended = datetime(2024, 1, 15, 11, 30, 0)
        run = Run(
            id="ralph2-dict-test",
            spec_path="/test/spec.md",
            spec_content="# Content",
            status="completed",
            config={"key": "value", "number": 42},
            started_at=started,
            ended_at=ended,
            root_work_item_id="ralph-item",
        )

        result = run.to_dict()

        assert result["id"] == "ralph2-dict-test"
        assert result["spec_path"] == "/test/spec.md"
        assert result["spec_content"] == "# Content"
        assert result["status"] == "completed"
        assert json.loads(result["config"]) == {"key": "value", "number": 42}
        assert result["started_at"] == "2024-01-15T10:00:00"
        assert result["ended_at"] == "2024-01-15T11:30:00"
        assert result["root_work_item_id"] == "ralph-item"

    def test_run_to_dict_with_none_ended_at(self):
        """Test Run.to_dict when ended_at is None."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-running",
            spec_path="/test/spec.md",
            spec_content="# Content",
            status="running",
            config={},
            started_at=started,
        )

        result = run.to_dict()

        assert result["ended_at"] is None

    def test_run_status_values(self):
        """Test Run with different status values."""
        started = datetime.now()
        statuses = ["running", "completed", "stuck", "paused", "aborted"]

        for status in statuses:
            run = Run(
                id=f"ralph2-{status}",
                spec_path="/spec.md",
                spec_content="# Spec",
                status=status,
                config={},
                started_at=started,
            )
            assert run.status == status


class TestIterationDataclass:
    """Tests for the Iteration dataclass."""

    def test_iteration_creation_with_required_fields(self):
        """Test creating an Iteration with required fields."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        iteration = Iteration(
            id=1,
            run_id="ralph2-test",
            number=1,
            intent="Implement feature X",
            outcome="continue",
            started_at=started,
        )

        assert iteration.id == 1
        assert iteration.run_id == "ralph2-test"
        assert iteration.number == 1
        assert iteration.intent == "Implement feature X"
        assert iteration.outcome == "continue"
        assert iteration.started_at == started
        assert iteration.ended_at is None

    def test_iteration_creation_with_optional_id_none(self):
        """Test creating an Iteration with id=None (before DB insert)."""
        started = datetime.now()
        iteration = Iteration(
            id=None,
            run_id="ralph2-test",
            number=3,
            intent="Test iteration",
            outcome="done",
            started_at=started,
        )

        assert iteration.id is None

    def test_iteration_to_dict(self):
        """Test Iteration.to_dict serialization."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        ended = datetime(2024, 1, 15, 10, 30, 0)
        iteration = Iteration(
            id=5,
            run_id="ralph2-dict",
            number=2,
            intent="Complete task Y",
            outcome="stuck",
            started_at=started,
            ended_at=ended,
        )

        result = iteration.to_dict()

        assert result["id"] == 5
        assert result["run_id"] == "ralph2-dict"
        assert result["number"] == 2
        assert result["intent"] == "Complete task Y"
        assert result["outcome"] == "stuck"
        assert result["started_at"] == "2024-01-15T10:00:00"
        assert result["ended_at"] == "2024-01-15T10:30:00"

    def test_iteration_to_dict_with_none_ended_at(self):
        """Test Iteration.to_dict when ended_at is None."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        iteration = Iteration(
            id=1,
            run_id="ralph2-test",
            number=1,
            intent="In progress",
            outcome="continue",
            started_at=started,
        )

        result = iteration.to_dict()

        assert result["ended_at"] is None

    def test_iteration_outcome_values(self):
        """Test Iteration with different outcome values."""
        started = datetime.now()
        outcomes = ["continue", "done", "stuck"]

        for outcome in outcomes:
            iteration = Iteration(
                id=None,
                run_id="ralph2-test",
                number=1,
                intent="Test",
                outcome=outcome,
                started_at=started,
            )
            assert iteration.outcome == outcome


class TestAgentOutputDataclass:
    """Tests for the AgentOutput dataclass."""

    def test_agent_output_creation(self):
        """Test creating an AgentOutput."""
        output = AgentOutput(
            id=1,
            iteration_id=10,
            agent_type="planner",
            raw_output_path="/outputs/planner_1.txt",
            summary="Created 3 tasks for implementation",
        )

        assert output.id == 1
        assert output.iteration_id == 10
        assert output.agent_type == "planner"
        assert output.raw_output_path == "/outputs/planner_1.txt"
        assert output.summary == "Created 3 tasks for implementation"

    def test_agent_output_with_none_id(self):
        """Test creating AgentOutput with id=None (before DB insert)."""
        output = AgentOutput(
            id=None,
            iteration_id=5,
            agent_type="executor",
            raw_output_path="/outputs/executor_5.txt",
            summary="Completed task",
        )

        assert output.id is None

    def test_agent_output_to_dict(self):
        """Test AgentOutput.to_dict serialization."""
        output = AgentOutput(
            id=42,
            iteration_id=100,
            agent_type="verifier",
            raw_output_path="/path/to/output.txt",
            summary="Verification passed",
        )

        result = output.to_dict()

        assert result["id"] == 42
        assert result["iteration_id"] == 100
        assert result["agent_type"] == "verifier"
        assert result["raw_output_path"] == "/path/to/output.txt"
        assert result["summary"] == "Verification passed"

    def test_agent_output_agent_type_values(self):
        """Test AgentOutput with different agent types."""
        agent_types = ["planner", "executor", "verifier"]

        for agent_type in agent_types:
            output = AgentOutput(
                id=None,
                iteration_id=1,
                agent_type=agent_type,
                raw_output_path="/output.txt",
                summary="Test",
            )
            assert output.agent_type == agent_type


class TestHumanInputDataclass:
    """Tests for the HumanInput dataclass."""

    def test_human_input_creation_with_required_fields(self):
        """Test creating a HumanInput with required fields."""
        created = datetime(2024, 1, 15, 10, 0, 0)
        human_input = HumanInput(
            id=1,
            run_id="ralph2-test",
            input_type="comment",
            content="Please focus on test coverage",
            created_at=created,
        )

        assert human_input.id == 1
        assert human_input.run_id == "ralph2-test"
        assert human_input.input_type == "comment"
        assert human_input.content == "Please focus on test coverage"
        assert human_input.created_at == created
        assert human_input.consumed_at is None

    def test_human_input_with_consumed_at(self):
        """Test creating a HumanInput that has been consumed."""
        created = datetime(2024, 1, 15, 10, 0, 0)
        consumed = datetime(2024, 1, 15, 10, 15, 0)
        human_input = HumanInput(
            id=2,
            run_id="ralph2-test",
            input_type="pause",
            content="Pause requested",
            created_at=created,
            consumed_at=consumed,
        )

        assert human_input.consumed_at == consumed

    def test_human_input_to_dict(self):
        """Test HumanInput.to_dict serialization."""
        created = datetime(2024, 1, 15, 10, 0, 0)
        consumed = datetime(2024, 1, 15, 10, 30, 0)
        human_input = HumanInput(
            id=10,
            run_id="ralph2-dict",
            input_type="resume",
            content="Resume after fixing issue",
            created_at=created,
            consumed_at=consumed,
        )

        result = human_input.to_dict()

        assert result["id"] == 10
        assert result["run_id"] == "ralph2-dict"
        assert result["input_type"] == "resume"
        assert result["content"] == "Resume after fixing issue"
        assert result["created_at"] == "2024-01-15T10:00:00"
        assert result["consumed_at"] == "2024-01-15T10:30:00"

    def test_human_input_to_dict_with_none_consumed_at(self):
        """Test HumanInput.to_dict when consumed_at is None."""
        created = datetime(2024, 1, 15, 10, 0, 0)
        human_input = HumanInput(
            id=1,
            run_id="ralph2-test",
            input_type="comment",
            content="Pending comment",
            created_at=created,
        )

        result = human_input.to_dict()

        assert result["consumed_at"] is None

    def test_human_input_type_values(self):
        """Test HumanInput with different input types."""
        created = datetime.now()
        input_types = ["comment", "pause", "resume", "abort"]

        for input_type in input_types:
            human_input = HumanInput(
                id=None,
                run_id="ralph2-test",
                input_type=input_type,
                content="Test",
                created_at=created,
            )
            assert human_input.input_type == input_type

    def test_human_input_with_none_id(self):
        """Test creating HumanInput with id=None (before DB insert)."""
        created = datetime.now()
        human_input = HumanInput(
            id=None,
            run_id="ralph2-test",
            input_type="comment",
            content="New comment",
            created_at=created,
        )

        assert human_input.id is None


class TestDataclassIntegration:
    """Integration tests for dataclass models."""

    def test_run_config_complex_dict(self):
        """Test Run with complex config dictionary."""
        started = datetime.now()
        complex_config = {
            "max_iterations": 50,
            "settings": {
                "verbose": True,
                "timeout": 300,
            },
            "enabled_features": ["planning", "verification"],
        }

        run = Run(
            id="ralph2-complex",
            spec_path="/spec.md",
            spec_content="# Spec",
            status="running",
            config=complex_config,
            started_at=started,
        )

        result = run.to_dict()
        parsed_config = json.loads(result["config"])

        assert parsed_config["max_iterations"] == 50
        assert parsed_config["settings"]["verbose"] is True
        assert "planning" in parsed_config["enabled_features"]

    def test_models_immutability_not_enforced(self):
        """Test that dataclass fields can be modified (not frozen)."""
        started = datetime.now()
        run = Run(
            id="ralph2-mutable",
            spec_path="/spec.md",
            spec_content="# Spec",
            status="running",
            config={},
            started_at=started,
        )

        # Should be able to modify status
        run.status = "completed"
        assert run.status == "completed"

        # Should be able to set ended_at
        ended = datetime.now()
        run.ended_at = ended
        assert run.ended_at == ended


class TestRalph2DBClose:
    """Tests for Ralph2DB.close() safety - spec requirement: 'WHEN database close() is called on already-closed connection, THEN no exception is raised'."""

    def test_close_multiple_times_no_exception(self, tmp_path):
        """Test that calling close() multiple times raises no exception."""
        from ralph2.state.db import Ralph2DB

        db_path = str(tmp_path / "test_close.db")
        db = Ralph2DB(db_path)

        # First close - should succeed
        db.close()

        # Second close - should NOT raise exception (spec requirement)
        db.close()

        # Third close - also should not raise
        db.close()

    def test_close_sets_closed_flag(self, tmp_path):
        """Test that close() sets the _closed flag."""
        from ralph2.state.db import Ralph2DB

        db_path = str(tmp_path / "test_flag.db")
        db = Ralph2DB(db_path)

        assert db._closed is False
        db.close()
        assert db._closed is True

    def test_close_handles_already_closed_sqlite_connection(self, tmp_path):
        """Test that close() handles sqlite connection already being closed."""
        from ralph2.state.db import Ralph2DB

        db_path = str(tmp_path / "test_sqlite_closed.db")
        db = Ralph2DB(db_path)

        # Close the underlying sqlite connection directly (simulating error state)
        db.conn.close()

        # Ralph2DB.close() should handle this gracefully
        db.close()  # Should not raise even though conn is already closed

        # And second call should also not raise
        db.close()

    def test_closed_flag_initialized_on_creation(self, tmp_path):
        """Test that _closed flag is False after database creation."""
        from ralph2.state.db import Ralph2DB

        db_path = str(tmp_path / "test_init.db")
        db = Ralph2DB(db_path)

        assert hasattr(db, '_closed')
        assert db._closed is False

        db.close()


class TestRalph2DBUpdateIterationIntent:
    """Tests for Ralph2DB.update_iteration_intent() - spec requirement: 'Database operations use transaction boundaries for multi-step operations' and 'Direct SQL execution bypasses database abstraction'."""

    def test_update_iteration_intent_exists(self, tmp_path):
        """Test that update_iteration_intent method exists on Ralph2DB."""
        from ralph2.state.db import Ralph2DB

        db_path = str(tmp_path / "test_intent.db")
        db = Ralph2DB(db_path)

        assert hasattr(db, 'update_iteration_intent')
        assert callable(getattr(db, 'update_iteration_intent'))

        db.close()

    def test_update_iteration_intent_updates_intent(self, tmp_path):
        """Test that update_iteration_intent correctly updates the intent field."""
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import Run, Iteration
        from datetime import datetime

        db_path = str(tmp_path / "test_intent_update.db")
        db = Ralph2DB(db_path)

        # Create a run first
        run = Run(
            id="test-run-123",
            spec_path="/path/to/spec.md",
            spec_content="# Test Spec",
            status="running",
            config={},
            started_at=datetime.now()
        )
        db.create_run(run)

        # Create an iteration with empty intent
        iteration = Iteration(
            id=None,
            run_id="test-run-123",
            number=1,
            intent="",  # Empty initially
            outcome="continue",
            started_at=datetime.now()
        )
        iteration = db.create_iteration(iteration)

        # Update the intent
        db.update_iteration_intent(iteration.id, "New iteration intent")

        # Verify the intent was updated
        updated_iteration = db.get_iteration(iteration.id)
        assert updated_iteration.intent == "New iteration intent"

        db.close()

    def test_update_iteration_intent_respects_transactions(self, tmp_path):
        """Test that update_iteration_intent respects transaction boundaries."""
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import Run, Iteration
        from datetime import datetime

        db_path = str(tmp_path / "test_intent_txn.db")
        db = Ralph2DB(db_path)

        # Create run and iteration
        run = Run(
            id="test-run-txn",
            spec_path="/path/to/spec.md",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now()
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="test-run-txn",
            number=1,
            intent="original",
            outcome="continue",
            started_at=datetime.now()
        )
        iteration = db.create_iteration(iteration)

        # Update within a transaction
        with db.transaction():
            db.update_iteration_intent(iteration.id, "updated in txn")

        # Verify update persisted
        updated = db.get_iteration(iteration.id)
        assert updated.intent == "updated in txn"

        db.close()

    def test_update_iteration_intent_auto_commits_outside_transaction(self, tmp_path):
        """Test that update_iteration_intent auto-commits when outside a transaction."""
        from ralph2.state.db import Ralph2DB
        from ralph2.state.models import Run, Iteration
        from datetime import datetime

        db_path = str(tmp_path / "test_intent_auto.db")
        db = Ralph2DB(db_path)

        # Create run and iteration
        run = Run(
            id="test-run-auto",
            spec_path="/path/to/spec.md",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now()
        )
        db.create_run(run)

        iteration = Iteration(
            id=None,
            run_id="test-run-auto",
            number=1,
            intent="original",
            outcome="continue",
            started_at=datetime.now()
        )
        iteration = db.create_iteration(iteration)

        # Update outside any transaction - should auto-commit
        db.update_iteration_intent(iteration.id, "auto-committed")

        # Open a new connection to verify the data was committed
        db2 = Ralph2DB(db_path)
        updated = db2.get_iteration(iteration.id)
        assert updated.intent == "auto-committed"

        db.close()
        db2.close()
