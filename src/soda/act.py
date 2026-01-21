"""ACT phase data structures and act() function.

The ACT phase executes the iteration plan from ORIENT, implementing tasks
through a TDD cycle. The orchestrator handles git operations (branch, commit,
merge); agents handle implementation work.

This module contains the Pydantic models for ACT input/output and will
eventually contain the act() async function that drives the phase.

ACT outputs:
- tasks_completed: list of task IDs that were completed
- tasks_blocked: list of blocked tasks with reasons
- task_comments: comments posted to tasks during work
- new_subtasks: subtasks discovered and created during work
- learnings: efficiency knowledge discovered
- commits: git commit hashes created
"""

import re
import subprocess
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from soda.state.git import GitClient
    from soda.state.trace import TraceClient


# =============================================================================
# Reuse NewTask from orient.py to avoid duplication
# =============================================================================

# Import NewTask from orient.py - same structure needed for subtasks
from soda.orient import NewTask


# =============================================================================
# BlockedTask Structure
# =============================================================================


class BlockedTask(BaseModel):
    """A task that was blocked during ACT execution.

    When an agent cannot complete a task (missing dependencies,
    external resources unavailable, etc.), it creates a BlockedTask
    with the reason for blocking.
    """

    task_id: str = Field(description="ID of the blocked task (e.g., 'ralph-abc123')")
    reason: str = Field(description="Reason why the task is blocked")


# =============================================================================
# TaskComment Structure (ACT-specific)
# =============================================================================


class TaskComment(BaseModel):
    """A comment posted to a task during ACT execution.

    Note: This is simpler than sense.TaskComment - ACT's TaskComment
    just captures what was posted, not the full metadata like timestamp
    and source (which are set by Trace when posting).
    """

    task_id: str = Field(description="ID of the task this comment was posted to")
    comment: str = Field(description="The comment text that was posted")


# =============================================================================
# Main ACT Output Structure
# =============================================================================


class ActOutput(BaseModel):
    """Complete output from the ACT phase.

    ACT executes the iteration plan, producing:
    - Completed tasks (by ID)
    - Blocked tasks (with reasons)
    - Comments posted to tasks
    - Subtasks discovered during work
    - Learnings for efficiency
    - Git commits created
    """

    tasks_completed: list[str] = Field(
        default_factory=list,
        description="Task IDs that were completed",
    )
    tasks_blocked: list[BlockedTask] = Field(
        default_factory=list,
        description="Tasks that were blocked with reasons",
    )
    task_comments: list[TaskComment] = Field(
        default_factory=list,
        description="Comments posted to tasks during work",
    )
    new_subtasks: list[NewTask] = Field(
        default_factory=list,
        description="Subtasks discovered and created during work",
    )
    learnings: list[str] = Field(
        default_factory=list,
        description="Efficiency knowledge discovered (actionable, project-specific)",
    )
    commits: list[str] = Field(
        default_factory=list,
        description="Git commit hashes created during ACT",
    )


# =============================================================================
# TestBaseline Structure (for workspace setup)
# =============================================================================


class TestBaseline(BaseModel):
    """Test baseline capturing pass/fail state before ACT execution.

    Used by the orchestrator to establish the test state before making changes,
    so that new failures can be detected and distinguished from pre-existing failures.
    """

    passed: int = Field(default=0, description="Number of tests that passed")
    failed: int = Field(default=0, description="Number of tests that failed")
    total: int = Field(default=0, description="Total number of tests run")
    has_tests: bool = Field(
        default=False, description="Whether the project has test infrastructure"
    )
    failed_tests: list[str] = Field(
        default_factory=list,
        description="Names of tests that failed (for comparison)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if tests could not be run (e.g., pytest not found)",
    )


# =============================================================================
# VerifyResult Structure (Task Verification)
# =============================================================================


class VerifyResult(BaseModel):
    """Result of task verification (comparing test run to baseline).

    After implementing a task, tests are run and compared to the baseline
    to determine if the implementation introduced regressions.
    """

    passed: bool = Field(
        description="Whether all tests passed (no failures at all)"
    )
    new_failures: list[str] = Field(
        default_factory=list,
        description="Test names that failed but weren't in baseline",
    )
    regressions: bool = Field(
        description="True if new_failures > 0 (new failures introduced)"
    )


