"""SENSE phase: gather claims from systems without judgment.

The SENSE phase gathers claims from various sources (git, trace, database)
without judgment. This module provides:
1. Pydantic models for structured Claims output
2. The sense() function that orchestrates all collection

All structures must be JSON-serializable for passing to ORIENT.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from soda.project import read_memory
from soda.state.db import SodaDB
from soda.state.git import GitClient
from soda.state.trace import TraceClient

logger = logging.getLogger(__name__)


# =============================================================================
# Code State Claims
# =============================================================================


class CommitInfo(BaseModel):
    """Information about a single commit."""

    hash: str = Field(description="Git commit hash (short or full)")
    message: str = Field(description="Commit message")
    timestamp: datetime = Field(description="Commit timestamp")


class DiffSummary(BaseModel):
    """Summary of lines added/removed in a diff."""

    lines_added: int = Field(description="Number of lines added")
    lines_removed: int = Field(description="Number of lines removed")


class FileChange(BaseModel):
    """Detailed change information for a single file."""

    path: str = Field(description="File path")
    change_type: str = Field(description="Change type: added, modified, or deleted")
    lines_added: int = Field(default=0, description="Lines added in this file")
    lines_removed: int = Field(default=0, description="Lines removed in this file")


class GitDelta(BaseModel):
    """Detailed delta information since milestone base.

    Provides per-file line counts and commit messages for ORIENT navigation.
    """

    files: list[FileChange] = Field(
        default_factory=list,
        description="Per-file change details",
    )
    commits: list["CommitInfo"] = Field(
        default_factory=list,
        description="Commits with full messages",
    )
    total_lines_added: int = Field(default=0, description="Total lines added")
    total_lines_removed: int = Field(default=0, description="Total lines removed")


class CodeStateClaims(BaseModel):
    """Claims about the current code state.

    Gathered from git: branch, uncommitted changes, commits since milestone base.
    """

    branch: Optional[str] = Field(
        default=None,
        description="Current branch name",
    )
    staged_count: int = Field(
        default=0,
        description="Number of staged changes",
    )
    unstaged_count: int = Field(
        default=0,
        description="Number of unstaged changes",
    )
    commits: list[CommitInfo] = Field(
        default_factory=list,
        description="Commits since milestone base (hash, message, timestamp)",
    )
    files_changed: list[str] = Field(
        default_factory=list,
        description="Files changed since milestone base",
    )
    diff_summary: Optional[DiffSummary] = Field(
        default=None,
        description="Summary of lines added/removed",
    )
    git_delta: Optional[GitDelta] = Field(
        default=None,
        description="Detailed delta with per-file line counts and commit messages",
    )
    no_base_commit: bool = Field(
        default=False,
        description="True if milestone base is empty (new project)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading code state failed",
    )


# =============================================================================
# Work State Claims
# =============================================================================


class TaskInfo(BaseModel):
    """Information about a single task."""

    id: str = Field(description="Task ID (e.g., 'ralph-abc123')")
    title: str = Field(description="Task title")
    status: str = Field(description="Task status (open, blocked, closed, etc.)")
    blocker_reason: Optional[str] = Field(
        default=None,
        description="Reason for blocking (if status is blocked)",
    )


class TaskFull(BaseModel):
    """Full task data read directly from trace JSONL.

    Includes complete description for ORIENT context.
    """

    id: str = Field(description="Task ID (e.g., 'ralph-abc123')")
    title: str = Field(description="Task title")
    description: str = Field(default="", description="Full task description")
    status: str = Field(description="Task status (open, closed, blocked)")
    parent_id: Optional[str] = Field(
        default=None,
        description="Parent task ID if this is a subtask",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="When the task was created (ISO format)",
    )


class TaskComment(BaseModel):
    """A comment on a task."""

    task_id: str = Field(description="ID of the task this comment belongs to")
    source: str = Field(description="Source of the comment (executor, planner, etc.)")
    text: str = Field(description="Comment text")
    timestamp: datetime = Field(description="When the comment was made")


class WorkStateClaims(BaseModel):
    """Claims about the current work state.

    Gathered from trace: open tasks, blocked tasks, closed tasks, comments.
    """

    open_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Open tasks under milestone root",
    )
    blocked_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Blocked tasks with blocker reasons",
    )
    closed_tasks: list[TaskInfo] = Field(
        default_factory=list,
        description="Closed tasks",
    )
    recent_comments: list[TaskComment] = Field(
        default_factory=list,
        description="Recent comments (last 10) on milestone tasks",
    )
    full_tasks: list[TaskFull] = Field(
        default_factory=list,
        description="Full task data with descriptions (from JSONL)",
    )
    global_open_count: int = Field(
        default=0,
        description="Total open tasks in project (unscoped - what trc list shows)",
    )
    global_closed_count: int = Field(
        default=0,
        description="Total closed tasks in project (unscoped)",
    )
    no_root_work_item: bool = Field(
        default=False,
        description="True if no milestone root exists",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading work state failed",
    )


# =============================================================================
# Project State Claims
# =============================================================================


class IterationSummary(BaseModel):
    """Summary of a past iteration."""

    number: int = Field(description="Iteration number")
    intent: str = Field(description="Intent/goal of the iteration")
    outcome: str = Field(description="Outcome (continue, done, stuck)")


class AgentSummary(BaseModel):
    """Summary from an agent's output."""

    agent_type: str = Field(description="Type of agent (executor, verifier, etc.)")
    summary: str = Field(description="Agent's output summary")


