"""Main iteration loop orchestration for Ralph2."""

import asyncio
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import uuid
import json

from .state.db import Ralph2DB
from .state.models import Run, Iteration, AgentOutput, HumanInput
from .agents.planner import run_planner
from .agents.executor import run_executor
from .agents.verifier import run_verifier
from .agents.specialist import CodeReviewerSpecialist, run_specialist
from .project import ProjectContext, read_memory
from .feedback import create_work_items_from_feedback
from .milestone import complete_milestone
from .git import create_worktree, merge_branch_to_main, merge_branch, remove_worktree, abort_merge


@dataclass
class IterationContext:
    """Context passed between iteration phases."""
    run_id: str
    iteration_id: int
    iteration_number: int
    intent: str
    memory: str
    last_executor_summary: Optional[str] = None
    last_verifier_assessment: Optional[str] = None
    last_specialist_feedback: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    iteration_plan: Optional[Dict[str, Any]] = None


def _extract_spec_title(spec_content: str) -> str:
    """
    Extract the title from spec content.

    Looks for the first H1 heading (# Title) in the content.
    If no H1 is found, returns "Spec" as default.

    Args:
        spec_content: The spec file content

    Returns:
        The extracted title or "Spec" as default
    """
    lines = spec_content.split('\n')
    for line in lines:
        if line.strip().startswith('# '):
            # Remove the # and any leading/trailing whitespace
            return line.strip()[2:].strip()
    return "Spec"


def slugify_spec_title(title: str, max_length: int = 50) -> str:
    """
    Convert a spec title to a URL/branch-safe slug.

    Converts to lowercase, removes special characters, replaces spaces
    with hyphens, and truncates to max_length.

    Args:
        title: The title to slugify
        max_length: Maximum length of the slug (default: 50)

    Returns:
        Slugified title, or "spec" if result would be empty
    """
    if not title:
        return "spec"

    # Convert to lowercase
    slug = title.lower()

    # Replace any non-alphanumeric character (except spaces) with nothing
    slug = re.sub(r'[^a-z0-9\s]', '', slug)

    # Replace multiple spaces with single space
    slug = re.sub(r'\s+', ' ', slug)

    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    # Truncate to max_length, ensuring we don't cut mid-word if possible
    if len(slug) > max_length:
        slug = slug[:max_length]
        # Remove trailing hyphen if present
        slug = slug.rstrip('-')

    # If result is empty, return default
    if not slug:
        return "spec"

    return slug


def branch_exists(branch_name: str, cwd: str) -> bool:
    """
    Check if a git branch exists.

    Args:
        branch_name: The branch name to check
        cwd: Working directory (git repository root)

    Returns:
        True if branch exists, False otherwise
    """
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    return result.returncode == 0


