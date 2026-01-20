"""Tests for milestone_branch field in Run model and db.py CRUD operations.

This tests the foundational model/DB changes for milestone branch isolation.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ralph2.state.db import Ralph2DB
from ralph2.state.models import Run


class TestRunModelMilestoneBranch:
    """Tests for milestone_branch field on Run dataclass."""

    def test_run_has_milestone_branch_field(self):
        """Test that Run dataclass has milestone_branch field."""
        run = Run(
            id="ralph2-test",
            spec_path="/path/to/spec",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now(),
        )
        # Field should exist and default to None
        assert hasattr(run, "milestone_branch")
        assert run.milestone_branch is None

    def test_run_creation_with_milestone_branch(self):
        """Test creating a Run with milestone_branch specified."""
        run = Run(
            id="ralph2-test",
            spec_path="/path/to/spec",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now(),
            milestone_branch="feature/my-feature",
        )
        assert run.milestone_branch == "feature/my-feature"

    def test_run_to_dict_includes_milestone_branch(self):
        """Test that Run.to_dict includes milestone_branch."""
        run = Run(
            id="ralph2-test",
            spec_path="/path/to/spec",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now(),
            milestone_branch="feature/test-branch",
        )
        result = run.to_dict()
        assert "milestone_branch" in result
        assert result["milestone_branch"] == "feature/test-branch"

    def test_run_to_dict_milestone_branch_none(self):
        """Test that Run.to_dict handles None milestone_branch."""
        run = Run(
            id="ralph2-test",
            spec_path="/path/to/spec",
            spec_content="# Test",
            status="running",
            config={},
            started_at=datetime.now(),
        )
        result = run.to_dict()
        assert "milestone_branch" in result
        assert result["milestone_branch"] is None


class TestRalph2DBMilestoneBranchColumn:
    """Tests for milestone_branch column in runs table."""

    def test_runs_table_has_milestone_branch_column(self):
        """Test that runs table has milestone_branch column after schema init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                cursor = db.conn.cursor()
                cursor.execute("PRAGMA table_info(runs)")
                columns = [row[1] for row in cursor.fetchall()]
                assert "milestone_branch" in columns
            finally:
                db.close()

    def test_milestone_branch_column_migration(self):
        """Test that existing databases get milestone_branch column via migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # Create a database without milestone_branch column (simulate old schema)
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE runs (
                    id TEXT PRIMARY KEY,
                    spec_path TEXT NOT NULL,
                    spec_content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    root_work_item_id TEXT
                )
            """)
            conn.commit()
            conn.close()

            # Now open with Ralph2DB - should migrate
            db = Ralph2DB(db_path)
            try:
                cursor = db.conn.cursor()
                cursor.execute("PRAGMA table_info(runs)")
                columns = [row[1] for row in cursor.fetchall()]
                assert "milestone_branch" in columns
            finally:
                db.close()


class TestRalph2DBCreateRunWithMilestoneBranch:
    """Tests for create_run() with milestone_branch."""

    def test_create_run_with_milestone_branch(self):
        """Test creating a run with milestone_branch stores it correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-create",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/test-create",
                )
                db.create_run(run)

                # Verify directly in DB
                cursor = db.conn.cursor()
                cursor.execute("SELECT milestone_branch FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()
                assert row[0] == "feature/test-create"
            finally:
                db.close()

    def test_create_run_without_milestone_branch(self):
        """Test creating a run without milestone_branch stores NULL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-no-branch",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Verify directly in DB
                cursor = db.conn.cursor()
                cursor.execute("SELECT milestone_branch FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()
                assert row[0] is None
            finally:
                db.close()


class TestRalph2DBGetRunWithMilestoneBranch:
    """Tests for get_run() returning milestone_branch."""

    def test_get_run_returns_milestone_branch(self):
        """Test that get_run returns Run with milestone_branch populated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-get",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/get-test",
                )
                db.create_run(run)

                result = db.get_run(run.id)
                assert result is not None
                assert result.milestone_branch == "feature/get-test"
            finally:
                db.close()

    def test_get_run_returns_none_milestone_branch(self):
        """Test that get_run handles NULL milestone_branch correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-get-null",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                result = db.get_run(run.id)
                assert result is not None
                assert result.milestone_branch is None
            finally:
                db.close()

    def test_get_latest_run_returns_milestone_branch(self):
        """Test that get_latest_run returns Run with milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-latest",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/latest-test",
                )
                db.create_run(run)

                result = db.get_latest_run()
                assert result is not None
                assert result.milestone_branch == "feature/latest-test"
            finally:
                db.close()

    def test_list_runs_returns_milestone_branch(self):
        """Test that list_runs returns Runs with milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-list",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/list-test",
                )
                db.create_run(run)

                results = db.list_runs()
                assert len(results) == 1
                assert results[0].milestone_branch == "feature/list-test"
            finally:
                db.close()