class ProjectStateClaims(BaseModel):
    """Claims about the project state.

    Gathered from database: iteration history, agent summaries.
    """

    iteration_number: int = Field(
        description="Current iteration number",
    )
    iteration_history: list[IterationSummary] = Field(
        default_factory=list,
        description="Recent iteration history (last 5)",
    )
    agent_summaries: list[AgentSummary] = Field(
        default_factory=list,
        description="Last agent summaries (executor, verifier)",
    )
    first_iteration: bool = Field(
        default=False,
        description="True if this is the first iteration",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if reading project state failed",
    )


# =============================================================================
# Human Input Claims
# =============================================================================


class HumanInputClaims(BaseModel):
    """Claims about pending human input.

    Includes type, content, and whether it modifies the spec.
    """

    input_type: str = Field(
        description="Type of input (comment, pause, resume, abort)",
    )
    content: str = Field(
        description="Content of the human input",
    )
    spec_modified: bool = Field(
        default=False,
        description="True if this input modifies the spec",
    )


# =============================================================================
# Main Claims Structure
# =============================================================================


class Claims(BaseModel):
    """Complete claims output from SENSE phase.

    Contains all gathered information from code, work, project,
    human input, and learnings sources.
    """

    timestamp: datetime = Field(
        description="When SENSE was executed",
    )
    iteration_number: int = Field(
        description="Current iteration number",
    )
    code_state: CodeStateClaims = Field(
        description="Claims about code state (git)",
    )
    work_state: WorkStateClaims = Field(
        description="Claims about work state (trace)",
    )
    project_state: ProjectStateClaims = Field(
        description="Claims about project state (database)",
    )
    human_input: Optional[HumanInputClaims] = Field(
        default=None,
        description="Pending human input (if any)",
    )
    learnings: str = Field(
        default="",
        description="Content from memory.md (learnings)",
    )
    file_tree: str = Field(
        default="",
        description="File tree structure of the project",
    )


# =============================================================================
# SENSE Function
# =============================================================================


class SenseContext(BaseModel):
    """Context required for the SENSE phase.

    Contains all the identifiers and configuration needed to collect claims
    from various sources.
    """

    run_id: str = Field(description="Current run ID")
    iteration_number: int = Field(description="Current iteration number")
    milestone_base: Optional[str] = Field(
        default=None,
        description="Git ref for milestone base (None if new project)",
    )
    root_work_item_id: Optional[str] = Field(
        default=None,
        description="Root work item ID in trace (None if not set)",
    )
    project_id: str = Field(description="Project UUID for state lookup")
    project_root: str = Field(description="Path to project root")


# Default directories/files to exclude from file tree
DEFAULT_IGNORES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    "*.egg-info",
    ".eggs",
    ".coverage",
    "htmlcov",
    ".hypothesis",
}


