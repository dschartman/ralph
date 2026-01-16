"""Tests for milestone_branch field in Run model - Milestone Branch Isolation feature.

These tests verify:
1. Run model has milestone_branch: Optional[str] field
2. to_dict() includes milestone_branch
3. db.py stores and retrieves milestone_branch
4. Backward compatibility (runs without milestone_branch default to None)
"""

import pytest
import tempfile
import json
from datetime import datetime
from pathlib import Path

from ralph2.state.models import Run
from ralph2.state.db import Ralph2DB


class TestRunMilestoneBranchField:
    """Tests for the milestone_branch field on the Run dataclass."""

    def test_run_has_milestone_branch_field(self):
        """Test that Run dataclass has milestone_branch field."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-test",
            spec_path="/path/to/spec.md",
            spec_content="# Test Spec",
            status="running",
            config={},
            started_at=started,
        )

        # Field should exist and default to None
        assert hasattr(run, 'milestone_branch')
        assert run.milestone_branch is None

    def test_run_creation_with_milestone_branch(self):
        """Test creating a Run with milestone_branch set."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-with-branch",
            spec_path="/path/to/spec.md",
            spec_content="# Test Spec",
            status="running",
            config={},
            started_at=started,
            milestone_branch="feature/my-milestone",
        )

        assert run.milestone_branch == "feature/my-milestone"

    def test_run_to_dict_includes_milestone_branch_when_set(self):
        """Test that to_dict() includes milestone_branch when it has a value."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-dict-test",
            spec_path="/test/spec.md",
            spec_content="# Content",
            status="running",
            config={},
            started_at=started,
            milestone_branch="feature/test-branch",
        )

        result = run.to_dict()

        assert "milestone_branch" in result
        assert result["milestone_branch"] == "feature/test-branch"

    def test_run_to_dict_includes_milestone_branch_when_none(self):
        """Test that to_dict() includes milestone_branch even when None."""
        started = datetime(2024, 1, 15, 10, 0, 0)
        run = Run(
            id="ralph2-dict-none",
            spec_path="/test/spec.md",
            spec_content="# Content",
            status="running",
            config={},
            started_at=started,
        )

        result = run.to_dict()

        assert "milestone_branch" in result
        assert result["milestone_branch"] is None


class TestDBMilestoneBranchColumn:
    """Tests for milestone_branch column in the database."""

    def test_create_run_with_milestone_branch(self):
        """Test creating a run with milestone_branch stores it in DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-mb",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/my-feature",
                )
                db.create_run(run)

                # Retrieve and verify
                retrieved = db.get_run(run.id)
                assert retrieved is not None
                assert retrieved.milestone_branch == "feature/my-feature"
            finally:
                db.close()

    def test_create_run_without_milestone_branch(self):
        """Test creating a run without milestone_branch (backward compatible)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-no-mb",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Retrieve and verify milestone_branch is None
                retrieved = db.get_run(run.id)
                assert retrieved is not None
                assert retrieved.milestone_branch is None
            finally:
                db.close()

    def test_get_latest_run_includes_milestone_branch(self):
        """Test that get_latest_run returns milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-latest",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/latest-branch",
                )
                db.create_run(run)

                latest = db.get_latest_run()
                assert latest is not None
                assert latest.milestone_branch == "feature/latest-branch"
            finally:
                db.close()

    def test_list_runs_includes_milestone_branch(self):
        """Test that list_runs returns runs with milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run1 = Run(
                    id="test-run-list-1",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime(2024, 1, 1),
                    milestone_branch="feature/branch-1",
                )
                run2 = Run(
                    id="test-run-list-2",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime(2024, 6, 1),
                    milestone_branch="feature/branch-2",
                )
                db.create_run(run1)
                db.create_run(run2)

                runs = db.list_runs()
                assert len(runs) == 2
                # Results sorted by started_at DESC
                assert runs[0].milestone_branch == "feature/branch-2"
                assert runs[1].milestone_branch == "feature/branch-1"
            finally:
                db.close()

    def test_migration_adds_milestone_branch_column(self):
        """Test that DB migration adds milestone_branch column to existing schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # Create DB - schema migration should add milestone_branch column
            db = Ralph2DB(db_path)
            try:
                # Check column exists in schema
                cursor = db.conn.cursor()
                cursor.execute("PRAGMA table_info(runs)")
                columns = [row[1] for row in cursor.fetchall()]

                assert "milestone_branch" in columns, "milestone_branch column should exist"
            finally:
                db.close()

    def test_update_run_milestone_branch(self):
        """Test updating a run's milestone_branch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-run-update-mb",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                )
                db.create_run(run)

                # Update milestone_branch
                db.update_run_milestone_branch(run.id, "feature/updated-branch")

                # Verify update
                retrieved = db.get_run(run.id)
                assert retrieved is not None
                assert retrieved.milestone_branch == "feature/updated-branch"
            finally:
                db.close()


class TestRowToRunWithMilestoneBranch:
    """Tests for _row_to_run helper handling milestone_branch."""

    def test_row_to_run_includes_milestone_branch(self):
        """Test that _row_to_run parses milestone_branch correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-row-mb",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
                    status="running",
                    config={},
                    started_at=datetime.now(),
                    milestone_branch="feature/row-test",
                )
                db.create_run(run)

                # Fetch row directly and use helper
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM runs WHERE id = ?", (run.id,))
                row = cursor.fetchone()

                result = db._row_to_run(row)
                assert result.milestone_branch == "feature/row-test"
            finally:
                db.close()

    def test_row_to_run_handles_null_milestone_branch(self):
        """Test that _row_to_run handles NULL milestone_branch correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            db = Ralph2DB(db_path)
            try:
                run = Run(
                    id="test-row-null-mb",
                    spec_path="/path/to/spec",
                    spec_content="# Test Spec",
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
