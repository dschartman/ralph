"""Tests for _row_to_run helper method in Ralph2DB."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run


class TestRowToRunHelper:
    """Tests for the _row_to_run helper method that DRYs up row parsing."""

    def test_row_to_run_helper_exists(self):
        """Test that _row_to_run method exists on Ralph2DB class."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                assert hasattr(db, "_row_to_run"), "_row_to_run helper method should exist"
            finally:
                db.close()

    def test_row_to_run_returns_run_object(self):
        """Test that _row_to_run returns a valid Run object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                # Create a run to get a valid row
                run = Run(
                    id="test-run-123",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={"max_iterations": 10},
                    started_at=datetime.now(),
                    root_work_item_id="ralph-abc123"
                )
                db.create_run(run)

                # Fetch the row directly
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                # Use the helper to convert
                result = db._row_to_run(row)

                assert isinstance(result, Run)
                assert result.id == run.id
                assert result.spec_path == run.spec_path
                assert result.spec_content == run.spec_content
                assert result.status == run.status
                assert result.config == run.config
                assert result.root_work_item_id == run.root_work_item_id
            finally:
                db.close()

    def test_row_to_run_handles_null_ended_at(self):
        """Test that _row_to_run handles null ended_at correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                # Create a run without ended_at
                run = Run(
                    id="test-run-456",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now()
                )
                db.create_run(run)

                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.ended_at is None
            finally:
                db.close()

    def test_row_to_run_handles_ended_at_value(self):
        """Test that _row_to_run parses ended_at correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                ended = datetime.now()
                run = Run(
                    id="test-run-789",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="completed",
                    config={},
                    started_at=datetime.now(),
                    ended_at=ended
                )
                db.create_run(run)

                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.ended_at is not None
                # Compare ISO strings since microseconds might differ
                assert result.ended_at.isoformat() == ended.isoformat()
            finally:
                db.close()

    def test_row_to_run_handles_null_root_work_item_id(self):
        """Test that _row_to_run handles null root_work_item_id correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-aaa",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now()
                )
                db.create_run(run)

                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.root_work_item_id is None
            finally:
                db.close()

    def test_get_run_uses_helper(self):
        """Verify get_run still works correctly after refactoring to use helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-get",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={"key": "value"},
                    started_at=datetime.now(),
                    root_work_item_id="ralph-xyz789"
                )
                db.create_run(run)

                result = db.get_run(run.id)
                assert result is not None
                assert result.id == run.id
                assert result.config == run.config
                assert result.root_work_item_id == run.root_work_item_id
            finally:
                db.close()

    def test_get_latest_run_uses_helper(self):
        """Verify get_latest_run still works correctly after refactoring."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run1 = Run(
                    id="test-run-old",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="completed",
                    config={},
                    started_at=datetime(2024, 1, 1)
                )
                run2 = Run(
                    id="test-run-new",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime(2024, 6, 1),
                    root_work_item_id="ralph-latest"
                )
                db.create_run(run1)
                db.create_run(run2)

                result = db.get_latest_run()
                assert result is not None
                assert result.id == run2.id
                assert result.root_work_item_id == run2.root_work_item_id
            finally:
                db.close()

    def test_list_runs_uses_helper(self):
        """Verify list_runs still works correctly after refactoring."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run1 = Run(
                    id="test-run-list-1",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="completed",
                    config={"iter": 1},
                    started_at=datetime(2024, 1, 1)
                )
                run2 = Run(
                    id="test-run-list-2",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={"iter": 2},
                    started_at=datetime(2024, 6, 1),
                    root_work_item_id="ralph-list"
                )
                db.create_run(run1)
                db.create_run(run2)

                results = db.list_runs()
                assert len(results) == 2
                # Results are sorted by started_at DESC
                assert results[0].id == run2.id
                assert results[1].id == run1.id
                assert all(isinstance(r, Run) for r in results)
            finally:
                db.close()