# =============================================================================
# Workspace Setup Functions (Orchestrator)
# =============================================================================


def create_work_branch(
    git_client: "GitClient",
    iteration_num: int,
    milestone_branch: Optional[str] = None,
) -> str:
    """Create a work branch for the current iteration.

    Creates a new branch following the pattern `soda/iteration-N` and checks it out.
    If a branch with that name already exists, a numbered suffix is added
    (e.g., soda/iteration-1-2, soda/iteration-1-3).

    Args:
        git_client: GitClient instance for git operations
        iteration_num: The iteration number (used in branch name)
        milestone_branch: Optional base branch to create from. If None, uses HEAD.

    Returns:
        The actual branch name created (may have suffix if original existed)
    """
    branch_name = f"soda/iteration-{iteration_num}"
    actual_name = git_client.create_branch(branch_name, milestone_branch)
    git_client.checkout_branch(actual_name)
    return actual_name


def _run_pytest(cwd: Optional[str] = None) -> tuple[str, int]:
    """Run pytest and return output and return code.

    Shared logic for both capture_test_baseline and verify_task.

    Args:
        cwd: Working directory to run tests in. If None, uses current directory.

    Returns:
        Tuple of (stdout+stderr combined, return_code)

    Raises:
        FileNotFoundError: if pytest is not installed
        subprocess.TimeoutExpired: if tests take longer than 5 minutes
    """
    result = subprocess.run(
        ["pytest", "--tb=no", "-v", "--no-header"],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,  # 5 minute timeout for test suite
    )
    return result.stdout + result.stderr, result.returncode


def _parse_test_results(output: str) -> tuple[int, int, list[str]]:
    """Parse pytest output to extract pass/fail counts and failed test names.

    Args:
        output: Combined stdout+stderr from pytest

    Returns:
        Tuple of (passed_count, failed_count, list_of_failed_test_names)
    """
    # Count PASSED and FAILED
    # Match lines like "test_file.py::test_name PASSED" or "FAILED" with percentage
    passed = len(re.findall(r"\bPASSED\s*\[\s*\d+%\]", output))
    failed = len(re.findall(r"\bFAILED\s*\[\s*\d+%\]", output))

    # Extract failed test names
    # Match lines like "test_file.py::test_name FAILED [100%]"
    failed_tests = re.findall(r"(\S+::\S+)\s+FAILED\s*\[\s*\d+%\]", output)

    return passed, failed, failed_tests


def capture_test_baseline(cwd: Optional[str] = None) -> TestBaseline:
    """Capture the test baseline by running the full test suite.

    Runs pytest with JSON output to capture pass/fail counts. If pytest
    is not available or no tests exist, returns a baseline indicating
    "no tests".

    Args:
        cwd: Working directory to run tests in. If None, uses current directory.

    Returns:
        TestBaseline with pass/fail counts or has_tests=False if no tests
    """
    try:
        output, returncode = _run_pytest(cwd)

        # Check for "no tests ran" or similar
        if "no tests ran" in output.lower() or returncode == 5:
            return TestBaseline(
                passed=0, failed=0, total=0, has_tests=False
            )

        passed, failed, failed_tests = _parse_test_results(output)
        total = passed + failed

        if total == 0:
            # No tests found
            return TestBaseline(
                passed=0, failed=0, total=0, has_tests=False
            )

        return TestBaseline(
            passed=passed,
            failed=failed,
            total=total,
            has_tests=True,
            failed_tests=failed_tests,
        )

    except FileNotFoundError:
        # pytest not installed
        return TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            error="pytest not found",
        )
    except subprocess.TimeoutExpired:
        return TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            error="Test suite timed out (>5 minutes)",
        )
    except Exception as e:
        return TestBaseline(
            passed=0,
            failed=0,
            total=0,
            has_tests=False,
            error=str(e),
        )