def _collect_file_tree(project_root: str, max_depth: int = 5) -> str:
    """Collect file tree structure of the project.

    Args:
        project_root: Path to the project root directory
        max_depth: Maximum depth to traverse (default 5)

    Returns:
        Formatted tree string like the 'tree' command output
    """
    try:
        root_path = Path(project_root)
        if not root_path.exists():
            return ""

        lines: list[str] = []

        def should_ignore(name: str) -> bool:
            """Check if a file/directory should be ignored."""
            if name in DEFAULT_IGNORES:
                return True
            # Check wildcard patterns
            for pattern in DEFAULT_IGNORES:
                if pattern.startswith("*") and name.endswith(pattern[1:]):
                    return True
            return False

        def build_tree(path: Path, prefix: str = "", depth: int = 0) -> None:
            """Recursively build tree structure."""
            if depth > max_depth:
                return

            # Get children, filtering out ignored items
            try:
                children = sorted(
                    [c for c in path.iterdir() if not should_ignore(c.name)],
                    key=lambda x: (not x.is_dir(), x.name.lower()),
                )
            except PermissionError:
                return

            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{child.name}")

                if child.is_dir():
                    extension = "    " if is_last else "│   "
                    build_tree(child, prefix + extension, depth + 1)

        # Start building from root
        lines.append(root_path.name + "/")
        build_tree(root_path)

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to collect file tree: {e}")
        return ""


