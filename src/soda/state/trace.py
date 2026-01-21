"""Trace CLI integration for Soda state layer.

This module provides a Python interface to the Trace CLI (`trc`) for
work item tracking. It allows reading work state, creating/closing tasks,
and posting comments.
"""

import re
import subprocess
from dataclasses import dataclass
from typing import Optional


class TraceError(Exception):
    """Error raised when Trace CLI operations fail."""

    pass


@dataclass
class Task:
    """A task from Trace.

    Attributes:
        id: The unique task identifier (e.g., "ralph-abc123").
        title: The task title.
        status: The task status (e.g., "open", "closed").
        priority: The task priority (0-4).
        description: Optional detailed description.
        parent_id: Optional parent task ID.
    """

    id: str
    title: str
    status: str
    priority: int
    description: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class Comment:
    """A comment on a Trace task.

    Attributes:
        timestamp: When the comment was posted.
        source: Who posted the comment (e.g., "executor", "planner").
        text: The comment text.
    """

    timestamp: str
    source: str
    text: str


class TraceClient:
    """Client for interacting with Trace CLI.

    This client provides methods to read work state, create/close tasks,
    and post comments using the Trace CLI (`trc`).

    Example:
        client = TraceClient()
        tasks = client.get_open_tasks()
        client.post_comment("ralph-123", "Starting work")
        client.close_task("ralph-123")
    """

    def get_open_tasks(self, root_id: Optional[str] = None) -> list[Task]:
        """Get open tasks that are ready to work on.

        Uses `trc ready` to find unblocked tasks. If root_id is provided,
        only returns tasks that are children of that root.

        Args:
            root_id: Optional root task ID to filter by.

        Returns:
            List of open, unblocked tasks.
        """
        output = self._run_command(["trc", "ready"])
        tasks = self._parse_task_list(output)

        if root_id:
            tasks = [t for t in tasks if t.parent_id == root_id]

        return tasks

    def get_blocked_tasks(self, root_id: Optional[str] = None) -> list[Task]:
        """Get tasks that are blocked by dependencies.

        Uses `trc list` and identifies tasks with "blocked by" markers.

        Args:
            root_id: Optional root task ID to filter by.

        Returns:
            List of blocked tasks.
        """
        output = self._run_command(["trc", "list"])
        tasks = self._parse_blocked_tasks(output)

        if root_id:
            tasks = [t for t in tasks if t.parent_id == root_id]

        return tasks

    def get_closed_tasks(self, root_id: Optional[str] = None) -> list[Task]:
        """Get closed tasks.

        Uses `trc list --status closed` to find closed tasks.

        Args:
            root_id: Optional root task ID to filter by.

        Returns:
            List of closed tasks.
        """
        output = self._run_command(["trc", "list", "--status", "closed"])
        tasks = self._parse_closed_task_list(output)

        if root_id:
            tasks = [t for t in tasks if t.parent_id == root_id]

        return tasks

    def get_task_comments(self, task_id: str) -> list[Comment]:
        """Get comments on a task.

        Uses `trc show` to get task details including comments.

        Args:
            task_id: The task ID to get comments for.

        Returns:
            List of comments on the task.
        """
        output = self._run_command(["trc", "show", task_id])
        return self._parse_comments(output)

    def create_task(
        self,
        title: str,
        description: str,
        parent: Optional[str] = None,
    ) -> str:
        """Create a new task in Trace.

        Args:
            title: The task title.
            description: The task description (required by trc).
            parent: Optional parent task ID.

        Returns:
            The ID of the created task.
        """
        cmd = ["trc", "create", title, "--description", description]
        if parent:
            cmd.extend(["--parent", parent])

        output = self._run_command(cmd)
        return self._parse_created_task_id(output)

    def close_task(self, task_id: str, message: Optional[str] = None) -> None:
        """Close a task in Trace.

        Args:
            task_id: The task ID to close.
            message: Optional closing message.
        """
        cmd = ["trc", "close", task_id]
        if message:
            cmd.extend(["--message", message])

        self._run_command(cmd)

    def post_comment(
        self,
        task_id: str,
        content: str,
        source: Optional[str] = None,
    ) -> None:
        """Post a comment on a task.

        Args:
            task_id: The task ID to comment on.
            content: The comment text.
            source: Optional source identifier (e.g., "executor").
        """
        cmd = ["trc", "comment", task_id, content]
        if source:
            cmd.extend(["--source", source])

        self._run_command(cmd)

    def _run_command(self, cmd: list[str]) -> str:
        """Run a trc command and return output.

        Args:
            cmd: The command to run as a list of strings.

        Returns:
            The command stdout.

        Raises:
            TraceError: If the command fails.
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise TraceError(
                    f"Trace command failed: {result.stderr or result.stdout}"
                )
            return result.stdout
        except subprocess.SubprocessError as e:
            raise TraceError(f"Trace command error: {e}")

    def _parse_task_list(self, output: str) -> list[Task]:
        """Parse trc ready/list output into Task objects.

        Output format:
            Ready work (not blocked):

            \u25cb ralph-abc123 [P2] Task title
               \u2514\u2500 child of: ralph-parent - Parent title
            \u25cb ralph-def456 [P1] Another task
        """
        tasks = []
        lines = output.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Match task line: \u25cb ralph-id [P#] Title
            task_match = re.match(r"^\u25cb\s+(\S+)\s+\[P(\d+)\]\s+(.+)$", line)
            if task_match:
                task_id = task_match.group(1)
                priority = int(task_match.group(2))
                title = task_match.group(3)

                # Check next line for parent
                parent_id = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    parent_match = re.match(
                        r"^\s+\u2514\u2500\s+child of:\s+(\S+)\s+-\s+",
                        next_line,
                    )
                    if parent_match:
                        parent_id = parent_match.group(1)

                tasks.append(
                    Task(
                        id=task_id,
                        title=title,
                        status="open",
                        priority=priority,
                        parent_id=parent_id,
                    )
                )

            i += 1

        return tasks

    def _parse_blocked_tasks(self, output: str) -> list[Task]:
        """Parse trc list output to identify blocked tasks.

        Blocked tasks have a "blocked by:" marker in the output.
        """
        tasks = []
        lines = output.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Match task line: \u25cb ralph-id [P#] Title
            task_match = re.match(r"^\u25cb\s+(\S+)\s+\[P(\d+)\]\s+(.+)$", line)
            if task_match:
                task_id = task_match.group(1)
                priority = int(task_match.group(2))
                title = task_match.group(3)

                # Check next line for blocked by
                is_blocked = False
                parent_id = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    blocked_match = re.match(
                        r"^\s+\u2514\u2500\s+blocked by:\s+(\S+)\s+-\s+",
                        next_line,
                    )
                    if blocked_match:
                        is_blocked = True
                        parent_id = blocked_match.group(1)

                if is_blocked:
                    tasks.append(
                        Task(
                            id=task_id,
                            title=title,
                            status="open",
                            priority=priority,
                            parent_id=parent_id,
                        )
                    )

            i += 1

        return tasks

    def _parse_closed_task_list(self, output: str) -> list[Task]:
        """Parse trc list --status closed output into Task objects.

        Output format (closed tasks use filled circle ●):
            ● ralph-abc123 [P2] Completed task
               └─ child of: ralph-parent - Parent title
            ● ralph-def456 [P1] Another completed task
        """
        tasks = []
        lines = output.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Match task line: ● ralph-id [P#] Title
            task_match = re.match(r"^●\s+(\S+)\s+\[P(\d+)\]\s+(.+)$", line)
            if task_match:
                task_id = task_match.group(1)
                priority = int(task_match.group(2))
                title = task_match.group(3)

                # Check next line for parent
                parent_id = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    parent_match = re.match(
                        r"^\s+└─\s+child of:\s+(\S+)\s+-\s+",
                        next_line,
                    )
                    if parent_match:
                        parent_id = parent_match.group(1)

                tasks.append(
                    Task(
                        id=task_id,
                        title=title,
                        status="closed",
                        priority=priority,
                        parent_id=parent_id,
                    )
                )

            i += 1

        return tasks

    def _parse_comments(self, output: str) -> list[Comment]:
        """Parse trc show output to extract comments.

        Comments section format:
            Comments:
              [2026-01-20 10:30:00] source: Comment text
        """
        comments = []
        in_comments_section = False

        for line in output.split("\n"):
            if line.strip() == "Comments:":
                in_comments_section = True
                continue

            if in_comments_section:
                # Match: [timestamp] source: text
                # Source can contain spaces/hyphens (e.g., "orient agent", "code-reviewer")
                comment_match = re.match(
                    r"^\s+\[([^\]]+)\]\s+([^:]+):\s+(.+)$",
                    line,
                )
                if comment_match:
                    comments.append(
                        Comment(
                            timestamp=comment_match.group(1),
                            source=comment_match.group(2).strip(),
                            text=comment_match.group(3),
                        )
                    )

        return comments

    def _parse_created_task_id(self, output: str) -> str:
        """Parse task ID from trc create output.

        Output format: Created issue ralph-abc123: Task title
        """
        match = re.search(r"Created issue (\S+):", output)
        if match:
            return match.group(1)
        raise TraceError(f"Could not parse task ID from output: {output}")