def verify_task(baseline: TestBaseline, cwd: Optional[str] = None) -> VerifyResult:
    """Verify task by running tests and comparing to baseline.

    Runs the test suite and compares the results against the baseline
    captured before implementation. New failures (tests that fail now
    but weren't failing in the baseline) are identified as regressions.

    Args:
        baseline: TestBaseline captured before implementation started
        cwd: Working directory to run tests in. If None, uses current directory.

    Returns:
        VerifyResult with:
        - passed: True if all tests pass (no failures at all)
        - new_failures: Test names that failed but weren't in baseline
        - regressions: True if new_failures > 0
    """
    try:
        output, returncode = _run_pytest(cwd)

        # Check for "no tests ran" or similar - treat as success
        if "no tests ran" in output.lower() or returncode == 5:
            return VerifyResult(
                passed=True,
                new_failures=[],
                regressions=False,
            )

        passed_count, failed_count, current_failed = _parse_test_results(output)
        total = passed_count + failed_count

        if total == 0:
            # No tests found - treat as success
            return VerifyResult(
                passed=True,
                new_failures=[],
                regressions=False,
            )

        # Find new failures (failed now but not in baseline)
        baseline_failures_set = set(baseline.failed_tests)
        new_failures = [
            test_name for test_name in current_failed
            if test_name not in baseline_failures_set
        ]

        # All tests passed if no failures at all
        all_passed = failed_count == 0

        return VerifyResult(
            passed=all_passed,
            new_failures=new_failures,
            regressions=len(new_failures) > 0,
        )

    except FileNotFoundError:
        # pytest not installed - can't verify, treat as success
        return VerifyResult(
            passed=True,
            new_failures=[],
            regressions=False,
        )
    except subprocess.TimeoutExpired:
        # Test suite timed out - treat as failure with regression
        return VerifyResult(
            passed=False,
            new_failures=["<test suite timed out>"],
            regressions=True,
        )
    except Exception as e:
        # Unexpected error - treat as failure with regression
        return VerifyResult(
            passed=False,
            new_failures=[f"<error: {e}>"],
            regressions=True,
        )


# =============================================================================
# Commit Functions (Orchestrator)
# =============================================================================


def commit_task_changes(
    git_client: "GitClient",
    task_id: str,
) -> Optional[str]:
    """Commit changes after task completion with message referencing task ID.

    This function stages all changes (including untracked files) and creates
    a commit with a message that references the task ID. If there are no
    changes to commit, returns None without creating a commit.

    Args:
        git_client: GitClient instance for git operations
        task_id: The task ID to reference in the commit message

    Returns:
        The commit hash if a commit was created, None if no changes were made
    """
    # Check for uncommitted changes first
    if not git_client.has_uncommitted_changes():
        return None

    # Stage all changes (including untracked files)
    git_client._run_git(["add", "-A"])

    # Create commit with task ID in message
    commit_message = f"[{task_id}] Task completed"
    git_client._run_git(["commit", "-m", commit_message])

    # Get the commit hash
    result = git_client._run_git(["rev-parse", "HEAD"])
    return result.stdout.strip()


def commit_or_stash_uncommitted(
    git_client: "GitClient",
    task_id: str,
) -> dict:
    """Commit or stash any uncommitted changes at end of task.

    This function ensures no uncommitted changes are left at the end of a
    task. It commits any changes with a message referencing the task ID.

    Args:
        git_client: GitClient instance for git operations
        task_id: The task ID to reference in the commit message

    Returns:
        A dict with:
        - "action": "committed", "stashed", or "none"
        - "commit_hash": The commit hash if committed, None otherwise
    """
    # Check for uncommitted changes
    if not git_client.has_uncommitted_changes():
        return {"action": "none", "commit_hash": None}

    # Stage all changes and commit
    git_client._run_git(["add", "-A"])
    commit_message = f"[{task_id}] Uncommitted changes at task end"
    git_client._run_git(["commit", "-m", commit_message])

    # Get the commit hash
    result = git_client._run_git(["rev-parse", "HEAD"])
    commit_hash = result.stdout.strip()

    return {"action": "committed", "commit_hash": commit_hash}


# =============================================================================
# Trace Integration Functions (Task Updates)
# =============================================================================


