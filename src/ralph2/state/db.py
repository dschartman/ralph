"""SQLite database operations for Ralph2 state management."""

import sqlite3
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import json
from contextlib import contextmanager

from .models import Run, Iteration, AgentOutput, HumanInput


class Ralph2DB:
    """Manages SQLite database for Ralph2 state."""

    def __init__(self, db_path: str):
        """
        Initialize database connection and ensure schema exists.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._transaction_depth = 0
        self._closed = False
        self._init_schema()

    def _init_schema(self):
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()

        # Runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
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

        # Iterations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS iterations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                intent TEXT NOT NULL,
                outcome TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)

        # Agent outputs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_id INTEGER NOT NULL,
                agent_type TEXT NOT NULL,
                raw_output_path TEXT NOT NULL,
                summary TEXT NOT NULL,
                FOREIGN KEY (iteration_id) REFERENCES iterations(id)
            )
        """)

        # Human inputs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS human_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                input_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)

        # Migration: Add root_work_item_id column to runs table if it doesn't exist
        cursor.execute("PRAGMA table_info(runs)")
        columns = [row[1] for row in cursor.fetchall()]
        if "root_work_item_id" not in columns:
            cursor.execute("ALTER TABLE runs ADD COLUMN root_work_item_id TEXT")

        self.conn.commit()

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Usage:
            with db.transaction():
                db.create_run(run)
                db.create_iteration(iteration)

        If an exception occurs, the transaction is rolled back.
        Otherwise, it is committed when the context exits.

        Supports nested transactions using savepoints.
        """
        self._transaction_depth += 1
        savepoint_name = f"sp_{self._transaction_depth}"

        if self._transaction_depth == 1:
            # First level: start a real transaction
            self.conn.execute("BEGIN")
        else:
            # Nested level: use savepoint
            self.conn.execute(f"SAVEPOINT {savepoint_name}")

        try:
            yield
            # Commit on successful exit
            if self._transaction_depth == 1:
                self.conn.commit()
            else:
                self.conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except Exception:
            # Rollback on error
            if self._transaction_depth == 1:
                self.conn.rollback()
            else:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            raise
        finally:
            self._transaction_depth -= 1

    def begin_transaction(self):
        """
        Manually begin a transaction.

        Must be paired with commit_transaction() or rollback_transaction().
        Prefer using the transaction() context manager when possible.
        """
        if not self._in_transaction:
            self.conn.execute("BEGIN")
            self._in_transaction = True

    def commit_transaction(self):
        """
        Manually commit the current transaction.

        Only commits if a transaction was started with begin_transaction().
        """
        if self._in_transaction:
            self.conn.commit()
            self._in_transaction = False

    def rollback_transaction(self):
        """
        Manually rollback the current transaction.

        Only rolls back if a transaction was started with begin_transaction().
        """
        if self._in_transaction:
            self.conn.rollback()
            self._in_transaction = False

    def _should_auto_commit(self) -> bool:
        """
        Determine if operations should auto-commit.

        Returns False if we're inside a transaction context or manual transaction.
        """
        return self._transaction_depth == 0 and not self._in_transaction

    def create_run(self, run: Run) -> Run:
        """Create a new run."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO runs (id, spec_path, spec_content, status, config, started_at, ended_at, root_work_item_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run.id,
            run.spec_path,
            run.spec_content,
            run.status,
            json.dumps(run.config),
            run.started_at.isoformat(),
            run.ended_at.isoformat() if run.ended_at else None,
            run.root_work_item_id
        ))
        if self._should_auto_commit():
            self.conn.commit()
        return run

    def get_run(self, run_id: str) -> Optional[Run]:
        """Get a run by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            return Run(
                id=row["id"],
                spec_path=row["spec_path"],
                spec_content=row["spec_content"],
                status=row["status"],
                config=json.loads(row["config"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                root_work_item_id=row["root_work_item_id"] if "root_work_item_id" in row.keys() else None
            )
        return None

    def update_run_status(self, run_id: str, status: str, ended_at: Optional[datetime] = None):
        """Update run status."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE runs
            SET status = ?, ended_at = ?
            WHERE id = ?
        """, (status, ended_at.isoformat() if ended_at else None, run_id))
        if self._should_auto_commit():
            self.conn.commit()

    def update_run_root_work_item(self, run_id: str, root_work_item_id: str):
        """Update run's root work item ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE runs
            SET root_work_item_id = ?
            WHERE id = ?
        """, (root_work_item_id, run_id))
        if self._should_auto_commit():
            self.conn.commit()

    def get_latest_run(self) -> Optional[Run]:
        """Get the most recent run."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return Run(
                id=row["id"],
                spec_path=row["spec_path"],
                spec_content=row["spec_content"],
                status=row["status"],
                config=json.loads(row["config"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                root_work_item_id=row["root_work_item_id"] if "root_work_item_id" in row.keys() else None
            )
        return None

    def list_runs(self) -> List[Run]:
        """List all runs."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM runs ORDER BY started_at DESC")
        rows = cursor.fetchall()
        return [
            Run(
                id=row["id"],
                spec_path=row["spec_path"],
                spec_content=row["spec_content"],
                status=row["status"],
                config=json.loads(row["config"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                root_work_item_id=row["root_work_item_id"] if "root_work_item_id" in row.keys() else None
            )
            for row in rows
        ]

    def create_iteration(self, iteration: Iteration) -> Iteration:
        """Create a new iteration."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO iterations (run_id, number, intent, outcome, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            iteration.run_id,
            iteration.number,
            iteration.intent,
            iteration.outcome,
            iteration.started_at.isoformat(),
            iteration.ended_at.isoformat() if iteration.ended_at else None
        ))
        if self._should_auto_commit():
            self.conn.commit()
        iteration.id = cursor.lastrowid
        return iteration

    def get_iteration(self, iteration_id: int) -> Optional[Iteration]:
        """Get an iteration by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM iterations WHERE id = ?", (iteration_id,))
        row = cursor.fetchone()
        if row:
            return Iteration(
                id=row["id"],
                run_id=row["run_id"],
                number=row["number"],
                intent=row["intent"],
                outcome=row["outcome"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None
            )
        return None

    def update_iteration(self, iteration_id: int, outcome: str, ended_at: datetime):
        """Update iteration outcome and end time."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE iterations
            SET outcome = ?, ended_at = ?
            WHERE id = ?
        """, (outcome, ended_at.isoformat(), iteration_id))
        if self._should_auto_commit():
            self.conn.commit()

    def list_iterations(self, run_id: str) -> List[Iteration]:
        """List all iterations for a run."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM iterations WHERE run_id = ? ORDER BY number", (run_id,))
        rows = cursor.fetchall()
        return [
            Iteration(
                id=row["id"],
                run_id=row["run_id"],
                number=row["number"],
                intent=row["intent"],
                outcome=row["outcome"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None
            )
            for row in rows
        ]

    def get_latest_iteration(self, run_id: str) -> Optional[Iteration]:
        """
        Get the most recent iteration for a run.

        This is useful for resumability - determining the last completed iteration
        before resuming a run.

        Args:
            run_id: The run ID to get the latest iteration for

        Returns:
            The most recent Iteration, or None if no iterations exist
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM iterations
            WHERE run_id = ?
            ORDER BY number DESC
            LIMIT 1
        """, (run_id,))
        row = cursor.fetchone()
        if row:
            return Iteration(
                id=row["id"],
                run_id=row["run_id"],
                number=row["number"],
                intent=row["intent"],
                outcome=row["outcome"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None
            )
        return None

    def create_agent_output(self, output: AgentOutput) -> AgentOutput:
        """Create a new agent output."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO agent_outputs (iteration_id, agent_type, raw_output_path, summary)
            VALUES (?, ?, ?, ?)
        """, (
            output.iteration_id,
            output.agent_type,
            output.raw_output_path,
            output.summary
        ))
        if self._should_auto_commit():
            self.conn.commit()
        output.id = cursor.lastrowid
        return output

    def get_agent_outputs(self, iteration_id: int) -> List[AgentOutput]:
        """Get all agent outputs for an iteration."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agent_outputs WHERE iteration_id = ?", (iteration_id,))
        rows = cursor.fetchall()
        return [
            AgentOutput(
                id=row["id"],
                iteration_id=row["iteration_id"],
                agent_type=row["agent_type"],
                raw_output_path=row["raw_output_path"],
                summary=row["summary"]
            )
            for row in rows
        ]

    def query_agent_outputs(
        self,
        run_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        content_search: Optional[str] = None
    ) -> List[AgentOutput]:
        """
        Query agent outputs with optional filters.

        This enables efficient searching of agent outputs by iteration, agent type,
        or content without reading entire files. Agents can use this to find relevant
        previous work.

        Args:
            run_id: Filter by run ID (via iterations)
            agent_type: Filter by agent type (e.g., "planner", "executor", "verifier")
            content_search: Filter by content in summary (case-insensitive substring match)

        Returns:
            List of AgentOutput objects matching the filters
        """
        cursor = self.conn.cursor()

        # Build the query dynamically based on provided filters
        query = """
            SELECT ao.* FROM agent_outputs ao
            JOIN iterations i ON ao.iteration_id = i.id
            WHERE 1=1
        """
        params = []

        if run_id is not None:
            query += " AND i.run_id = ?"
            params.append(run_id)

        if agent_type is not None:
            query += " AND ao.agent_type = ?"
            params.append(agent_type)

        if content_search is not None:
            query += " AND ao.summary LIKE ?"
            params.append(f"%{content_search}%")

        query += " ORDER BY i.number, ao.id"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        return [
            AgentOutput(
                id=row["id"],
                iteration_id=row["iteration_id"],
                agent_type=row["agent_type"],
                raw_output_path=row["raw_output_path"],
                summary=row["summary"]
            )
            for row in rows
        ]

    def create_human_input(self, human_input: HumanInput) -> HumanInput:
        """Create a new human input."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO human_inputs (run_id, input_type, content, created_at, consumed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            human_input.run_id,
            human_input.input_type,
            human_input.content,
            human_input.created_at.isoformat(),
            human_input.consumed_at.isoformat() if human_input.consumed_at else None
        ))
        if self._should_auto_commit():
            self.conn.commit()
        human_input.id = cursor.lastrowid
        return human_input

    def get_unconsumed_inputs(self, run_id: str) -> List[HumanInput]:
        """Get all unconsumed human inputs for a run."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM human_inputs
            WHERE run_id = ? AND consumed_at IS NULL
            ORDER BY created_at
        """, (run_id,))
        rows = cursor.fetchall()
        return [
            HumanInput(
                id=row["id"],
                run_id=row["run_id"],
                input_type=row["input_type"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                consumed_at=datetime.fromisoformat(row["consumed_at"]) if row["consumed_at"] else None
            )
            for row in rows
        ]

    def mark_input_consumed(self, input_id: int, consumed_at: datetime):
        """Mark a human input as consumed."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE human_inputs
            SET consumed_at = ?
            WHERE id = ?
        """, (consumed_at.isoformat(), input_id))
        if self._should_auto_commit():
            self.conn.commit()

    def close(self):
        """
        Close database connection safely.

        Safe to call multiple times - subsequent calls are no-ops.
        Handles connection errors gracefully by catching exceptions
        and ensuring _closed flag is always set.
        """
        if self._closed:
            return

        try:
            self.conn.close()
        except Exception:
            # Connection may already be closed or in error state.
            # We suppress exceptions here since the goal is cleanup -
            # there's nothing useful we can do with a close failure.
            pass
        finally:
            self._closed = True
