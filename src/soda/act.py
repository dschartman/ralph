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
    error: Optional[str] = Field(
        default=None,
        description="Error message if tests could not be run (e.g., pytest not found)",
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
        # Run pytest with JSON-like output to capture results
        # We use --tb=no to minimize output and -q for quiet mode
        # -v gives us test names which we can count
        result = subprocess.run(
            ["pytest", "--tb=no", "-v", "--no-header"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300,  # 5 minute timeout for test suite
        )

        # Parse output to count passed/failed tests
        # pytest -v output format: "test_file.py::test_name PASSED" or "FAILED"
        stdout = result.stdout + result.stderr

        # Check for "no tests ran" or similar
        if "no tests ran" in stdout.lower() or result.returncode == 5:
            return TestBaseline(
                passed=0, failed=0, total=0, has_tests=False
            )

        # Count PASSED and FAILED
        # Match lines like "test_file.py::test_name PASSED" or "FAILED" with percentage
        # The regex looks for PASSED/FAILED followed by optional percentage bracket
        passed = len(re.findall(r"\bPASSED\s*\[\s*\d+%\]", stdout))
        failed = len(re.findall(r"\bFAILED\s*\[\s*\d+%\]", stdout))
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