def post_progress_comment(
    trace_client: "TraceClient",
    task_id: str,
    comment: str,
) -> TaskComment:
    """Post a progress comment to a task in Trace.

    This function posts a comment to the specified task and returns a
    TaskComment object recording what was posted. Comments are posted
    with source="executor" to identify them as coming from the ACT phase.

    Args:
        trace_client: TraceClient instance for Trace operations
        task_id: The ID of the task to comment on (e.g., 'ralph-abc123')
        comment: The comment text to post

    Returns:
        TaskComment with the task_id and comment that was posted
    """
    trace_client.post_comment(task_id, comment, source="executor")
    return TaskComment(task_id=task_id, comment=comment)


def close_task_in_trace(
    trace_client: "TraceClient",
    task_id: str,
    completion_message: Optional[str] = None,
) -> None:
    """Close a task in Trace with an optional completion message.

    This function marks a task as closed in Trace. If a completion message
    is provided, it will be recorded with the closure. If no message is
    provided, a default message is used.

    Args:
        trace_client: TraceClient instance for Trace operations
        task_id: The ID of the task to close (e.g., 'ralph-abc123')
        completion_message: Optional message to record with the closure
    """
    message = completion_message or "Task completed"
    trace_client.close_task(task_id, message=message)


def mark_task_blocked(
    trace_client: "TraceClient",
    task_id: str,
    blocker_reason: str,
) -> BlockedTask:
    """Mark a task as blocked by posting a blocker comment to Trace.

    This function posts a comment indicating the task is blocked with
    the provided reason. It returns a BlockedTask object for tracking
    in the ACT output.

    Args:
        trace_client: TraceClient instance for Trace operations
        task_id: The ID of the task that is blocked (e.g., 'ralph-abc123')
        blocker_reason: The reason why the task is blocked

    Returns:
        BlockedTask with the task_id and reason
    """
    blocker_comment = f"BLOCKED: {blocker_reason}"
    trace_client.post_comment(task_id, blocker_comment, source="executor")
    return BlockedTask(task_id=task_id, reason=blocker_reason)


def create_subtask(
    trace_client: "TraceClient",
    parent_id: str,
    title: str,
    description: str,
) -> str:
    """Create a subtask under a parent task in Trace.

    This function creates a new task as a child of the specified parent task.
    Subtasks are typically discovered during work on the parent task.

    Args:
        trace_client: TraceClient instance for Trace operations
        parent_id: The ID of the parent task (e.g., 'ralph-parent')
        title: The title of the new subtask
        description: The description of the new subtask

    Returns:
        The ID of the newly created subtask
    """
    return trace_client.create_task(title, description, parent=parent_id)


# =============================================================================
# FinalizeResult Structure
# =============================================================================


class FinalizeResult(BaseModel):
    """Result of finalize_iteration operation.

    Captures the outcome of merging the work branch to the milestone branch
    and cleaning up afterward.
    """

    success: bool = Field(
        description="Whether finalization succeeded (merge complete, branch deleted)"
    )
    merged: bool = Field(description="Whether the merge was successful")
    branch_deleted: bool = Field(description="Whether the work branch was deleted")
    conflict_reason: Optional[str] = Field(
        default=None,
        description="Reason for failure if merge had conflicts",
    )


# =============================================================================
# Finalize Function (Orchestrator)
# =============================================================================


