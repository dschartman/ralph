"""SODA Runner: Main iteration loop orchestrator.

The runner orchestrates the SODA loop: SENSE → ORIENT → DECIDE → ACT.
It handles iteration control, routing based on DECIDE outcomes, and
tracks state across iterations.

This module contains:
- RunContext: Configuration for a SODA run
- IterationResult: Output from a single iteration
- RunResult: Final result from the full loop
- BootstrapResult: Result from project initialization
- MilestoneContext: Result from milestone setup
- bootstrap(): Initialize project for SODA run
- setup_milestone(): Create milestone branch and root work item
- run_iteration(): Execute a single SENSE → ORIENT → DECIDE → (ACT) cycle
- run_loop(): Execute iterations until DONE, STUCK, or max iterations
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from soda.act import ActContext, ActOutput, BlockedTask, act
from soda.decide import Decision, DecisionOutcome, decide
from soda.orient import OrientContext, OrientOutput, orient
from soda.project import (
    ensure_soda_id_in_gitignore,
    find_git_root,
    get_project_db_path,
    get_project_id,
    get_project_state_dir,
    get_project_summaries_dir,
    read_memory,
)
from soda.sense import Claims, SenseContext, sense
from soda.state.db import SodaDB
from soda.state.git import GitClient, GitError
from soda.state.models import IterationOutcome, RunStatus
from soda.state.trace import TraceClient

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================


class BootstrapResult(BaseModel):
    """Result from bootstrapping a project for SODA run.

    Contains all the information needed to start a SODA run, including
    project identification and initial state detection.
    """

    project_id: str = Field(description="Project UUID for state storage")
    spec_content: str = Field(description="The specification content to satisfy")
    is_new_project: bool = Field(
        description="True if .soda-id was just created (first run)"
    )
    is_kickstart: bool = Field(
        description="True if project has no code structure and needs scaffolding"
    )


class MilestoneContext(BaseModel):
    """Result from setting up a milestone for a SODA run.

    Contains the branch name and root work item ID needed to track
    work for this milestone.
    """

    milestone_branch: str = Field(description="Branch where work accumulates")
    root_work_item_id: str = Field(description="Root work item ID in Trace")
    is_resumed: bool = Field(
        default=False,
        description="True if reusing existing branch/work item from a previous run",
    )


class RunContext(BaseModel):
    """Configuration and context for a SODA run.

    Contains all the identifiers and settings needed to run the SODA loop.
    """

    project_id: str = Field(description="Project UUID for state storage")
    spec_content: str = Field(description="The specification content to satisfy")
    milestone_branch: str = Field(description="Branch where work accumulates")
    root_work_item_id: Optional[str] = Field(
        default=None,
        description="Root work item ID in Trace (None if not using Trace)",
    )
    max_iterations: int = Field(
        default=20,
        ge=1,
        description="Maximum iterations before halting (default: 20)",
    )
    working_directory: Optional[str] = Field(
        default=None,
        description="Working directory for the project (None = current dir)",
    )
    run_id: str = Field(description="Current run ID for state tracking")
    milestone_base: Optional[str] = Field(
        default=None,
        description="Git ref for milestone base (None if new project)",
    )


class IterationResult(BaseModel):
    """Result from a single iteration.

    Contains the iteration number, the decision outcome, and outputs
    from ORIENT and optionally ACT.
    """

    iteration_num: int = Field(description="The iteration number (1-indexed)")
    outcome: DecisionOutcome = Field(
        description="Decision outcome: DONE, STUCK, or CONTINUE"
    )
    orient_output: OrientOutput = Field(description="Output from ORIENT phase")
    decision: Decision = Field(description="The routing decision from DECIDE")
    act_output: Optional[ActOutput] = Field(
        default=None,
        description="Output from ACT phase (only if outcome was CONTINUE)",
    )


class RunResult(BaseModel):
    """Final result from the SODA run loop.

    Indicates how the run terminated and provides summary information.
    """

    status: str = Field(
        description="Termination status: 'done', 'stuck', or 'max_iterations'"
    )
    iterations_completed: int = Field(
        description="Total number of iterations completed"
    )
    final_outcome: str = Field(
        description="The final outcome (DONE reason, STUCK reason, etc.)"
    )
    summary: str = Field(description="Human-readable summary of the run")


# =============================================================================
# Bootstrap Phase
# =============================================================================


class BootstrapError(Exception):
    """Error raised during bootstrap when project cannot be initialized."""

    pass


def _detect_kickstart(project_root: Path) -> bool:
    """Detect if project needs scaffolding (no existing code structure).

    A project is considered a kickstart if it has:
    - No package manager manifest (pyproject.toml, package.json, Cargo.toml)
    - No src/ directory

    Args:
        project_root: Path to the project root

    Returns:
        True if project needs scaffolding, False if it has existing structure
    """
    # Check for package manager manifests
    manifests = ["pyproject.toml", "package.json", "Cargo.toml"]
    has_manifest = any((project_root / m).exists() for m in manifests)

    # Check for src directory
    has_src = (project_root / "src").is_dir()

    # Kickstart if no manifest AND no src
    return not has_manifest and not has_src


def _ensure_git_has_commits(git_client: GitClient, project_root: Path) -> bool:
    """Ensure git repo has at least one commit.

    If the repo has no commits, creates an initial empty commit.
    This is needed for git operations like diff and branch creation.

    Args:
        git_client: GitClient for git operations
        project_root: Path to the project root

    Returns:
        True if an initial commit was created, False if commits already existed
    """
    try:
        # Try to get HEAD - this fails if no commits exist
        git_client._run_git(["rev-parse", "HEAD"])
        return False  # Commits exist
    except GitError:
        # No commits - create initial empty commit
        logger.info("Creating initial empty commit")
        git_client._run_git(["commit", "--allow-empty", "-m", "Initial commit"])
        return True


async def bootstrap(
    working_dir: str,
    spec_path: str,
) -> BootstrapResult:
    """Initialize project for SODA run.

    This function handles first-time project setup:
    1. Validates git repository exists
    2. Validates spec file exists and is readable
    3. Creates .soda-id if not exists
    4. Creates state directory ~/.soda/projects/<project-id>/
    5. Initializes database
    6. Creates initial commit if repo has no commits
    7. Detects if project needs scaffolding (kickstart)

    Args:
        working_dir: Working directory for the project
        spec_path: Path to the specification file (Sodafile)

    Returns:
        BootstrapResult with project_id, spec_content, is_new_project, is_kickstart

    Raises:
        BootstrapError: If validation fails (no git repo, no spec file, etc.)
    """
    project_root = Path(working_dir).resolve()

    # --- Validate git repository exists ---
    git_root = find_git_root(project_root)
    if git_root is None:
        raise BootstrapError(
            f"Not a git repository: {project_root}\n"
            "SODA requires a git repository. Run 'git init' first."
        )

    # --- Validate spec file exists and is readable ---
    spec_file = Path(spec_path)
    if not spec_file.is_absolute():
        spec_file = project_root / spec_file

    if not spec_file.exists():
        raise BootstrapError(
            f"Spec file not found: {spec_file}\n"
            "Create a Sodafile in the project root."
        )

    try:
        spec_content = spec_file.read_text()
    except (OSError, IOError) as e:
        raise BootstrapError(f"Cannot read spec file: {spec_file}\n{e}") from e

    if not spec_content.strip():
        raise BootstrapError(f"Spec file is empty: {spec_file}")

    # --- Get or create project ID ---
    soda_id_path = project_root / ".soda-id"
    is_new_project = not soda_id_path.exists()

    project_id = get_project_id(project_root)
    logger.info(f"Project ID: {project_id} (new={is_new_project})")

    # --- Ensure .soda-id is gitignored ---
    if ensure_soda_id_in_gitignore(project_root):
        logger.debug("Added .soda-id to .gitignore")

    # --- Create state directory ---
    state_dir = get_project_state_dir(project_id)
    logger.debug(f"State directory: {state_dir}")

    # --- Initialize database ---
    db_path = get_project_db_path(project_id)
    db = SodaDB(str(db_path))
    db.close()
    logger.debug(f"Database initialized: {db_path}")

    # --- Ensure git has commits ---
    git_client = GitClient(cwd=str(project_root))
    _ensure_git_has_commits(git_client, project_root)

    # --- Verify git is in clean state ---
    if git_client.has_uncommitted_changes():
        logger.warning(
            "Git repository has uncommitted changes. "
            "Consider committing or stashing before running SODA."
        )

    # --- Detect kickstart ---
    is_kickstart = _detect_kickstart(project_root)
    if is_kickstart:
        logger.info("Kickstart detected: project has no code structure")

    return BootstrapResult(
        project_id=project_id,
        spec_content=spec_content,
        is_new_project=is_new_project,
        is_kickstart=is_kickstart,
    )


# =============================================================================
# Milestone Phase
# =============================================================================


class MilestoneError(Exception):
    """Error raised during milestone setup."""

    pass


def extract_spec_title(spec_content: str) -> str:
    """Extract the title from a spec's first H1 heading.

    Looks for the first line starting with "# " and extracts the title.
    Falls back to "SODA Work Item" if no H1 heading is found.

    Args:
        spec_content: The spec file content

    Returns:
        The extracted title or default fallback
    """
    match = re.search(r"^#\s+(.+)$", spec_content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "SODA Work Item"


async def setup_milestone(
    project_id: str,
    spec_content: str,
    git_client: GitClient,
    trace_client: TraceClient,
    db: SodaDB,
    run_id: Optional[str] = None,
) -> MilestoneContext:
    """Setup milestone context for a SODA run.

    This function works in place on the current branch:
    1. Records the current branch name (no branch creation/switching)
    2. Creates a root work item in Trace (or reuses existing one on resume)

    On resume (when run_id is provided), it will:
    - Reuse the existing root work item from the run

    Args:
        project_id: Project UUID for state storage
        spec_content: The specification content
        git_client: GitClient for git operations
        trace_client: TraceClient for Trace operations
        db: SodaDB for state persistence
        run_id: Optional run ID for resume (reuses existing work item)

    Returns:
        MilestoneContext with current branch name, work item ID, and resume status

    Raises:
        MilestoneError: If milestone setup fails
    """
    is_resumed = False
    root_work_item_id: Optional[str] = None

    # --- Get current branch (work in place, no branch switching) ---
    try:
        current_branch = git_client.get_current_branch()
        logger.info(f"Working on branch: {current_branch}")
    except GitError as e:
        raise MilestoneError(f"Failed to get current branch: {e}") from e

    # --- Handle resume case ---
    if run_id is not None:
        existing_run = db.get_run(run_id)
        if existing_run is not None:
            root_work_item_id = existing_run.root_work_item_id
            if root_work_item_id:
                logger.info(
                    f"Resuming run: work_item={root_work_item_id}"
                )
                is_resumed = True

    # --- Create root work item if needed ---
    if root_work_item_id is None:
        title = extract_spec_title(spec_content)
        # Create a summary from first few lines of spec
        spec_lines = spec_content.strip().split("\n")
        summary = "\n".join(spec_lines[:10])
        if len(spec_lines) > 10:
            summary += "\n..."

        try:
            root_work_item_id = trace_client.create_task(
                title=title,
                description=summary,
            )
            logger.info(f"Created root work item: {root_work_item_id}")
        except Exception as e:
            # Trace errors shouldn't fail the whole milestone setup
            # Log warning and continue without a root work item
            logger.warning(f"Failed to create root work item in Trace: {e}")
            root_work_item_id = ""  # Empty string to indicate no work item

    return MilestoneContext(
        milestone_branch=current_branch,
        root_work_item_id=root_work_item_id,
        is_resumed=is_resumed,
    )


# =============================================================================
# Iteration Execution
# =============================================================================


async def run_iteration(
    ctx: RunContext,
    iteration_num: int,
    git_client: GitClient,
    trace_client: TraceClient,
    db: SodaDB,
    quiet: bool = False,
) -> IterationResult:
    """Execute a single iteration of the SODA loop.

    Runs SENSE → ORIENT → DECIDE, and if DECIDE returns CONTINUE, runs ACT.
    Does NOT loop - returns after one iteration cycle.

    Args:
        ctx: RunContext with run configuration
        iteration_num: Current iteration number (1-indexed)
        git_client: GitClient for git operations
        trace_client: TraceClient for Trace operations
        db: SodaDB for state persistence
        quiet: If True, suppress streaming output (default: False, always stream)

    Returns:
        IterationResult with the iteration outcome and phase outputs
    """
    # Create streaming callback (always on unless quiet mode)
    streaming_callback = None
    if not quiet:
        from soda.agents.streaming import StreamingCallback
        streaming_callback = StreamingCallback(verbose=True)
    # --- SENSE Phase ---
    logger.info("📡 SENSE: Gathering claims...")
    sense_ctx = SenseContext(
        run_id=ctx.run_id,
        iteration_number=iteration_num,
        milestone_base=ctx.milestone_base,
        root_work_item_id=ctx.root_work_item_id,
        project_id=ctx.project_id,
        project_root=ctx.working_directory or ".",
    )
    claims = sense(sense_ctx, git_client, trace_client, db)
    logger.info(f"   {len(claims.work_state.open_tasks)} open tasks, {len(claims.work_state.closed_tasks)} closed")

    # --- ORIENT Phase ---
    logger.info("🧭 ORIENT: Verifying claims and planning...")

    # Build iteration history for pattern recognition
    iteration_history = _build_iteration_history(db, ctx.run_id, iteration_num)

    orient_ctx = OrientContext(
        claims=claims,
        spec=ctx.spec_content,
        iteration_history=iteration_history,
        root_work_item_id=ctx.root_work_item_id,
    )
    orient_output = await orient(orient_ctx, streaming_callback=streaming_callback)
    logger.info(f"   spec_satisfied={orient_output.spec_satisfied.value}, actionable_work={orient_output.actionable_work_exists}")
    if orient_output.gaps:
        logger.info(f"   {len(orient_output.gaps)} gap(s) identified")

    # --- DECIDE Phase ---
    logger.info("🎯 DECIDE: Routing based on ORIENT output...")
    decision = decide(orient_output)
    logger.info(f"   Decision: {decision.outcome.value}")

    # --- ACT Phase (only if CONTINUE) ---
    act_output: Optional[ActOutput] = None
    if decision.outcome == DecisionOutcome.CONTINUE:
        logger.info("⚙️  ACT: Executing iteration plan...")

        # ACT requires an iteration plan from ORIENT
        if orient_output.iteration_plan is None:
            logger.warning("   ⚠️  No iteration plan from ORIENT - skipping ACT")
        else:
            if orient_output.iteration_plan.tasks:
                tasks_preview = ", ".join(t.task_id for t in orient_output.iteration_plan.tasks[:3])
                logger.info(f"   Tasks: {tasks_preview}")
            intent_preview = orient_output.iteration_plan.intent[:80]
            logger.info(f"   Intent: {intent_preview}...")

            # Read current learnings for ACT
            learnings = read_memory(ctx.project_id)

            act_ctx = ActContext(
                iteration_plan_json=orient_output.iteration_plan.model_dump_json(),
                learnings=learnings,
                spec_content=ctx.spec_content,
                iteration_num=iteration_num,
                milestone_branch=ctx.milestone_branch,
                working_directory=ctx.working_directory,
            )
            act_output = await act(
                act_ctx, git_client, trace_client, streaming_callback=streaming_callback
            )
            logger.info(f"   ✓ {len(act_output.tasks_completed)} completed, {len(act_output.tasks_blocked)} blocked")

    return IterationResult(
        iteration_num=iteration_num,
        outcome=decision.outcome,
        orient_output=orient_output,
        decision=decision,
        act_output=act_output,
    )


def _build_iteration_history(
    db: SodaDB,
    run_id: str,
    current_iteration: int,
) -> list[dict]:
    """Build iteration history for pattern recognition in ORIENT.

    Args:
        db: SodaDB for retrieving past iterations
        run_id: Current run ID
        current_iteration: Current iteration number (to exclude)

    Returns:
        List of iteration summaries with number, intent, outcome
    """
    iterations = db.get_iterations(run_id)
    history = []

    for it in iterations:
        if it.number < current_iteration:
            # Get executor summary if available
            executor_summary = None
            agent_outputs = db.get_agent_outputs(it.id)
            for output in agent_outputs:
                if output.agent_type.value == "executor":
                    executor_summary = output.summary
                    break

            history.append({
                "number": it.number,
                "intent": it.intent or "N/A",
                "outcome": it.outcome.value if it.outcome else "N/A",
                "executor_summary": executor_summary,
            })

    return history


# =============================================================================
# Main Loop
# =============================================================================


def _sdk_exception_handler(loop: "asyncio.AbstractEventLoop", context: dict) -> None:
    """Custom exception handler that suppresses SDK cancel scope errors.

    The Claude Agent SDK has a bug where async generator cleanup can raise
    RuntimeError about cancel scopes being exited in different tasks.
    These errors are logged as "Task exception was never retrieved" and
    can interfere with subsequent operations.

    This handler suppresses those specific errors while letting other
    exceptions through to the default handler.
    """
    exception = context.get("exception")
    if isinstance(exception, RuntimeError):
        msg = str(exception).lower()
        if "cancel scope" in msg and "different task" in msg:
            # Suppress SDK cancel scope errors
            logger.debug(f"Suppressed SDK background task error: {exception}")
            return

    # Use default handling for other exceptions
    loop.default_exception_handler(context)


async def run_loop(
    ctx: RunContext,
    git_client: GitClient,
    trace_client: TraceClient,
    db: SodaDB,
    quiet: bool = False,
) -> RunResult:
    """Execute the full SODA loop until termination.

    Runs iterations until:
    - DONE: Spec is satisfied
    - STUCK: Cannot make progress
    - max_iterations: Safety limit reached

    Args:
        ctx: RunContext with run configuration
        git_client: GitClient for git operations
        trace_client: TraceClient for Trace operations
        db: SodaDB for state persistence
        quiet: If True, suppress streaming output (default: False, always stream)

    Returns:
        RunResult with termination status and summary
    """
    # Install custom exception handler to suppress SDK cancel scope errors
    # This reduces log spam from the SDK's background task cleanup failures
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_sdk_exception_handler)

    logger.info(f"Starting SODA loop (max {ctx.max_iterations} iterations)")

    iterations_completed = 0
    last_result: Optional[IterationResult] = None

    for iteration_num in range(1, ctx.max_iterations + 1):
        logger.info(f"\n{'='*60}\nIteration {iteration_num}\n{'='*60}")

        try:
            result = await run_iteration(
                ctx=ctx,
                iteration_num=iteration_num,
                git_client=git_client,
                trace_client=trace_client,
                db=db,
                quiet=quiet,
            )
            iterations_completed = iteration_num
            last_result = result

            # Record iteration in database
            _record_iteration(db, ctx.run_id, result)

            # Check termination conditions
            if result.outcome == DecisionOutcome.DONE:
                logger.info("Loop terminated: DONE")
                return RunResult(
                    status="done",
                    iterations_completed=iterations_completed,
                    final_outcome=result.decision.summary or "Spec satisfied",
                    summary=_build_done_summary(result),
                )

            if result.outcome == DecisionOutcome.STUCK:
                logger.info("Loop terminated: STUCK")
                return RunResult(
                    status="stuck",
                    iterations_completed=iterations_completed,
                    final_outcome=result.decision.reason or "No actionable work",
                    summary=_build_stuck_summary(result),
                )

            # CONTINUE - loop back for next iteration
            logger.info("Continuing to next iteration...")

        except Exception as e:
            logger.error(f"Iteration {iteration_num} failed: {e}")
            # Record failed iteration
            _record_failed_iteration(db, ctx.run_id, iteration_num, str(e))
            # Continue to next iteration on recoverable errors
            # TODO: Add retry logic for transient errors
            iterations_completed = iteration_num

    # Max iterations reached
    logger.warning(f"Loop terminated: max iterations ({ctx.max_iterations}) reached")
    return RunResult(
        status="max_iterations",
        iterations_completed=iterations_completed,
        final_outcome=f"Max iterations ({ctx.max_iterations}) reached",
        summary=_build_max_iterations_summary(last_result, ctx.max_iterations),
    )


def _record_iteration(db: SodaDB, run_id: str, result: IterationResult) -> None:
    """Record an iteration result in the database.

    Args:
        db: SodaDB for state persistence
        run_id: Current run ID
        result: The iteration result to record
    """
    from soda.state.models import AgentOutput, AgentType, Iteration

    # Map DecisionOutcome to IterationOutcome
    outcome_map = {
        DecisionOutcome.DONE: IterationOutcome.DONE,
        DecisionOutcome.STUCK: IterationOutcome.STUCK,
        DecisionOutcome.CONTINUE: IterationOutcome.CONTINUE,
    }

    iteration = db.create_iteration(
        Iteration(
            id=None,
            run_id=run_id,
            number=result.iteration_num,
            intent=result.orient_output.iteration_plan.intent
            if result.orient_output.iteration_plan
            else "No iteration plan",
            outcome=outcome_map[result.outcome],
            started_at=datetime.now(),
            ended_at=datetime.now(),
        )
    )

    # Record ORIENT summary as agent output
    if iteration.id is not None:
        orient_summary = (
            f"spec_satisfied={result.orient_output.spec_satisfied.value}, "
            f"actionable_work={result.orient_output.actionable_work_exists}, "
            f"gaps={len(result.orient_output.gaps)}"
        )
        db.create_agent_output(
            AgentOutput(
                id=None,
                iteration_id=iteration.id,
                agent_type=AgentType.VERIFIER,  # ORIENT acts as verifier
                raw_output_path="",
                summary=orient_summary,
            )
        )

        # Record ACT summary if present
        if result.act_output:
            act_summary = (
                f"completed={len(result.act_output.tasks_completed)}, "
                f"blocked={len(result.act_output.tasks_blocked)}, "
                f"commits={len(result.act_output.commits)}"
            )
            db.create_agent_output(
                AgentOutput(
                    id=None,
                    iteration_id=iteration.id,
                    agent_type=AgentType.EXECUTOR,
                    raw_output_path="",
                    summary=act_summary,
                )
            )


def _record_failed_iteration(
    db: SodaDB, run_id: str, iteration_num: int, error: str
) -> None:
    """Record a failed iteration in the database.

    Args:
        db: SodaDB for state persistence
        run_id: Current run ID
        iteration_num: The iteration number that failed
        error: Error message
    """
    from soda.state.models import Iteration

    db.create_iteration(
        Iteration(
            id=None,
            run_id=run_id,
            number=iteration_num,
            intent=f"Failed: {error[:100]}",
            outcome=IterationOutcome.STUCK,
            started_at=datetime.now(),
            ended_at=datetime.now(),
        )
    )


def _build_done_summary(result: IterationResult) -> str:
    """Build a summary for DONE termination."""
    parts = [
        f"Spec satisfied after {result.iteration_num} iteration(s).",
    ]
    if result.decision.summary:
        parts.append(f"Summary: {result.decision.summary}")
    if result.act_output:
        parts.append(
            f"Final iteration: {len(result.act_output.tasks_completed)} tasks completed."
        )
    return " ".join(parts)


def _build_stuck_summary(result: IterationResult) -> str:
    """Build a summary for STUCK termination."""
    parts = [
        f"Stuck after {result.iteration_num} iteration(s).",
    ]
    if result.decision.reason:
        parts.append(f"Reason: {result.decision.reason}")
    if result.orient_output.gaps:
        gap_descriptions = [g.description for g in result.orient_output.gaps[:3]]
        parts.append(f"Gaps: {'; '.join(gap_descriptions)}")
    return " ".join(parts)


def _build_max_iterations_summary(
    last_result: Optional[IterationResult], max_iterations: int
) -> str:
    """Build a summary for max_iterations termination."""
    parts = [f"Reached maximum iterations ({max_iterations})."]
    if last_result:
        parts.append(f"Last outcome: {last_result.outcome.value}")
        if last_result.orient_output.gaps:
            remaining = len(last_result.orient_output.gaps)
            parts.append(f"Remaining gaps: {remaining}")
    return " ".join(parts)


# =============================================================================
# Run Completion
# =============================================================================


def complete_run(
    run_id: str,
    project_id: str,
    status: Literal["done", "stuck"],
    iterations: int,
    tasks_completed: list[str],
    tasks_blocked: list[BlockedTask],
    learnings: list[str],
    db: SodaDB,
    spec_title: str = "SODA Run",
    milestone_branch: Optional[str] = None,
) -> Path:
    """Complete a run and write summary.

    This function handles run completion by:
    1. Updating the database with the final status and timestamp
    2. Writing a summary markdown file to the summaries directory
    3. Printing completion information to the console

    Args:
        run_id: The run ID to complete
        project_id: The project UUID for locating the summaries directory
        status: Termination status - "done" or "stuck"
        iterations: Total number of iterations completed
        tasks_completed: List of task IDs that were completed during the run
        tasks_blocked: List of BlockedTask objects for tasks that couldn't be completed
        learnings: List of efficiency learnings discovered during the run
        db: SodaDB instance for database operations
        spec_title: Title of the spec for the summary (default: "SODA Run")
        milestone_branch: Optional milestone branch name for next steps

    Returns:
        Path to the summary file that was written
    """
    # --- Update Database ---
    completion_time = datetime.now()
    run_status = RunStatus.DONE if status == "done" else RunStatus.STUCK
    db.update_run_status(run_id, run_status, completion_time)

    # --- Write Summary ---
    summaries_dir = get_project_summaries_dir(project_id)
    timestamp_str = completion_time.strftime("%Y%m%d-%H%M%S")
    summary_filename = f"run-{run_id[:8]}-{timestamp_str}.md"
    summary_path = summaries_dir / summary_filename

    summary_content = _build_run_summary(
        run_id=run_id,
        status=status,
        iterations=iterations,
        tasks_completed=tasks_completed,
        tasks_blocked=tasks_blocked,
        learnings=learnings,
        spec_title=spec_title,
        completion_time=completion_time,
        milestone_branch=milestone_branch,
    )

    summary_path.write_text(summary_content)
    logger.info(f"Summary written to: {summary_path}")

    # --- Console Output ---
    _print_completion_message(
        status=status,
        iterations=iterations,
        tasks_completed=tasks_completed,
        tasks_blocked=tasks_blocked,
        milestone_branch=milestone_branch,
    )

    return summary_path


def _build_run_summary(
    run_id: str,
    status: str,
    iterations: int,
    tasks_completed: list[str],
    tasks_blocked: list[BlockedTask],
    learnings: list[str],
    spec_title: str,
    completion_time: datetime,
    milestone_branch: Optional[str] = None,
) -> str:
    """Build the markdown summary content for a completed run.

    Args:
        run_id: The run ID
        status: Termination status - "done" or "stuck"
        iterations: Total number of iterations completed
        tasks_completed: List of task IDs that were completed
        tasks_blocked: List of BlockedTask objects
        learnings: List of efficiency learnings
        spec_title: Title of the spec
        completion_time: Timestamp of completion
        milestone_branch: Optional milestone branch name

    Returns:
        Markdown-formatted summary string
    """
    lines = [
        "# SODA Run Summary",
        "",
        f"**Run ID:** {run_id}",
        f"**Status:** {status.upper()}",
        f"**Iterations:** {iterations}",
        f"**Completed:** {completion_time.isoformat()}",
        "",
        "## Spec",
        spec_title,
        "",
    ]

    # Tasks Completed section
    lines.append("## Tasks Completed")
    if tasks_completed:
        for task_id in tasks_completed:
            lines.append(f"- {task_id}")
    else:
        lines.append("*No tasks completed*")
    lines.append("")

    # Tasks Blocked section
    lines.append("## Tasks Blocked")
    if tasks_blocked:
        for blocked in tasks_blocked:
            lines.append(f"- {blocked.task_id}: {blocked.reason}")
    else:
        lines.append("*No blocked tasks*")
    lines.append("")

    # Learnings section
    lines.append("## Learnings Captured")
    if learnings:
        for learning in learnings:
            lines.append(f"- {learning}")
    else:
        lines.append("*No learnings captured*")
    lines.append("")

    # Next Steps section
    lines.append("## Next Steps")
    if status == "done":
        if milestone_branch:
            lines.append(f"1. Review changes on branch `{milestone_branch}`")
            lines.append(
                f"2. Create PR: `gh pr create --base main --head {milestone_branch}`"
            )
        else:
            lines.append("1. Review the changes made during this run")
            lines.append("2. Create a pull request to merge your changes")
    else:  # stuck
        lines.append("1. Review the blocked tasks above")
        lines.append("2. Address the blockers manually")
        lines.append("3. Resume the run with `soda resume`")
    lines.append("")

    return "\n".join(lines)


def _print_completion_message(
    status: str,
    iterations: int,
    tasks_completed: list[str],
    tasks_blocked: list[BlockedTask],
    milestone_branch: Optional[str] = None,
) -> None:
    """Print completion information to the console.

    Args:
        status: Termination status - "done" or "stuck"
        iterations: Total number of iterations completed
        tasks_completed: List of task IDs that were completed
        tasks_blocked: List of BlockedTask objects
        milestone_branch: Optional milestone branch name
    """
    if status == "done":
        print("\n" + "=" * 60)
        print("SODA Run Complete!")
        print("=" * 60)
        print(f"Status: DONE")
        print(f"Iterations: {iterations}")
        print(f"Tasks completed: {len(tasks_completed)}")
        if tasks_blocked:
            print(f"Tasks blocked: {len(tasks_blocked)}")
        print("")
        print("Next steps:")
        if milestone_branch:
            print(f"  1. Review changes on branch: {milestone_branch}")
            print(f"  2. Create PR: gh pr create --base main --head {milestone_branch}")
        else:
            print("  1. Review the changes made during this run")
            print("  2. Create a pull request to merge your changes")
    else:  # stuck
        print("\n" + "=" * 60)
        print("SODA Run Stuck")
        print("=" * 60)
        print(f"Status: STUCK")
        print(f"Iterations: {iterations}")
        print(f"Tasks completed: {len(tasks_completed)}")
        print(f"Tasks blocked: {len(tasks_blocked)}")
        print("")
        if tasks_blocked:
            print("Blocked tasks:")
            for blocked in tasks_blocked[:3]:  # Show first 3
                print(f"  - {blocked.task_id}: {blocked.reason[:50]}...")
            if len(tasks_blocked) > 3:
                print(f"  ... and {len(tasks_blocked) - 3} more")
        print("")
        print("Next steps:")
        print("  1. Address the blockers above")
        print("  2. Resume with: soda resume")