def _collect_code_state(
    git_client: GitClient,
    milestone_base: Optional[str],
) -> CodeStateClaims:
    """Collect code state claims from git.

    Args:
        git_client: GitClient instance for git operations
        milestone_base: Base ref for comparing commits (None if new project)

    Returns:
        CodeStateClaims with git state or error message
    """
    try:
        # No base commit case
        if milestone_base is None:
            return CodeStateClaims(
                branch=git_client.get_current_branch(),
                staged_count=0,
                unstaged_count=0,
                commits=[],
                files_changed=[],
                diff_summary=None,
                no_base_commit=True,
            )

        # Get branch
        branch = git_client.get_current_branch()

        # Get uncommitted changes via git status --porcelain
        status_result = git_client._run_git(["status", "--porcelain"], check=False)
        staged_count = 0
        unstaged_count = 0
        if status_result.returncode == 0 and status_result.stdout.strip():
            for line in status_result.stdout.strip().split("\n"):
                if not line:
                    continue
                # Format: XY filename
                # X = staged status, Y = unstaged status
                # Space means no change in that index
                if len(line) >= 2:
                    staged_status = line[0]
                    unstaged_status = line[1]
                    if staged_status not in (" ", "?"):
                        staged_count += 1
                    if unstaged_status not in (" ", "?") or line.startswith("??"):
                        unstaged_count += 1

        # Get commits since base
        git_commits = git_client.get_commits_since(milestone_base)
        commits = [
            CommitInfo(
                hash=c.sha,
                message=c.message,
                timestamp=datetime.fromisoformat(c.timestamp.replace("Z", "+00:00")),
            )
            for c in git_commits
        ]

        # Get files changed
        files_result = git_client._run_git(
            ["diff", "--name-only", f"{milestone_base}..HEAD"],
            check=False,
        )
        files_changed = []
        if files_result.returncode == 0 and files_result.stdout.strip():
            files_changed = files_result.stdout.strip().split("\n")

        # Get diff summary
        diff_summary = None
        diff_stat_result = git_client._run_git(
            ["diff", "--shortstat", f"{milestone_base}..HEAD"],
            check=False,
        )
        if diff_stat_result.returncode == 0 and diff_stat_result.stdout.strip():
            # Parse shortstat output like: "5 files changed, 100 insertions(+), 50 deletions(-)"
            stat_text = diff_stat_result.stdout.strip()
            lines_added = 0
            lines_removed = 0
            if "insertion" in stat_text:
                import re
                add_match = re.search(r"(\d+) insertion", stat_text)
                if add_match:
                    lines_added = int(add_match.group(1))
            if "deletion" in stat_text:
                import re
                del_match = re.search(r"(\d+) deletion", stat_text)
                if del_match:
                    lines_removed = int(del_match.group(1))
            diff_summary = DiffSummary(
                lines_added=lines_added,
                lines_removed=lines_removed,
            )

        # Collect detailed git delta with per-file line counts
        git_delta = None
        try:
            file_changes: list[FileChange] = []

            # Get per-file line counts: git diff --numstat base..HEAD
            numstat_result = git_client._run_git(
                ["diff", "--numstat", f"{milestone_base}..HEAD"],
                check=False,
            )
            numstat_map: dict[str, tuple[int, int]] = {}
            if numstat_result.returncode == 0 and numstat_result.stdout.strip():
                for line in numstat_result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        added_str, removed_str, filepath = parts[0], parts[1], parts[2]
                        # Handle binary files (shown as '-')
                        added = int(added_str) if added_str != "-" else 0
                        removed = int(removed_str) if removed_str != "-" else 0
                        numstat_map[filepath] = (added, removed)

            # Get change types: git diff --name-status base..HEAD
            name_status_result = git_client._run_git(
                ["diff", "--name-status", f"{milestone_base}..HEAD"],
                check=False,
            )
            if name_status_result.returncode == 0 and name_status_result.stdout.strip():
                for line in name_status_result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        status_code, filepath = parts[0], parts[1]
                        # Map status codes to human-readable types
                        change_type_map = {
                            "A": "added",
                            "M": "modified",
                            "D": "deleted",
                            "R": "renamed",
                            "C": "copied",
                        }
                        change_type = change_type_map.get(
                            status_code[0], "modified"
                        )
                        lines_added_file, lines_removed_file = numstat_map.get(
                            filepath, (0, 0)
                        )
                        file_changes.append(
                            FileChange(
                                path=filepath,
                                change_type=change_type,
                                lines_added=lines_added_file,
                                lines_removed=lines_removed_file,
                            )
                        )

            # Calculate totals
            total_added = sum(fc.lines_added for fc in file_changes)
            total_removed = sum(fc.lines_removed for fc in file_changes)

            git_delta = GitDelta(
                files=file_changes,
                commits=commits,  # Reuse already-collected commits
                total_lines_added=total_added,
                total_lines_removed=total_removed,
            )
        except Exception as e:
            logger.warning(f"Failed to collect git delta: {e}")
            # git_delta stays None

        return CodeStateClaims(
            branch=branch,
            staged_count=staged_count,
            unstaged_count=unstaged_count,
            commits=commits,
            files_changed=files_changed,
            diff_summary=diff_summary,
            git_delta=git_delta,
            no_base_commit=False,
        )

    except Exception as e:
        logger.warning(f"Failed to collect code state: {e}")
        return CodeStateClaims(
            branch=None,
            staged_count=0,
            unstaged_count=0,
            commits=[],
            files_changed=[],
            diff_summary=None,
            git_delta=None,
            error=str(e),
        )


