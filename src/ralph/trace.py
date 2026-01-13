"""Wrapper for Trace CLI commands."""

import subprocess
import json
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Task:
    """Represents a Trace task."""
    id: str
    title: str
    status: str
    priority: int
    project: str
    created: str
    updated: str
    description: Optional[str] = None
    parent: Optional[str] = None


class TraceClient:
    """Client for interacting with Trace CLI."""

    def __init__(self, project_path: Optional[str] = None):
        """Initialize Trace client.

        Args:
            project_path: Path to the project directory. If None, uses current directory.
        """
        self.project_path = project_path

    def _run_command(self, args: List[str]) -> str:
        """Run a trc command and return output.

        Args:
            args: Command arguments to pass to trc

        Returns:
            Command output as string

        Raises:
            RuntimeError: If command fails
        """
        cmd = ["trc"] + args
        if self.project_path:
            cmd.extend(["--project", self.project_path])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Trace command failed: {e.stderr}")

    def ready(self) -> List[Task]:
        """Get all ready tasks (not blocked).

        Returns:
            List of Task objects that are ready to work on
        """
        output = self._run_command(["ready"])
        tasks = []

        # Parse output format:
        # ○ task-id [P2] Task title
        for line in output.strip().split('\n'):
            if line.startswith('○'):
                parts = line.split(None, 3)  # Split on whitespace, max 4 parts
                if len(parts) >= 4:
                    task_id = parts[1]
                    priority_str = parts[2].strip('[]P')
                    title = parts[3]

                    # Get full task details
                    task = self.show(task_id)
                    if task:
                        tasks.append(task)

        return tasks

    def list(self) -> List[Task]:
        """Get all tasks in the backlog.

        Returns:
            List of all Task objects
        """
        output = self._run_command(["list"])
        tasks = []

        # Parse output format (same as ready)
        for line in output.strip().split('\n'):
            if line.startswith('○') or line.startswith('✓'):
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    task_id = parts[1]

                    # Get full task details
                    task = self.show(task_id)
                    if task:
                        tasks.append(task)

        return tasks

    def show(self, task_id: str) -> Optional[Task]:
        """Get details of a specific task.

        Args:
            task_id: ID of the task to show

        Returns:
            Task object or None if not found
        """
        try:
            output = self._run_command(["show", task_id])
        except RuntimeError:
            return None

        # Parse task details
        task_data = {}
        description_lines = []
        in_description = False

        for line in output.strip().split('\n'):
            if ':' in line and not in_description:
                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                value = value.strip()

                if key == 'description':
                    in_description = True
                    if value:  # Description starts on same line
                        description_lines.append(value)
                else:
                    task_data[key] = value
            elif in_description:
                # Empty line ends description
                if not line.strip() and description_lines:
                    break
                if line.strip():
                    description_lines.append(line)

        if description_lines:
            task_data['description'] = '\n'.join(description_lines)

        return Task(
            id=task_data.get('id', ''),
            title=task_data.get('title', ''),
            status=task_data.get('status', ''),
            priority=int(task_data.get('priority', 0)),
            project=task_data.get('project', ''),
            created=task_data.get('created', ''),
            updated=task_data.get('updated', ''),
            description=task_data.get('description'),
            parent=task_data.get('parent')
        )

    def create(self, title: str, description: str = "", parent: Optional[str] = None) -> Task:
        """Create a new task.

        Args:
            title: Task title
            description: Task description (required for context across iterations)
            parent: Parent task ID (for subtasks)

        Returns:
            Created Task object
        """
        args = ["create", title]

        if description:
            args.extend(["--description", description])

        if parent:
            args.extend(["--parent", parent])

        output = self._run_command(args)

        # Extract task ID from output (format: "Created task-id")
        task_id = output.strip().split()[-1]

        # Get full task details
        task = self.show(task_id)
        if not task:
            raise RuntimeError(f"Failed to retrieve created task {task_id}")

        return task

    def close(self, task_id: str):
        """Mark a task as complete.

        Args:
            task_id: ID of the task to close
        """
        self._run_command(["close", task_id])

    def comment(self, task_id: str, comment: str):
        """Add a comment to a task.

        Args:
            task_id: ID of the task
            comment: Comment text to add
        """
        self._run_command(["comment", task_id, comment])

    def get_task_state_summary(self) -> Dict[str, any]:
        """Get a summary of current task state.

        Returns:
            Dictionary with task counts and ready tasks
        """
        all_tasks = self.list()
        ready_tasks = self.ready()

        open_count = sum(1 for t in all_tasks if t.status == 'open')
        closed_count = sum(1 for t in all_tasks if t.status == 'closed')

        return {
            'total': len(all_tasks),
            'open': open_count,
            'closed': closed_count,
            'ready': len(ready_tasks),
            'ready_tasks': ready_tasks
        }