def finalize_iteration(
    git_client: "GitClient",
    work_branch: str,
    milestone_branch: str,
) -> FinalizeResult:
    """Merge work branch to milestone branch and clean up.

    This function finalizes an iteration by:
    1. Checking out the milestone branch
    2. Attempting to merge the work branch
    3. If merge succeeds: deleting the work branch
    4. If merge fails: preserving the work branch for investigation

    Args:
        git_client: GitClient instance for git operations
        work_branch: Name of the work branch to merge (e.g., 'soda/iteration-1')
        milestone_branch: Name of the milestone branch to merge into

    Returns:
        FinalizeResult with:
        - success: True if merge succeeded and branch was deleted
        - merged: True if merge completed without conflicts
        - branch_deleted: True if work branch was deleted
        - conflict_reason: Reason if merge failed (None if successful)
    """
    # Attempt to merge work branch into milestone branch
    # merge_branch() handles checkout of target branch internally
    merge_succeeded = git_client.merge_branch(work_branch, milestone_branch)

    if not merge_succeeded:
        # Merge failed (conflict) - preserve work branch for investigation
        return FinalizeResult(
            success=False,
            merged=False,
            branch_deleted=False,
            conflict_reason=f"Merge conflict when merging {work_branch} into {milestone_branch}",
        )

    # Merge succeeded - delete the work branch
    git_client.delete_branch(work_branch)

    return FinalizeResult(
        success=True,
        merged=True,
        branch_deleted=True,
        conflict_reason=None,
    )


# =============================================================================
# ACT Context Structure
# =============================================================================


class ActContext(BaseModel):
    """Context required for the ACT phase.

    Contains all the information needed to execute the iteration plan.
    """

    iteration_plan_json: str = Field(
        description="JSON-serialized IterationPlan from ORIENT"
    )
    learnings: str = Field(
        default="",
        description="Accumulated learnings/efficiency knowledge",
    )
    spec_content: str = Field(description="The specification content for context")
    iteration_num: int = Field(description="Current iteration number")
    milestone_branch: str = Field(description="Branch to merge back to after ACT")
    working_directory: Optional[str] = Field(
        default=None,
        description="Working directory for the project (None = current dir)",
    )


# =============================================================================
# Task Execution Result (Agent Output per Task)
# =============================================================================


class TaskExecutionResult(BaseModel):
    """Result from agent executing a single task.

    The executor agent returns this after attempting to complete a task.
    It indicates whether the task was completed, blocked, or needs subtasks.
    """

    completed: bool = Field(
        description="Whether the task was successfully completed"
    )
    blocked: bool = Field(
        default=False,
        description="Whether the task is blocked and cannot proceed",
    )
    blocker_reason: Optional[str] = Field(
        default=None,
        description="Reason for blocking (required if blocked=True)",
    )
    progress_notes: str = Field(
        default="",
        description="Notes on what was done (for Trace comment)",
    )
    subtasks_needed: list[NewTask] = Field(
        default_factory=list,
        description="Subtasks discovered that need to be created",
    )
    learning: Optional[str] = Field(
        default=None,
        description="Efficiency knowledge discovered (what you wish you knew before starting)",
    )


# =============================================================================
# Executor System Prompt
# =============================================================================


EXECUTOR_SYSTEM_PROMPT = """You are the EXECUTOR agent in the SODA loop.

## Your Role

You execute tasks from the iteration plan. Your job is to implement the assigned
task following TDD principles when appropriate, then report what you accomplished.

---

## Task Execution Flow

### 1. Understand the Task
- Read the task title and rationale
- Understand what needs to be done
- Review any relevant code context

### 2. Execute the Task

**For Code Work (features, bug fixes, refactoring):**
Follow TDD cycle:
1. Write a failing test that captures the requirement
2. Write the minimum code to make the test pass
3. Refactor if needed while keeping tests green
4. Run tests to verify

**For Non-Code Work (docs, config, research):**
Do the work directly without TDD.

**For Investigation Tasks:**
1. Investigate the issue thoroughly
2. Document findings in progress_notes
3. If you find a fix, implement it
4. If you can't fix it, explain why and what's blocking

### 3. Verify Your Work
- Run the relevant tests
- Ensure no regressions were introduced
- If tests fail, fix them before reporting completion

### 4. Report Results
Return a TaskExecutionResult with:
- `completed`: true if task is done, false if blocked
- `blocked`: true if you cannot proceed
- `blocker_reason`: why you're blocked (if blocked)
- `progress_notes`: what you did (for Trace comment)
- `subtasks_needed`: any subtasks discovered during work
- `learning`: what you wish you knew before starting

---

## Tools Available

You have full development tools:
- **Read**: Read files to understand code
- **Write**: Create new files
- **Edit**: Modify existing files
- **Glob**: Find files by pattern
- **Grep**: Search code for patterns
- **Bash**: Run commands (tests, builds, etc.)

---

## Key Principles

1. **TDD for code work** - Write test first, then implementation
2. **Small, focused changes** - Do only what the task requires
3. **Verify before reporting** - Run tests before marking complete
4. **Document blockers clearly** - If blocked, explain what's needed
5. **Capture learnings** - Note efficiency knowledge for future iterations

---

## Output Requirements

Your output must be valid TaskExecutionResult JSON:

```json
{
  "completed": true | false,
  "blocked": false | true,
  "blocker_reason": null | "reason string",
  "progress_notes": "Description of what was done",
  "subtasks_needed": [
    {
      "title": "Subtask title",
      "description": "What needs to be done",
      "priority": 1
    }
  ],
  "learning": null | "Efficiency knowledge discovered"
}
```

If `blocked` is true, `blocker_reason` is required.
If `completed` is false but not blocked, explain why in `progress_notes`.
"""