def _collect_full_tasks(
    project_root: str,
    root_work_item_id: Optional[str],
) -> list[TaskFull]:
    """Collect full task data from .trace/issues.jsonl.

    Reads the trace JSONL file directly to surface full task context
    including descriptions, without relying on the trace CLI.

    Args:
        project_root: Path to the project root directory
        root_work_item_id: Root work item ID to filter tasks (None = all tasks)

    Returns:
        List of TaskFull objects with complete task data
    """
    tasks: list[TaskFull] = []
    jsonl_path = Path(project_root) / ".trace" / "issues.jsonl"

    if not jsonl_path.exists():
        logger.debug(f"Trace JSONL not found at {jsonl_path}")
        return tasks

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    task_id = data.get("id", "")

                    # Extract parent_id from dependencies
                    parent_id = None
                    deps = data.get("dependencies", [])
                    for dep in deps:
                        if dep.get("type") == "parent":
                            parent_id = dep.get("depends_on_id")
                            break

                    # Filter by root if specified
                    if root_work_item_id:
                        # Include if task is root, or is a child of root
                        if task_id != root_work_item_id and parent_id != root_work_item_id:
                            # Check if any ancestor is the root (recursive check)
                            # For now, only include direct children + root itself
                            # A full implementation would traverse the tree
                            continue

                    tasks.append(
                        TaskFull(
                            id=task_id,
                            title=data.get("title", ""),
                            description=data.get("description", ""),
                            status=data.get("status", "open"),
                            parent_id=parent_id,
                            created_at=data.get("created_at"),
                        )
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse trace line: {e}")
                    continue

    except Exception as e:
        logger.warning(f"Failed to read trace JSONL: {e}")

    return tasks


def _collect_work_state(
    trace_client: TraceClient,
    root_work_item_id: Optional[str],
    project_root: str,
) -> WorkStateClaims:
    """Collect work state claims from trace.

    Args:
        trace_client: TraceClient instance for trace operations
        root_work_item_id: Root work item ID (None if not set)

    Returns:
        WorkStateClaims with task state or error message
    """
    try:
        # No root work item case
        if root_work_item_id is None:
            return WorkStateClaims(
                open_tasks=[],
                blocked_tasks=[],
                closed_tasks=[],
                recent_comments=[],
                no_root_work_item=True,
            )

        # Get open tasks
        open_trace_tasks = trace_client.get_open_tasks(root_id=root_work_item_id)
        open_tasks = [
            TaskInfo(
                id=t.id,
                title=t.title,
                status=t.status,
            )
            for t in open_trace_tasks
        ]

        # Get blocked tasks
        blocked_trace_tasks = trace_client.get_blocked_tasks(root_id=root_work_item_id)
        blocked_tasks = [
            TaskInfo(
                id=t.id,
                title=t.title,
                status="blocked",
                blocker_reason=t.parent_id,  # parent_id is the blocker in trace
            )
            for t in blocked_trace_tasks
        ]

        # Get closed tasks
        closed_trace_tasks = trace_client.get_closed_tasks(root_id=root_work_item_id)
        closed_tasks = [
            TaskInfo(
                id=t.id,
                title=t.title,
                status="closed",
            )
            for t in closed_trace_tasks
        ]

        # Get recent comments (last 10)
        # For each task, get comments and merge
        all_comments: list[TaskComment] = []
        # Collect comments from all tasks (open + blocked)
        for task in open_trace_tasks + blocked_trace_tasks:
            task_comments = trace_client.get_task_comments(task.id)
            for c in task_comments:
                try:
                    timestamp = datetime.fromisoformat(c.timestamp)
                except ValueError:
                    timestamp = datetime.now()
                all_comments.append(
                    TaskComment(
                        task_id=task.id,
                        source=c.source,
                        text=c.text,
                        timestamp=timestamp,
                    )
                )

        # Sort by timestamp desc and take last 10
        all_comments.sort(key=lambda c: c.timestamp, reverse=True)
        recent_comments = all_comments[:10]

        # Collect full task data from JSONL
        full_tasks = _collect_full_tasks(project_root, root_work_item_id)

        # Collect global counts (unscoped - what trc list shows)
        all_tasks = _collect_full_tasks(project_root, None)  # No root filter
        global_open_count = sum(1 for t in all_tasks if t.status == "open")
        global_closed_count = sum(1 for t in all_tasks if t.status == "closed")

        return WorkStateClaims(
            open_tasks=open_tasks,
            blocked_tasks=blocked_tasks,
            closed_tasks=closed_tasks,
            recent_comments=recent_comments,
            full_tasks=full_tasks,
            global_open_count=global_open_count,
            global_closed_count=global_closed_count,
            no_root_work_item=False,
        )

    except Exception as e:
        logger.warning(f"Failed to collect work state: {e}")
        return WorkStateClaims(
            open_tasks=[],
            blocked_tasks=[],
            closed_tasks=[],
            recent_comments=[],
            full_tasks=[],
            global_open_count=0,
            global_closed_count=0,
            error=str(e),
        )


def _collect_project_state(
    db: SodaDB,
    run_id: str,
    iteration_number: int,
) -> ProjectStateClaims:
    """Collect project state claims from database.

    Args:
        db: SodaDB instance for database operations
        run_id: Current run ID
        iteration_number: Current iteration number

    Returns:
        ProjectStateClaims with iteration history or error message
    """
    try:
        # Get iteration history (last 5)
        all_iterations = db.get_iterations(run_id)

        # Determine if first iteration
        first_iteration = len(all_iterations) == 0

        # Get last 5 iterations
        recent_iterations = all_iterations[-5:] if all_iterations else []
        iteration_history = [
            IterationSummary(
                number=it.number,
                intent=it.intent,
                outcome=it.outcome.value,
            )
            for it in recent_iterations
        ]

        # Get last agent summaries (from most recent iteration)
        agent_summaries: list[AgentSummary] = []
        if all_iterations:
            latest_iteration = all_iterations[-1]
            if latest_iteration.id is not None:
                outputs = db.get_agent_outputs(latest_iteration.id)
                agent_summaries = [
                    AgentSummary(
                        agent_type=o.agent_type.value,
                        summary=o.summary,
                    )
                    for o in outputs
                ]

        return ProjectStateClaims(
            iteration_number=iteration_number,
            iteration_history=iteration_history,
            agent_summaries=agent_summaries,
            first_iteration=first_iteration,
        )

    except Exception as e:
        logger.warning(f"Failed to collect project state: {e}")
        return ProjectStateClaims(
            iteration_number=iteration_number,
            iteration_history=[],
            agent_summaries=[],
            error=str(e),
        )


def _collect_human_input(
    db: SodaDB,
    run_id: str,
) -> Optional[HumanInputClaims]:
    """Collect pending human input from database.

    Args:
        db: SodaDB instance for database operations
        run_id: Current run ID

    Returns:
        HumanInputClaims if pending input exists, None otherwise
    """
    try:
        unconsumed = db.get_unconsumed_inputs(run_id)
        if not unconsumed:
            return None

        # Take the first unconsumed input
        first_input = unconsumed[0]

        # Check if content indicates spec modification
        spec_modified = "spec" in first_input.content.lower() and (
            "update" in first_input.content.lower()
            or "change" in first_input.content.lower()
            or "modify" in first_input.content.lower()
            or "add" in first_input.content.lower()
        )

        return HumanInputClaims(
            input_type=first_input.input_type.value,
            content=first_input.content,
            spec_modified=spec_modified,
        )

    except Exception as e:
        logger.warning(f"Failed to collect human input: {e}")
        return None


def sense(
    ctx: SenseContext,
    git_client: GitClient,
    trace_client: TraceClient,
    db: SodaDB,
) -> Claims:
    """Execute the SENSE phase: gather claims from all sources.

    This function orchestrates collection from:
    - Git (code state)
    - Trace (work state)
    - Database (project state, human input)
    - Memory file (learnings)

    Handles partial failures gracefully - if any source fails, that section
    includes an error message but SENSE continues with other sources.

    Args:
        ctx: SenseContext with run context and identifiers
        git_client: GitClient for git operations
        trace_client: TraceClient for trace operations
        db: SodaDB for database operations

    Returns:
        Claims object with all gathered information
    """
    timestamp = datetime.now()

    # Collect from each source independently
    code_state = _collect_code_state(
        git_client=git_client,
        milestone_base=ctx.milestone_base,
    )

    work_state = _collect_work_state(
        trace_client=trace_client,
        root_work_item_id=ctx.root_work_item_id,
        project_root=ctx.project_root,
    )

    project_state = _collect_project_state(
        db=db,
        run_id=ctx.run_id,
        iteration_number=ctx.iteration_number,
    )

    human_input = _collect_human_input(
        db=db,
        run_id=ctx.run_id,
    )

    # Collect learnings from memory
    try:
        learnings = read_memory(ctx.project_id)
    except Exception as e:
        logger.warning(f"Failed to read memory: {e}")
        learnings = ""

    # Collect file tree
    file_tree = _collect_file_tree(ctx.project_root)

    return Claims(
        timestamp=timestamp,
        iteration_number=ctx.iteration_number,
        code_state=code_state,
        work_state=work_state,
        project_state=project_state,
        human_input=human_input,
        learnings=learnings,
        file_tree=file_tree,
    )