def repo_has_commits(cwd: str) -> bool:
    """Check if the git repository has any commits.

    Args:
        cwd: Working directory (git repository root)

    Returns:
        True if repo has at least one commit, False otherwise
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    return result.returncode == 0


def ensure_repo_has_commits(cwd: str) -> bool:
    """Ensure the git repository has at least one commit.

    If the repo has no commits, creates an initial empty commit to enable
    branching operations. This handles the case where ralph2 is run on a
    fresh repository.

    Args:
        cwd: Working directory (git repository root)

    Returns:
        True if repo now has commits (either already had or was created)
    """
    if repo_has_commits(cwd):
        return True

    # Create initial commit
    print("   📝 Creating initial commit (fresh repository)...")
    result = subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Initial commit (created by Ralph2)"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    if result.returncode != 0:
        print(f"   ⚠️  Warning: Could not create initial commit: {result.stderr}")
        return False

    return True


def generate_unique_branch_name(
    slug: str,
    cwd: str,
    explicit_branch: str | None = None
) -> str:
    """
    Generate a unique branch name from a slug.

    If explicit_branch is provided, returns it as-is (reuses existing branches).
    Otherwise, generates feature/{slug} and appends -2, -3, etc. if it exists.

    Args:
        slug: The slugified spec title
        cwd: Working directory (git repository root)
        explicit_branch: Optional explicit branch name to use

    Returns:
        A unique branch name in format "feature/{slug}" or "feature/{slug}-N"
    """
    # If explicit branch provided, use it as-is (reuse existing)
    if explicit_branch:
        return explicit_branch

    # Generate base branch name
    base_name = f"feature/{slug}"

    # Check if base name exists
    if not branch_exists(base_name, cwd):
        return base_name

    # Try with suffixes -2, -3, etc.
    suffix = 2
    while True:
        candidate = f"{base_name}-{suffix}"
        if not branch_exists(candidate, cwd):
            return candidate
        suffix += 1
        # Safety limit to prevent infinite loop
        if suffix > 100:
            raise RuntimeError(f"Could not find unique branch name for {base_name}")


def slugify_to_branch_name(title: str, max_length: int = 50) -> str:
    """
    Convert a title to a full branch name with feature/ prefix.

    This is a convenience wrapper around slugify_spec_title that adds
    the feature/ prefix.

    Args:
        title: The title to slugify
        max_length: Maximum length of the slug portion (default: 50)

    Returns:
        Branch name in format "feature/{slug}" or "feature/spec" if empty
    """
    slug = slugify_spec_title(title, max_length)
    return f"feature/{slug}"


def create_milestone_branch(
    branch_name: str,
    cwd: str,
    allow_suffix: bool = True
) -> str:
    """
    Create a milestone branch if it doesn't exist.

    When allow_suffix is True and the branch exists, appends -2, -3, etc.
    until a unique name is found (for auto-generated branch names).

    When allow_suffix is False and the branch exists, reuses the existing
    branch (for user-specified --branch flag).

    Args:
        branch_name: The desired branch name
        cwd: Working directory (git repository root)
        allow_suffix: If True, append suffix to find unique name; if False,
                     reuse existing branch

    Returns:
        The actual branch name used (may have suffix if allow_suffix=True)

    Raises:
        RuntimeError: If branch creation fails
    """
    # Check if branch exists
    if branch_exists(branch_name, cwd):
        if not allow_suffix:
            # User-specified branch: reuse existing
            return branch_name
        else:
            # Auto-generated: find unique name with suffix
            suffix = 2
            while True:
                candidate = f"{branch_name}-{suffix}"
                if not branch_exists(candidate, cwd):
                    branch_name = candidate
                    break
                suffix += 1
                if suffix > 100:
                    raise RuntimeError(f"Could not find unique branch name for {branch_name}")

    # Create the branch from main (as per spec: "create branch from main")
    result = subprocess.run(
        ["git", "branch", branch_name, "main"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    if result.returncode != 0 and not branch_exists(branch_name, cwd):
        raise RuntimeError(f"Failed to create branch {branch_name}: {result.stderr}")

    return branch_name


def _create_milestone_branch(branch_name: str, cwd: str) -> bool:
    """
    Create the milestone branch if it doesn't exist.

    The branch is created from main to ensure a clean starting point.

    Args:
        branch_name: The branch name to create
        cwd: Working directory (git repository root)

    Returns:
        True if branch was created or already exists
    """
    if branch_exists(branch_name, cwd):
        return True

    # Create branch from main (as per spec: "create branch from main")
    result = subprocess.run(
        ["git", "branch", branch_name, "main"],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    return result.returncode == 0


class Ralph2Runner:
    """Orchestrates the Ralph2 multi-agent iteration loop."""

    @staticmethod
    def validate_work_item_id(work_item_id: str) -> bool:
        """
        Validate that a work item ID matches expected format.

        Work item IDs can be in formats like:
        - "ralph-1abc23" (standard format)
        - "tmpro-ddk9g-b2fi3m" (multiple segments, e.g., from temp directories)
        - "ralph2-executor-ralph-0ikoux" (nested/compound IDs)

        This validation prevents command injection and path traversal attacks
        while allowing the various ID formats Trace generates.

        Args:
            work_item_id: The work item ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not work_item_id:
            return False

        # Allow alphanumeric segments separated by hyphens or underscores
        # Must start with a letter, no special characters (no path separators, shell metacharacters)
        # Segments can be alphanumeric, separated by hyphens
        pattern = r'^[a-zA-Z][a-zA-Z0-9]*(-[a-zA-Z0-9]+)+$'
        return bool(re.match(pattern, work_item_id))

    def __init__(
        self,
        spec_path: Optional[str],
        project_context: ProjectContext,
        root_work_item_id: Optional[str] = None,
        spec_content: Optional[str] = None,
        branch: Optional[str] = None
    ):
        """
        Initialize Ralph2 runner.

        Args:
            spec_path: Path to the Ralph2file (spec), or None if spec_content provided
            project_context: ProjectContext with paths for state storage
            root_work_item_id: Optional root work item ID (spec milestone in Trace)
            spec_content: Optional spec content (used when running from work item)
            branch: Optional explicit milestone branch name. If not provided, a branch
                   will be auto-generated from the spec title.

        Raises:
            ValueError: If root_work_item_id is provided but has invalid format
            ValueError: If neither spec_path nor spec_content is provided
        """
        self.spec_path = spec_path or f"trace:{root_work_item_id}"
        self.project_context = project_context

        # Validate root_work_item_id format before any subprocess calls
        if root_work_item_id is not None and not self.validate_work_item_id(root_work_item_id):
            raise ValueError(f"Invalid work item ID format: {root_work_item_id}")

        self.db = Ralph2DB(str(project_context.db_path))
        self.root_work_item_id = root_work_item_id

        # Store explicit branch (will be resolved during run if not provided)
        self._branch = branch
        self._milestone_branch: Optional[str] = None  # Will be set during run setup

        # Load spec content from file or use provided content
        if spec_content:
            self.spec_content = spec_content
        elif spec_path:
            with open(spec_path, 'r') as f:
                self.spec_content = f.read()
        else:
            raise ValueError("Either spec_path or spec_content must be provided")

        # Output directory is managed by ProjectContext
        self.output_dir = project_context.outputs_dir

    @property
    def branch_option(self) -> Optional[str]:
        """Get the explicit branch option passed to the runner."""
        return self._branch

    @property
    def milestone_branch(self) -> Optional[str]:
        """Get the current milestone branch (may be None until run starts)."""
        return self._milestone_branch

    @milestone_branch.setter
    def milestone_branch(self, value: Optional[str]):
        """Set the milestone branch."""
        self._milestone_branch = value

    def _ensure_milestone_branch(self) -> str:
        """
        Ensure a milestone branch exists for this run.

        If an explicit branch was provided via --branch, uses that.
        Otherwise, auto-generates from the spec title with uniqueness handling.

        Returns:
            The milestone branch name
        """
        cwd = str(self.project_context.project_root)

        if self._branch:
            # User-specified branch: use as-is (reuse if exists)
            branch_name = create_milestone_branch(self._branch, cwd, allow_suffix=False)
        else:
            # Auto-generate from spec title
            spec_title = _extract_spec_title(self.spec_content)
            base_branch_name = slugify_to_branch_name(spec_title)
            branch_name = create_milestone_branch(base_branch_name, cwd, allow_suffix=True)

        self._milestone_branch = branch_name
        return branch_name

    def _ensure_root_work_item(self) -> str:
        """
        Ensure a root work item exists for this spec.

        If root_work_item_id was provided at initialization, use it.
        Otherwise, check if a previous run has a root work item and reuse it.
        If not, create a new root work item from the spec title.

        Returns:
            The root work item ID

        Raises:
            RuntimeError: If unable to create or verify the root work item
        """
        # If explicitly provided, use it
        if self.root_work_item_id:
            return self.root_work_item_id

        # Check if any previous run has a root work item
        all_runs = self.db.list_runs()
        for existing_run in all_runs:
            if existing_run.root_work_item_id:
                # Verify it still exists in Trace
                try:
                    result = subprocess.run(
                        ["trc", "show", existing_run.root_work_item_id],
                        cwd=self.project_context.project_root,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0:
                        self.root_work_item_id = existing_run.root_work_item_id
                        return self.root_work_item_id
                    else:
                        # Check if it's a "not found" error (expected) vs other errors (should be logged)
                        stderr_lower = result.stderr.lower() if result.stderr else ""
                        if "not found" in stderr_lower or "does not exist" in stderr_lower:
                            # Expected case: work item was deleted or doesn't exist, continue silently
                            pass
                        else:
                            # Unexpected error: log it explicitly
                            print(f"   ⚠️  Warning: Error verifying work item {existing_run.root_work_item_id}: {result.stderr.strip() if result.stderr else 'Unknown error'}")
                except Exception as e:
                    print(f"   ⚠️  Warning: Could not verify existing root work item: {e}")

        # Create a new root work item
        spec_title = _extract_spec_title(self.spec_content)

        try:
            result = subprocess.run(
                ["trc", "create", spec_title, "--description", self.spec_content[:500]],
                cwd=self.project_context.project_root,
                capture_output=True,
                text=True,
                check=True
            )

            # Extract work item ID from output
            # Expected format: "Created <id>: <title>" (possibly with other lines before)
            output = result.stdout.strip()
            # Get the last line which should contain "Created <id>: <title>"
            last_line = output.split('\n')[-1].strip()
            if last_line.startswith("Created "):
                # Extract the ID between "Created " and ":"
                work_item_id = last_line.split()[1].rstrip(":")
            else:
                # Fallback: try to extract ID-like pattern from last line
                match = re.search(r'(\w+-\w+)', last_line)
                if match:
                    work_item_id = match.group(1)
                else:
                    raise RuntimeError(f"Could not extract work item ID from output: {last_line}")

            # Verify it looks like a valid work item ID (format: word-word)
            if not re.match(r'\w+-\w+', work_item_id):
                raise RuntimeError(f"Invalid work item ID format: {work_item_id}")

            self.root_work_item_id = work_item_id
            print(f"   📋 Created root work item: {work_item_id}")

            return work_item_id

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create root work item: {e.stderr}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to create root work item: {e}") from e


    def _save_agent_messages(self, iteration_id: int, agent_type: str, messages: list) -> str:
        """
        Save agent messages to a JSONL file.

        Args:
            iteration_id: Iteration ID
            agent_type: Type of agent (planner, executor, verifier)
            messages: List of message dictionaries from the agent

        Returns:
            Path to the saved output file
        """
        output_path = self.output_dir / f"iteration_{iteration_id}_{agent_type}.jsonl"

        # Save as JSONL (each message is one line)
        with open(output_path, 'w') as f:
            for msg in messages:
                json.dump(msg, f)
                f.write('\n')

        return str(output_path)

    def _cleanup_abandoned_branches(self):
        """Clean up abandoned ralph2/* feature branches and worktrees from interrupted work."""
        try:
            cwd = self.project_context.project_root
            self._cleanup_worktrees(cwd)
            self._cleanup_branches(cwd)
        except Exception as e:
            print(f"   ⚠️  Warning: Could not clean up branches/worktrees: {e}")

    def _cleanup_worktrees(self, cwd):
        """Clean up abandoned worktrees."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, check=False, cwd=cwd
        )
        if result.returncode != 0:
            return

        lines = result.stdout.strip().split('\n')
        for line in lines:
            if line.startswith('worktree '):
                worktree_path = line.replace('worktree ', '').strip()
                if 'ralph2-executor-' in worktree_path:
                    print(f"   🧹 Cleaning up abandoned worktree: {worktree_path}")
                    subprocess.run(
                        ["git", "worktree", "remove", worktree_path, "--force"],
                        capture_output=True, check=False, cwd=cwd
                    )

    def _cleanup_branches(self, cwd):
        """Clean up abandoned ralph2/* branches."""
        result = subprocess.run(
            ["git", "branch", "--list", "ralph2/*"],
            capture_output=True, text=True, check=False, cwd=cwd
        )
        if result.returncode != 0 or not result.stdout.strip():
            return

        branches = [b.strip().replace('* ', '') for b in result.stdout.strip().split('\n')]
        for branch in branches:
            if branch:
                print(f"   🧹 Cleaning up abandoned branch: {branch}")
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    capture_output=True, check=False, cwd=cwd
                )

    # =========================================================================
    # Orchestrator-managed worktree lifecycle
    # =========================================================================
    #
    # These methods implement the orchestrator-managed worktree pattern:
    # - Create all worktrees BEFORE launching parallel executors
    # - Merge completed worktrees SERIALLY after all executors finish
    # - Cleanup ALL worktrees (guaranteed, even on failure)
    #
    # This eliminates:
    # - Race conditions from parallel merges
    # - "git checkout main" failures when other worktrees have main checked out
    # - Stale worktrees from cleanup failures
    # =========================================================================

    def _create_worktrees(
        self, work_items: List[dict], run_id: str
    ) -> List[Tuple[dict, str, str]]:
        """Create worktrees for each work item BEFORE launching executors.

        This ensures all worktrees exist before any parallel execution begins,
        preventing race conditions in branch/worktree creation.

        Worktrees are branched FROM the milestone branch (not main), implementing
        milestone branch isolation.

        Args:
            work_items: List of work item dicts with 'work_item_id' key
            run_id: Current run ID (for worktree path uniqueness)

        Returns:
            List of (work_item, worktree_path, branch_name) tuples for successful creations.
            Failed creations are logged but not included in the result.
        """
        cwd = str(self.project_context.project_root)
        worktree_info = []

        # Use milestone branch as base if available, otherwise branch from current HEAD
        base_branch = getattr(self, '_milestone_branch', None)

        for wi in work_items:
            work_item_id = wi["work_item_id"]
            try:
                worktree_path, branch_name = create_worktree(
                    work_item_id, run_id, cwd, base_branch=base_branch
                )
                worktree_info.append((wi, worktree_path, branch_name))
                print(f"   📂 Created worktree for {work_item_id}: {worktree_path}")
            except RuntimeError as e:
                print(f"   ❌ Failed to create worktree for {work_item_id}: {e}")
                # Continue with other work items - don't let one failure stop all

        return worktree_info

    async def _merge_worktrees_serial(
        self, completed: List[Tuple[dict, str, str]]
    ) -> List[Tuple[str, str]]:
        """Merge completed worktrees to the milestone branch ONE AT A TIME.

        This serialized approach eliminates:
        - Race conditions from parallel merges
        - "git checkout" failures

        Implements milestone branch isolation by merging TO the milestone branch
        (not main). If no milestone branch is set, falls back to main.

        Args:
            completed: List of (work_item, worktree_path, branch_name) for successful executors

        Returns:
            List of (work_item_id, error_message) for failed merges
        """
        cwd = str(self.project_context.project_root)
        failed_merges = []

        # Merge to milestone branch if available, otherwise main
        target_branch = getattr(self, '_milestone_branch', None) or "main"

        for wi, worktree_path, branch_name in completed:
            work_item_id = wi["work_item_id"]
            print(f"   🔀 Merging {branch_name} to {target_branch}...")

            success, error_msg = merge_branch(branch_name, cwd, target_branch=target_branch)

            if success:
                print(f"   ✅ Merged {work_item_id} successfully")
            else:
                print(f"   ❌ Merge failed for {work_item_id}: {error_msg}")
                failed_merges.append((work_item_id, error_msg))
                # Abort the failed merge to leave target branch in a clean state
                abort_merge(cwd)

        return failed_merges

    def _cleanup_all_worktrees(self, worktree_info: List[Tuple[dict, str, str]]) -> None:
        """Cleanup ALL worktrees, guaranteed to attempt all regardless of failures.

        This method:
        - Attempts cleanup for every worktree
        - Logs failures but doesn't raise
        - Is safe to call even if some executors failed

        Args:
            worktree_info: List of (work_item, worktree_path, branch_name) tuples
        """
        cwd = str(self.project_context.project_root)

        for wi, worktree_path, branch_name in worktree_info:
            work_item_id = wi["work_item_id"]
            success = remove_worktree(worktree_path, branch_name, cwd)
            if success:
                print(f"   🧹 Cleaned up worktree for {work_item_id}")
            # Failures are already logged by remove_worktree

    def _handle_human_inputs(self, run_id: str) -> Tuple[Optional[str], List[str]]:
        """Process human inputs and return early exit status if needed.

        Returns:
            (exit_status, human_messages) - exit_status is "paused" or "aborted" if early exit
        """
        human_inputs = self.db.get_unconsumed_inputs(run_id)
        human_input_messages = []

        for human_input in human_inputs:
            if human_input.input_type == "comment":
                human_input_messages.append(human_input.content)
                self.db.mark_input_consumed(human_input.id, datetime.now())
            elif human_input.input_type == "pause":
                print("⏸️  Pausing run (human requested)")
                self.db.update_run_status(run_id, "paused", datetime.now())
                return "paused", []
            elif human_input.input_type == "abort":
                print("🛑 Aborting run (human requested)")
                self.db.update_run_status(run_id, "aborted", datetime.now())
                return "aborted", []

        return None, human_input_messages

    def _is_recoverable_error(self, error: Exception) -> bool:
        """Determine if an error is recoverable (can be retried) or fatal.

        Recoverable errors:
        - Rate limits (429, overloaded)
        - Network timeouts
        - Connection errors
        - Temporary service unavailability

        Fatal errors (require human intervention):
        - Invalid API key / authentication
        - Invalid configuration
        - Missing required files
        - Permission errors

        Args:
            error: The exception to classify

        Returns:
            True if the error is recoverable and can be retried
        """
        error_str = str(error).lower()

        # Recoverable patterns
        recoverable_patterns = [
            "rate limit",
            "429",
            "overloaded",
            "timeout",
            "connection",
            "network",
            "temporary",
            "unavailable",
            "retry",
            "503",
            "502",
            "500",
        ]

        # Fatal patterns (non-recoverable)
        fatal_patterns = [
            "api key",
            "authentication",
            "unauthorized",
            "401",
            "403",
            "permission denied",
            "file not found",
            "no such file",
            "invalid config",
        ]

        # Check for fatal patterns first
        for pattern in fatal_patterns:
            if pattern in error_str:
                return False

        # Check for recoverable patterns
        for pattern in recoverable_patterns:
            if pattern in error_str:
                return True

        # Default: assume recoverable for unknown errors
        # This is safer than defaulting to fatal, as retry is harmless
        return True

    def _build_iteration_history(self, run_id: str, current_iteration: int) -> list[dict]:
        """Build summary of previous iterations for pattern recognition.

        Args:
            run_id: The run ID
            current_iteration: Current iteration number (to exclude)

        Returns:
            List of iteration summaries with number, intent, outcome, and executor summary
        """
        iterations = self.db.list_iterations(run_id)
        history = []

        for it in iterations:
            if it.number < current_iteration:
                # Get executor summary if available
                executor_summary = None
                agent_outputs = self.db.get_agent_outputs(it.id)
                for output in agent_outputs:
                    if output.agent_type == "executor":
                        executor_summary = output.summary
                        break

                history.append({
                    "number": it.number,
                    "intent": it.intent or "N/A",
                    "outcome": it.outcome or "N/A",
                    "executor_summary": executor_summary,
                })

        return history

    async def _run_planner_with_retry(
        self, ctx: IterationContext, human_messages: List[str], max_retries: int = 3
    ) -> Tuple[Optional[dict], Optional[Exception]]:
        """Run the planner with retry for transient errors.

        Args:
            ctx: Iteration context
            human_messages: Human input messages
            max_retries: Maximum retry attempts for recoverable errors

        Returns:
            (planner_result, error) - result is None if failed, error is None if succeeded
        """
        last_error = None

        # Build iteration history for pattern recognition
        iteration_history = self._build_iteration_history(ctx.run_id, ctx.iteration_number)

        for attempt in range(max_retries):
            try:
                result = await run_planner(
                    spec_content=self.spec_content,
                    last_executor_summary=ctx.last_executor_summary,
                    last_verifier_assessment=ctx.last_verifier_assessment,
                    last_specialist_feedback=ctx.last_specialist_feedback,
                    human_inputs=human_messages if human_messages else None,
                    memory=ctx.memory,
                    project_id=self.project_context.project_id,
                    root_work_item_id=self.root_work_item_id,
                    iteration_history=iteration_history if iteration_history else None,
                )
                return result, None
            except Exception as e:
                last_error = e

                # Check if error is recoverable
                if not self._is_recoverable_error(e):
                    print(f"   ❌ Fatal planner error (non-recoverable): {e}")
                    return None, e

                # Recoverable error - retry with backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    print(f"   ⚠️  Planner attempt {attempt + 1} failed: {e}")
                    print(f"   ⏳ Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        print(f"   ❌ Planner failed after {max_retries} attempts")
        return None, last_error

    async def _run_planner_phase(self, ctx: IterationContext, human_messages: List[str]) -> Tuple[bool, Optional[str]]:
        """Run the planner phase.

        Returns:
            (success, early_exit_status) - early_exit_status is the status if run should end
        """
        # Pre-iteration health check: clean stale worktrees
        self._cleanup_abandoned_branches()

        print("🧠 Running Planner...")

        # Run planner with retry for transient errors
        planner_result, error = await self._run_planner_with_retry(ctx, human_messages)

        if error is not None:
            print(f"   ❌ Planner error: {error}")
            self.db.update_iteration(ctx.iteration_id, "STUCK", datetime.now())
            self.db.update_run_status(ctx.run_id, "stuck", datetime.now())
            self._write_summary(ctx.run_id)
            return False, "stuck"

        ctx.intent = planner_result["intent"]
        ctx.decision = planner_result["decision"]
        ctx.iteration_plan = planner_result.get("iteration_plan")
        print(f"   Decision: {ctx.decision['decision']} - {ctx.decision['reason']}")
        print(f"   Intent: {ctx.intent}\n")

        # Update iteration with intent
        self.db.update_iteration_intent(ctx.iteration_id, ctx.intent)

        # Save planner output
        planner_output_path = self._save_agent_messages(ctx.iteration_id, "planner", planner_result["messages"])
        self.db.create_agent_output(AgentOutput(
            id=None, iteration_id=ctx.iteration_id, agent_type="planner",
            raw_output_path=planner_output_path, summary=ctx.intent
        ))

        # Check if planner decided to stop
        if ctx.decision['decision'] in ('DONE', 'STUCK'):
            return self._handle_planner_termination(ctx)

        return True, None

    def _handle_planner_termination(self, ctx: IterationContext) -> Tuple[bool, str]:
        """Handle DONE or STUCK decisions from planner."""
        decision = ctx.decision['decision']
        print(f"   Planner decided {decision}, skipping executor and feedback phases")
        self.db.update_iteration(ctx.iteration_id, decision, datetime.now())

        if decision == "DONE":
            print("\n✅ Planner decided: DONE - Spec satisfied!")
            print(f"   Reason: {ctx.decision['reason']}")

            # Complete milestone: reparent remaining work and close root work item
            if self.root_work_item_id:
                try:
                    new_parent_ids = complete_milestone(
                        self.root_work_item_id,
                        str(self.project_context.project_root)
                    )
                    if new_parent_ids:
                        print(f"   📋 Milestone completed: {len(new_parent_ids)} category work items created for remaining work")
                    else:
                        print(f"   📋 Milestone completed: root work item closed")
                except Exception as e:
                    print(f"   ⚠️  Warning: Could not complete milestone: {e}")

            self.db.update_run_status(ctx.run_id, "completed", datetime.now())
            self._write_summary(ctx.run_id)
            return False, "completed"
        else:  # STUCK
            print("\n⚠️  Planner decided: STUCK - Cannot make progress")
            print(f"   Reason: {ctx.decision['reason']}")
            if ctx.decision.get('blocker'):
                print(f"   Blocker: {ctx.decision['blocker']}")
            self.db.update_run_status(ctx.run_id, "stuck", datetime.now())
            self._write_summary(ctx.run_id)
            return False, "stuck"

    async def _run_executor_phase(self, ctx: IterationContext) -> str:
        """Run the executor phase (single or parallel).

        Returns:
            Combined executor summary
        """
        if ctx.iteration_plan and ctx.iteration_plan.get("work_items"):
            return await self._run_parallel_executors(ctx)
        else:
            return await self._run_single_executor(ctx)

    async def _run_parallel_executors(self, ctx: IterationContext) -> str:
        """Run multiple executors in parallel with orchestrator-managed worktrees.

        Lifecycle:
        1. Create all worktrees BEFORE launching executors
        2. Run executors in parallel (each in its own worktree)
        3. Merge completed worktrees SERIALLY after all executors finish
        4. Cleanup ALL worktrees (guaranteed, even on failure)

        This eliminates race conditions from parallel merges and ensures
        cleanup happens even if executors fail.
        """
        work_items = ctx.iteration_plan["work_items"]
        print(f"⚙️  Running {len(work_items)} Executors in parallel...")

        # Phase 1: Create all worktrees BEFORE launching executors
        print("   📦 Creating worktrees...")
        worktree_info = self._create_worktrees(work_items, ctx.run_id)

        if not worktree_info:
            print("   ❌ No worktrees created, skipping parallel execution")
            return "No executors ran - all worktree creations failed"

        all_summaries = []
        executor_results = []

        try:
            # Phase 2: Run executors in parallel
            print("   🚀 Launching executors...")
            executor_tasks = [
                run_executor(
                    # No iteration_intent - executor reads task from Trace via work_item_id
                    spec_content=self.spec_content,
                    memory=ctx.memory,
                    work_item_id=wi["work_item_id"],
                    run_id=ctx.run_id,
                    worktree_path=wt_path,  # Orchestrator-managed worktree
                )
                for wi, wt_path, branch_name in worktree_info
            ]

            executor_results = await asyncio.gather(*executor_tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(executor_results):
                wi, wt_path, branch_name = worktree_info[i]
                work_item_id = wi["work_item_id"]

                if isinstance(result, Exception):
                    print(f"   ❌ Executor {i+1} ({work_item_id}) error: {result}")
                    result = self._create_error_executor_result(result)

                status, summary = result["status"], result["summary"]
                print(f"   Executor {i+1} ({work_item_id}) - Status: {status}")

                executor_output_path = self._save_agent_messages(
                    ctx.iteration_id, f"executor_{i+1}_{work_item_id}", result["messages"]
                )
                self.db.create_agent_output(AgentOutput(
                    id=None, iteration_id=ctx.iteration_id, agent_type=f"executor_{i+1}",
                    raw_output_path=executor_output_path, summary=summary
                ))
                all_summaries.append(f"Executor {i+1} ({work_item_id}):\n{summary}")

            # Phase 3: Merge completed worktrees SERIALLY
            # Only merge worktrees where executor completed successfully
            completed = [
                (wi, wt_path, branch)
                for (wi, wt_path, branch), result in zip(worktree_info, executor_results)
                if not isinstance(result, Exception) and result.get("status") == "Completed"
            ]

            if completed:
                print(f"   🔀 Merging {len(completed)} completed worktrees...")
                failed_merges = await self._merge_worktrees_serial(completed)
                if failed_merges:
                    for work_item_id, error_msg in failed_merges:
                        all_summaries.append(f"Merge failed for {work_item_id}: {error_msg}")
            else:
                print("   ⚠️  No completed executors to merge")

        finally:
            # Phase 4: Cleanup ALL worktrees (guaranteed)
            print("   🧹 Cleaning up worktrees...")
            self._cleanup_all_worktrees(worktree_info)

        print()
        return "\n\n".join(all_summaries)

    async def _run_single_executor(self, ctx: IterationContext) -> str:
        """Run a single executor."""
        print("⚙️  Running Executor...")
        try:
            executor_result = await run_executor(
                iteration_intent=ctx.intent, spec_content=self.spec_content, memory=ctx.memory
            )
        except Exception as e:
            print(f"   ❌ Executor error: {e}")
            executor_result = self._create_error_executor_result(e)

        status, summary = executor_result["status"], executor_result["summary"]
        print(f"   Status: {status}")
        print(f"   Summary: {summary[:200]}...\n" if len(summary) > 200 else f"   Summary: {summary}\n")

        executor_output_path = self._save_agent_messages(ctx.iteration_id, "executor", executor_result["messages"])
        self.db.create_agent_output(AgentOutput(
            id=None, iteration_id=ctx.iteration_id, agent_type="executor",
            raw_output_path=executor_output_path, summary=summary
        ))
        return summary

    def _create_error_executor_result(self, error: Exception) -> Dict[str, Any]:
        """Create a fallback executor result for errors."""
        return {
            "status": "Blocked",
            "summary": f"Status: Blocked\nWhat was done: Agent crashed with error\nBlockers: {error}\nNotes: Executor agent encountered an error and could not complete",
            "full_output": str(error),
            "messages": []
        }

    async def _run_feedback_phase(self, ctx: IterationContext) -> Tuple[str, str]:
        """Run verifier and specialists in parallel.

        Returns:
            (verifier_assessment, specialist_feedback)
        """
        print("🔍 Running Feedback Generators (Verifier + Specialists)...")

        specialists = [CodeReviewerSpecialist()]

        # Run verifier with retry for transient errors
        verifier_result = await self._run_verifier_with_retry(ctx)

        # Run specialists in parallel (no retry - less critical)
        specialist_tasks = [
            run_specialist(
                specialist=specialist,
                spec_content=self.spec_content,
                memory=ctx.memory,
                root_work_item_id=self.root_work_item_id or ""
            )
            for specialist in specialists
        ]
        specialist_results = await asyncio.gather(*specialist_tasks, return_exceptions=True)

        # Process verifier
        verifier_assessment = self._process_verifier_result(ctx, verifier_result)

        # Process specialists
        specialist_feedback = self._process_specialist_results(ctx, specialist_results, specialists)

        print()
        return verifier_assessment, specialist_feedback

    async def _run_verifier_with_retry(self, ctx: IterationContext, max_retries: int = 3) -> Any:
        """Run verifier with retry for transient errors.

        Args:
            ctx: Iteration context
            max_retries: Maximum number of retry attempts

        Returns:
            Verifier result dict or Exception if all retries failed
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await run_verifier(
                    spec_content=self.spec_content,
                    memory=ctx.memory,
                    root_work_item_id=self.root_work_item_id
                )
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    print(f"   ⚠️  Verifier attempt {attempt + 1} failed: {e}")
                    print(f"   ⏳ Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed - return the last error
        print(f"   ❌ Verifier failed after {max_retries} attempts")
        return last_error

    def _process_verifier_result(self, ctx: IterationContext, result) -> str:
        """Process verifier result and save output.

        IMPORTANT: When the verifier crashes, we use unverifiable status.
        This prevents a crashed verifier from silently passing an iteration that may have issues.
        The Planner will decide what to do based on this assessment.
        """
        if isinstance(result, Exception):
            print(f"   ❌ Verifier error: {result}")
            print(f"   ⚠️  Using unverifiable status - crashed verifier should not silently pass")
            result = {
                "spec_satisfied": "unverifiable",
                "assessment": f"Spec Satisfied: unverifiable (0/0 criteria)\nReasoning: Verifier agent crashed with error: {result}\nGaps: Unable to verify - agent error. Manual verification may be needed.",
                "full_output": str(result),
                "messages": []
            }

        spec_satisfied, assessment = result["spec_satisfied"], result["assessment"]
        print(f"   Verifier Assessment: spec_satisfied={spec_satisfied}")
        print(f"   Assessment: {assessment[:200]}...\n" if len(assessment) > 200 else f"   Assessment: {assessment}\n")

        verifier_output_path = self._save_agent_messages(ctx.iteration_id, "verifier", result["messages"])
        self.db.create_agent_output(AgentOutput(
            id=None, iteration_id=ctx.iteration_id, agent_type="verifier",
            raw_output_path=verifier_output_path, summary=assessment
        ))
        return assessment

    def _process_specialist_results(self, ctx: IterationContext, results: List, specialists: List) -> str:
        """Process specialist results, create work items, and save outputs."""
        specialist_feedback_summary = []

        for i, result in enumerate(results):
            specialist = specialists[i]
            if isinstance(result, Exception):
                print(f"   ❌ {specialist.name} error: {result}")
                result = {"specialist_name": specialist.name, "error": str(result), "feedback": [], "full_output": "", "messages": []}

            specialist_name = result["specialist_name"]
            feedback_items = result.get("feedback", [])
            print(f"   {specialist_name}: {len(feedback_items)} feedback items")

            # Create work items from feedback
            if feedback_items and self.root_work_item_id:
                try:
                    created_ids = create_work_items_from_feedback(
                        feedback_items=feedback_items, specialist_name=specialist_name,
                        root_work_item_id=self.root_work_item_id, project_root=str(self.project_context.project_root)
                    )
                    if created_ids:
                        print(f"   → Created {len(created_ids)} work items from {specialist_name} feedback")
                except Exception as e:
                    print(f"   ⚠️  Warning: Could not create work items from {specialist_name} feedback: {e}")

            # Save specialist output
            specialist_output_path = self._save_agent_messages(ctx.iteration_id, specialist_name, result.get("messages", []))
            feedback_summary = f"{specialist_name} feedback:\n"
            feedback_summary += "\n".join(f"  - {item}" for item in feedback_items) if feedback_items else "  No issues found"

            self.db.create_agent_output(AgentOutput(
                id=None, iteration_id=ctx.iteration_id, agent_type=specialist_name,
                raw_output_path=specialist_output_path, summary=feedback_summary
            ))
            specialist_feedback_summary.append(feedback_summary)

        return "\n\n".join(specialist_feedback_summary) if specialist_feedback_summary else "No specialist feedback"

    def _check_planner_decision(self, ctx: IterationContext) -> Optional[str]:
        """Check planner decision and return status if run should end."""
        planner_decision = ctx.decision['decision']

        if planner_decision == "DONE":
            print("\n✅ Planner decided: DONE - Spec satisfied!")
            print(f"   Reason: {ctx.decision['reason']}")
            self.db.update_run_status(ctx.run_id, "completed", datetime.now())
            self._write_summary(ctx.run_id)
            return "completed"

        elif planner_decision == "STUCK":
            print("\n⚠️  Planner decided: STUCK - Cannot make progress")
            print(f"   Reason: {ctx.decision['reason']}")
            if ctx.decision.get('blocker'):
                print(f"   Blocker: {ctx.decision['blocker']}")
            self.db.update_run_status(ctx.run_id, "stuck", datetime.now())
            self._write_summary(ctx.run_id)
            return "stuck"

        return None

    async def run(self, max_iterations: int = 50) -> str:
        """Run Ralph2 until completion or max iterations."""
        # Initialize or resume run
        run_id, iteration_number, last_exec, last_verify, last_spec = self._initialize_run(max_iterations)

        # Setup root work item
        setup_result = self._setup_root_work_item(run_id)
        if setup_result:
            return setup_result

        memory = read_memory(self.project_context.project_id)

        while iteration_number < max_iterations:
            iteration_number += 1
            print(f"\n{'='*60}\nIteration {iteration_number}\n{'='*60}\n")

            # Handle human inputs
            exit_status, human_messages = self._handle_human_inputs(run_id)
            if exit_status:
                return exit_status

            # Create iteration record
            iteration = self.db.create_iteration(Iteration(
                id=None, run_id=run_id, number=iteration_number,
                intent="", outcome="", started_at=datetime.now()
            ))

            # Create iteration context
            ctx = IterationContext(
                run_id=run_id, iteration_id=iteration.id, iteration_number=iteration_number,
                intent="", memory=memory, last_executor_summary=last_exec,
                last_verifier_assessment=last_verify, last_specialist_feedback=last_spec
            )

            # Run planner phase
            success, early_exit = await self._run_planner_phase(ctx, human_messages)
            if not success:
                return early_exit
            memory = read_memory(self.project_context.project_id)

            # Run executor phase
            last_exec = await self._run_executor_phase(ctx)

            # Run feedback phase
            last_verify, last_spec = await self._run_feedback_phase(ctx)
            self.db.update_iteration(ctx.iteration_id, "CONTINUE", datetime.now())

            # Check if planner wants to stop
            final_status = self._check_planner_decision(ctx)
            if final_status:
                return final_status
            print(f"   Continuing to next iteration...")

        print(f"\n⏱️  Max iterations ({max_iterations}) reached.")
        self.db.update_run_status(run_id, "max_iterations", datetime.now())
        self._write_summary(run_id)
        return "max_iterations"

    def _initialize_run(self, max_iterations: int) -> Tuple[str, int, Optional[str], Optional[str], Optional[str]]:
        """Initialize or resume a run. Returns (run_id, iteration_number, last_exec, last_verify, last_spec)."""
        existing_run = self.db.get_latest_run()

        if existing_run and existing_run.status == "running":
            return self._resume_run(existing_run, max_iterations)
        else:
            return self._create_new_run(max_iterations)

    def _resume_run(self, run: Run, max_iterations: int) -> Tuple[str, int, Optional[str], Optional[str], Optional[str]]:
        """Resume an interrupted run."""
        run.config["max_iterations"] = max_iterations
        print(f"♻️  Resuming interrupted Ralph2 run: {run.id}\n📋 Spec: {self.spec_path}")

        # Restore milestone branch from the run record and checkout
        if run.milestone_branch:
            self._milestone_branch = run.milestone_branch
            print(f"🌿 Milestone branch: {run.milestone_branch}")
            # Checkout the milestone branch so all work happens there
            cwd = str(self.project_context.project_root)
            result = subprocess.run(
                ["git", "checkout", run.milestone_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                check=False
            )
            if result.returncode != 0:
                print(f"   ⚠️  Warning: Could not checkout milestone branch: {result.stderr}")
        else:
            self._milestone_branch = None

        print(f"🧹 Cleaning up abandoned work from interruption...")
        self._cleanup_abandoned_branches()
        print()

        last_iteration = self.db.get_latest_iteration(run.id)
        iteration_number = last_iteration.number if last_iteration else 0
        print(f"   Resuming from iteration {iteration_number + 1}\n")

        last_exec, last_verify, last_spec = self._get_last_iteration_summaries(run.id, last_iteration)

        return run.id, iteration_number, last_exec, last_verify, last_spec

    def _create_new_run(self, max_iterations: int) -> Tuple[str, int, Optional[str], Optional[str], Optional[str]]:
        """Create a new run with milestone branch."""
        run_id = f"ralph2-{uuid.uuid4().hex[:8]}"

        # Generate or use explicit milestone branch
        milestone_branch = self._setup_milestone_branch()

        run = Run(
            id=run_id, spec_path=self.spec_path, spec_content=self.spec_content,
            status="running", config={"max_iterations": max_iterations}, started_at=datetime.now(),
            milestone_branch=milestone_branch
        )
        self.db.create_run(run)
        print(f"🚀 Starting Ralph2 run: {run_id}\n📋 Spec: {self.spec_path}")
        if milestone_branch:
            print(f"🌿 Milestone branch: {milestone_branch}")
        print()
        return run_id, 0, None, None, None

    def _setup_milestone_branch(self) -> Optional[str]:
        """Setup and create the milestone branch.

        Returns:
            The milestone branch name, or None if creation failed
        """
        cwd = str(self.project_context.project_root)

        # Ensure repo has at least one commit (fresh repo handling)
        if not ensure_repo_has_commits(cwd):
            print("   ⚠️  Warning: Could not ensure repo has commits")
            return None

        # Generate branch name from spec title if not explicitly provided
        if self._branch:
            branch_name = self._branch
        else:
            spec_title = _extract_spec_title(self.spec_content)
            slug = slugify_spec_title(spec_title)
            branch_name = generate_unique_branch_name(slug, cwd)

        # Create the branch if it doesn't exist
        if _create_milestone_branch(branch_name, cwd):
            self._milestone_branch = branch_name
            # Checkout the milestone branch so all work happens there
            result = subprocess.run(
                ["git", "checkout", branch_name],
                capture_output=True,
                text=True,
                cwd=cwd,
                check=False
            )
            if result.returncode != 0:
                print(f"   ⚠️  Warning: Could not checkout milestone branch {branch_name}: {result.stderr}")
            return branch_name
        else:
            print(f"   ⚠️  Warning: Could not create milestone branch {branch_name}")
            self._milestone_branch = None
            return None

    def _get_last_iteration_summaries(
        self, run_id: str, last_iteration: Optional[Any]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract summaries from the last iteration.

        Args:
            run_id: The run ID (for context, not currently used)
            last_iteration: The last iteration object, or None if no previous iteration

        Returns:
            Tuple of (executor_summary, verifier_assessment, specialist_feedback)
            All values are None if last_iteration is None.
        """
        if last_iteration is None:
            return None, None, None

        outputs = self.db.get_agent_outputs(last_iteration.id)
        last_exec, last_verify, last_spec = None, None, None

        for output in outputs:
            if output.agent_type.startswith("executor"):
                last_exec = output.summary if last_exec is None else f"{last_exec}\n\n{output.summary}"
            elif output.agent_type == "verifier":
                last_verify = output.summary
            elif "specialist" in output.agent_type.lower() or "reviewer" in output.agent_type.lower():
                last_spec = output.summary if last_spec is None else f"{last_spec}\n\n{output.summary}"

        return last_exec, last_verify, last_spec

    def _setup_root_work_item(self, run_id: str) -> Optional[str]:
        """Setup root work item. Returns early exit status if failed."""
        try:
            root_work_item_id = self._ensure_root_work_item()
            current_run = self.db.get_run(run_id)
            if current_run and not current_run.root_work_item_id:
                self.db.update_run_root_work_item(run_id, root_work_item_id)
            return None
        except RuntimeError as e:
            print(f"   ❌ Error setting up root work item: {e}")
            self.db.update_run_status(run_id, "stuck", datetime.now())
            return "stuck"

    def _write_summary(self, run_id: str):
        """Write a summary of the run to a file."""
        run = self.db.get_run(run_id)
        if not run:
            return

        iterations = self.db.list_iterations(run_id)

        summary_path = self.project_context.summaries_dir / f"summary_{run_id}.md"

        with open(summary_path, 'w') as f:
            f.write(f"# Ralph2 Run Summary\n\n")
            f.write(f"**Run ID:** {run.id}\n")
            f.write(f"**Status:** {run.status}\n")
            f.write(f"**Started:** {run.started_at.isoformat()}\n")
            if run.ended_at:
                f.write(f"**Ended:** {run.ended_at.isoformat()}\n")
                duration = run.ended_at - run.started_at
                f.write(f"**Duration:** {duration}\n")
            f.write(f"\n**Spec:** {run.spec_path}\n\n")

            f.write(f"## Iterations ({len(iterations)})\n\n")

            for iteration in iterations:
                f.write(f"### Iteration {iteration.number}\n\n")
                f.write(f"**Intent:** {iteration.intent}\n\n")
                f.write(f"**Outcome:** {iteration.outcome}\n\n")

                # Get agent outputs
                agent_outputs = self.db.get_agent_outputs(iteration.id)
                for output in agent_outputs:
                    f.write(f"**{output.agent_type.capitalize()} Summary:**\n")
                    f.write(f"```\n{output.summary}\n```\n\n")

                f.write("---\n\n")

        print(f"\n📄 Summary written to: {summary_path}")

    def close(self):
        """Close database connection."""
        self.db.close()


# Module-level wrapper for backward compatibility with existing tests
def validate_work_item_id(work_item_id: str) -> bool:
    """
    Validate that a work item ID matches expected format.

    This is a module-level wrapper around Ralph2Runner.validate_work_item_id()
    for backward compatibility.

    Args:
        work_item_id: The work item ID to validate

    Returns:
        True if valid, False otherwise
    """
    return Ralph2Runner.validate_work_item_id(work_item_id)


async def run_ralph2(spec_path: str = "Ralph2file", max_iterations: int = 50) -> str:
    """
    Run Ralph2 with the given spec.

    This is a convenience function that creates a ProjectContext automatically.
    For more control, use Ralph2Runner directly with a ProjectContext.

    Args:
        spec_path: Path to the Ralph2file
        max_iterations: Maximum number of iterations

    Returns:
        Final status
    """
    ctx = ProjectContext()
    runner = Ralph2Runner(spec_path, ctx)
    try:
        return await runner.run(max_iterations)
    finally:
        runner.close()


def main():
    """Main entry point for testing."""
    import sys

    spec_path = sys.argv[1] if len(sys.argv) > 1 else "Ralph2file"

    status = asyncio.run(run_ralph2(spec_path))
    print(f"\nFinal status: {status}")


if __name__ == "__main__":
    main()