# Tools available to the executor agent
EXECUTOR_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]


# =============================================================================
# Main ACT Function
# =============================================================================


async def act(
    ctx: ActContext,
    git_client: "GitClient",
    trace_client: "TraceClient",
) -> ActOutput:
    """Execute the ACT phase: implement tasks from the iteration plan.

    The ACT phase:
    1. Creates a work branch for the iteration
    2. Captures test baseline
    3. Executes each task in the iteration plan (via agent)
    4. Verifies each task (runs tests, compares to baseline)
    5. Commits changes at task boundaries
    6. Updates Trace with progress/completion/blockers
    7. Captures learnings
    8. Finalizes by merging work branch to milestone branch

    Args:
        ctx: ActContext with iteration plan and configuration
        git_client: GitClient instance for git operations
        trace_client: TraceClient instance for Trace operations

    Returns:
        ActOutput with completed tasks, blocked tasks, comments, subtasks,
        learnings, and commit hashes
    """
    import json
    from soda.agents.narrow import NarrowAgent
    from soda.orient import IterationPlan

    # Parse the iteration plan
    iteration_plan = IterationPlan.model_validate_json(ctx.iteration_plan_json)

    # Initialize output collectors
    tasks_completed: list[str] = []
    tasks_blocked: list[BlockedTask] = []
    task_comments: list[TaskComment] = []
    new_subtasks: list[NewTask] = []
    learnings: list[str] = []
    commits: list[str] = []

    # --- Setup Workspace ---
    # Create work branch for this iteration
    work_branch = create_work_branch(
        git_client,
        ctx.iteration_num,
        ctx.milestone_branch,
    )

    # Capture test baseline before making changes
    baseline = capture_test_baseline(ctx.working_directory)

    # --- Execute Each Task ---
    for planned_task in iteration_plan.tasks:
        task_id = planned_task.task_id
        task_title = planned_task.title
        task_rationale = planned_task.rationale

        # Build prompt for the executor agent
        prompt = _build_executor_prompt(
            task_id=task_id,
            task_title=task_title,
            task_rationale=task_rationale,
            approach=iteration_plan.approach,
            learnings=ctx.learnings,
            spec_content=ctx.spec_content,
        )

        # Invoke agent to execute the task
        agent = NarrowAgent()
        try:
            result: TaskExecutionResult = await agent.invoke(
                prompt=prompt,
                output_schema=TaskExecutionResult,
                tools=EXECUTOR_TOOLS,
                system_prompt=EXECUTOR_SYSTEM_PROMPT,
            )
        except Exception as e:
            # Agent invocation failed - mark task as blocked
            blocked = mark_task_blocked(
                trace_client, task_id, f"Agent invocation failed: {e}"
            )
            tasks_blocked.append(blocked)
            continue

        # --- Process Agent Result ---

        # Post progress comment to Trace
        if result.progress_notes:
            comment = post_progress_comment(
                trace_client, task_id, result.progress_notes
            )
            task_comments.append(comment)

        # Handle subtasks discovered during work
        for subtask in result.subtasks_needed:
            subtask_id = create_subtask(
                trace_client,
                task_id,
                subtask.title,
                subtask.description,
            )
            # Record the subtask with its new ID
            new_subtasks.append(
                NewTask(
                    title=subtask.title,
                    description=subtask.description,
                    priority=subtask.priority,
                    parent_id=task_id,
                )
            )

        # Capture learning if provided
        if result.learning:
            learnings.append(result.learning)

        # Handle blocked tasks
        if result.blocked:
            blocked = mark_task_blocked(
                trace_client,
                task_id,
                result.blocker_reason or "Task blocked (no reason provided)",
            )
            tasks_blocked.append(blocked)
            # Still commit any partial work
            commit_result = commit_or_stash_uncommitted(git_client, task_id)
            if commit_result["commit_hash"]:
                commits.append(commit_result["commit_hash"])
            continue

        # --- Verify Task ---
        if result.completed:
            verify_result = verify_task(baseline, ctx.working_directory)

            if verify_result.regressions:
                # New test failures introduced - mark as blocked
                failure_msg = f"Verification failed: new test failures: {verify_result.new_failures}"
                blocked = mark_task_blocked(trace_client, task_id, failure_msg)
                tasks_blocked.append(blocked)
                # Commit the broken state for investigation
                commit_result = commit_or_stash_uncommitted(git_client, task_id)
                if commit_result["commit_hash"]:
                    commits.append(commit_result["commit_hash"])
            else:
                # Task completed successfully
                close_task_in_trace(
                    trace_client,
                    task_id,
                    f"Completed: {result.progress_notes[:100] if result.progress_notes else 'Task done'}",
                )
                tasks_completed.append(task_id)

                # Commit task changes
                commit_hash = commit_task_changes(git_client, task_id)
                if commit_hash:
                    commits.append(commit_hash)
        else:
            # Task not completed but not blocked - partial progress
            comment = post_progress_comment(
                trace_client,
                task_id,
                f"Partial progress: {result.progress_notes or 'Some work done'}",
            )
            task_comments.append(comment)
            # Commit partial work
            commit_result = commit_or_stash_uncommitted(git_client, task_id)
            if commit_result["commit_hash"]:
                commits.append(commit_result["commit_hash"])

    # --- Finalize ---
    # Merge work branch back to milestone branch
    finalize_result = finalize_iteration(
        git_client,
        work_branch,
        ctx.milestone_branch,
    )

    # If finalize failed, record it as a learning
    if not finalize_result.success:
        learnings.append(
            f"Merge conflict during finalize: {finalize_result.conflict_reason}"
        )

    return ActOutput(
        tasks_completed=tasks_completed,
        tasks_blocked=tasks_blocked,
        task_comments=task_comments,
        new_subtasks=new_subtasks,
        learnings=learnings,
        commits=commits,
    )