class TestRalph2DBUpdateMilestoneBranch:
    """Tests for update_run_milestone_branch() method."""

    def test_update_run_milestone_branch_method_exists(self):
        """Test that update_run_milestone_branch method exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                assert hasattr(db, "update_run_milestone_branch")
                assert callable(getattr(db, "update_run_milestone_branch"))
            finally:
                db.close()

    def test_update_run_milestone_branch_updates_value(self):
        """Test that update_run_milestone_branch updates the value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                # Create a run without milestone_branch
                run = Run(
                    id="ralph2-test-update",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Update the milestone_branch
                db.update_run_milestone_branch(run.id, "feature/updated-branch")

                # Verify the update
                result = db.get_run(run.id)
                assert result.milestone_branch == "feature/updated-branch"
            finally:
                db.close()

    def test_update_run_milestone_branch_respects_transactions(self):
        """Test that update_run_milestone_branch respects transaction boundaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-txn",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Update within a transaction
                with db.transaction():
                    db.update_run_milestone_branch(run.id, "feature/txn-branch")

                # Verify update persisted
                result = db.get_run(run.id)
                assert result.milestone_branch == "feature/txn-branch"
            finally:
                db.close()

    def test_update_run_milestone_branch_auto_commits(self):
        """Test that update_run_milestone_branch auto-commits outside transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-test-auto",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Update outside transaction
                db.update_run_milestone_branch(run.id, "feature/auto-commit")

                # Open a new connection to verify commit
                db2 = Ralph2DB(db_path)
                result = db2.get_run(run.id)
                assert result.milestone_branch == "feature/auto-commit"
                db2.close()
            finally:
                db.close()


class TestRowToRunWithMilestoneBranch:
    """Tests for _row_to_run helper handling milestone_branch."""

    def test_row_to_run_includes_milestone_branch(self):
        """Test that _row_to_run correctly parses milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-row-test",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/row-test",
                )
                db.create_run(run)

                # Fetch the row directly and use helper
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.milestone_branch == "feature/row-test"
            finally:
                db.close()

    def test_row_to_run_handles_null_milestone_branch(self):
        """Test that _row_to_run handles NULL milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="ralph2-row-null",
                    spec_path="/path/to/spec",
                    spec_content="# Test",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.milestone_branch is None
            finally:
                db.close()


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing runs."""

    def test_existing_runs_without_milestone_branch_work(self):
        """Test that runs created before milestone_branch feature still work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # Create a database and insert a run directly (simulating old data)
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE runs (
                    id TEXT PRIMARY KEY,
                    spec_path TEXT NOT NULL,
                    spec_content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    root_work_item_id TEXT
                )
            """)
            conn.execute("""
                INSERT INTO runs (id, spec_path, spec_content, status, config, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("old-run-123", "/old/spec", "# Old Spec", "completed", "{}", "2024-01-01T00:00:00"))
            conn.commit()
            conn.close()

            # Now open with Ralph2DB (migration should add column)
            db = Ralph2DB(db_path)
            try:
                # Should be able to read the old run
                result = db.get_run("old-run-123")
                assert result is not None
                assert result.id == "old-run-123"
                # milestone_branch should be None for old runs
                assert result.milestone_branch is None
            finally:
                db.close()