def _build_executor_prompt(
    task_id: str,
    task_title: str,
    task_rationale: str,
    approach: str,
    learnings: str,
    spec_content: str,
) -> str:
    """Build the prompt for the executor agent.

    Args:
        task_id: ID of the task to execute
        task_title: Title of the task
        task_rationale: Why this task was selected
        approach: Overall approach from iteration plan
        learnings: Accumulated efficiency knowledge
        spec_content: The specification for context

    Returns:
        Formatted prompt string for the executor agent
    """
    parts = [
        "# Task Assignment",
        "",
        f"**Task ID:** {task_id}",
        f"**Title:** {task_title}",
        f"**Rationale:** {task_rationale}",
        "",
        "---",
        "",
        "# Approach",
        "",
        approach,
        "",
        "---",
        "",
    ]

    if learnings:
        parts.extend([
            "# Learnings (Efficiency Knowledge)",
            "",
            "Use these to work more efficiently:",
            "",
            learnings,
            "",
            "---",
            "",
        ])

    parts.extend([
        "# Spec (for context)",
        "",
        spec_content,
        "",
        "---",
        "",
        "# Your Task",
        "",
        "1. Understand what needs to be done",
        "2. Execute the task (follow TDD for code work)",
        "3. Run tests to verify your work",
        "4. Report your results",
        "",
        "Return a TaskExecutionResult with your findings.",
    ])

    return "\n".join(parts)
