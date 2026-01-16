"""Executor agent: Do the assigned work."""

import asyncio
import os
import subprocess
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage

from ralph2.agents.models import ExecutorResult
from ralph2.agents.streaming import stream_agent_output
from ralph2.agents.constants import AGENT_MODEL
from ralph2.git import GitBranchManager


EXECUTOR_SYSTEM_PROMPT = """You are the Executor agent in the Ralph2 multi-agent system.

Your job is to do the work assigned to you by the Planner.

## Your Responsibilities

1. Read the iteration intent to understand what you should work on
2. Read task details from Trace (`trc show <id>`) as needed
3. Do the work using the appropriate approach:
   - **Code work**: Write a failing test first, then make it pass
   - **Non-code work** (docs, research, configs): Do directly
4. Keep Trace updated as you work (comments, subtasks, status)
5. Commit your work to the branch before finishing

## Using Trace for Work Tracking

Use Trace (not TodoWrite) for all work tracking. Trace persists across sessions and commits to git.

**Core workflow:**
```bash
trc show <id>          # Get task details with description and comments
trc comment <id> "message" --source executor  # Leave progress comments
trc create "subtask" --description "details" --parent <id>  # Break down work
trc close <id>         # Mark complete when fully finished
```

**When to leave comments:**
- When you start working on a task
- When you complete significant progress
- When you discover something important
- When you encounter a blocker

**When to create subtasks:**
- When work naturally breaks into distinct pieces
- When you discover additional work needed
- Use `--parent <id>` to link to the main task

**Key rules:**
- Always include `--source executor` when commenting
- `--description` is required when creating tasks (preserves context)
- Comments persist and are visible to the Planner
- Be specific about what you did and learned

## Committing Your Work

You are working in a git branch. Before finishing:

1. Stage your changes: `git add -A`
2. Commit with a meaningful message: `git commit -m "description of changes"`

Your work will be merged to main after you complete. Uncommitted changes will be lost.

## Test-Driven Development

When writing code (functions, modules, features, bug fixes):
1. Write a test that expresses the expected behavior
2. Run it—confirm it fails
3. Write the minimum code to make it pass
4. Run the test again—confirm it passes

Keep the test. It documents the behavior and catches regressions.

When NOT to write tests:
- Documentation or README updates
- Research, analysis, or recommendations
- Configuration changes

If unsure whether something needs a test: if it has behavior that can break, test it.

## Your Boundaries

- You DO NOT decide what to work on (the Planner does that)
- You DO NOT judge if the spec is satisfied (the Verifier does that)
- You DO the work: read, edit, test, comment, commit

## Recognizing Verification Boundaries

Some work can be verified with tests you write (infrastructure/capability).
Some work requires real external systems to verify (behavior).

**Infrastructure work** (you can fully verify):
- API clients, data models, configuration loading
- Test with mocks—proves the plumbing works

**Behavioral work** (requires real systems to verify):
- Agent decision-making, classification accuracy
- LLM judgment calls, response quality

When you complete infrastructure but cannot verify behavior:
- Report Status: **Blocked** (not Completed)
- Document exactly what resources are needed for behavioral verification

## Before You Finish

Before reporting your final status, verify:
1. **Traces updated**: All relevant tasks have comments documenting your work
2. **Work committed**: All changes are committed to the branch (`git status` shows clean)

Your structured output will ask you to confirm both of these.

## Valid Exit Conditions

- **Completed**: Work finished, tests pass, changes committed, traces updated
- **Blocked**: Can't proceed—missing dependency, unclear requirement, or external blocker
- **Uncertain**: Not sure if approach is correct, need guidance

All three are valid outcomes. Don't force completion.
"""


async def _run_executor_agent(
    prompt: str,
    options: ClaudeAgentOptions,
) -> tuple[Optional[ExecutorResult], str, list]:
    """Run the executor agent and return results.

    Args:
        prompt: The prompt to send to the agent
        options: Agent options

    Returns:
        (result, full_output, messages)
    """
    full_output = []
    messages = []
    result: Optional[ExecutorResult] = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            # Save raw message
            if hasattr(message, "model_dump"):
                messages.append(message.model_dump())
            else:
                messages.append(str(message))

            # Stream output to terminal using shared utility
            stream_agent_output(message, full_output)

            # Check for the final result with structured output
            if isinstance(message, ResultMessage):
                if message.structured_output:
                    # Validate and convert to Pydantic model
                    result = ExecutorResult.model_validate(message.structured_output)
                    print(f"\033[32m✓ Executor status: {result.status}\033[0m")
                elif message.subtype == "error_max_structured_output_retries":
                    print(f"\033[31m✗ Failed to get structured output after retries\033[0m")

    full_text = "\n".join(full_output)
    return result, full_text, messages


def _check_uncommitted_changes(worktree_path: str) -> bool:
    """Check if there are uncommitted changes in the worktree.

    Args:
        worktree_path: Path to the git worktree

    Returns:
        True if there are uncommitted changes, False if clean or directory doesn't exist
    """
    if not os.path.isdir(worktree_path):
        # Worktree doesn't exist (may be mocked in tests) - assume clean
        return False

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
    except Exception:
        # If git status fails, assume clean to avoid blocking
        return False


def _auto_commit_changes(worktree_path: str, message: str) -> bool:
    """Auto-commit any uncommitted changes in the worktree.

    Args:
        worktree_path: Path to the git worktree
        message: Commit message

    Returns:
        True if commit succeeded, False otherwise
    """
    # Stage all changes
    result = subprocess.run(
        ["git", "add", "-A"],
        cwd=worktree_path,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return False

    # Commit
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=worktree_path,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


async def _verify_and_remediate_commit(
    result: ExecutorResult,
    options: ClaudeAgentOptions,
    worktree_path: str
) -> ExecutorResult:
    """Verify work is committed and remediate if not.

    If the executor reported work_committed=False or there are uncommitted changes,
    prompt the agent to commit, or auto-commit as fallback.

    Args:
        result: The executor result
        options: Agent options for follow-up prompts
        worktree_path: Path to the git worktree

    Returns:
        Updated ExecutorResult
    """
    has_uncommitted = _check_uncommitted_changes(worktree_path)

    # If agent said committed but there are uncommitted changes, log discrepancy
    if result.work_committed and has_uncommitted:
        print(f"\033[33m⚠ Agent reported work_committed=True but uncommitted changes found\033[0m")

    # If no uncommitted changes, we're good
    if not has_uncommitted:
        if not result.work_committed:
            # Agent said false but actually there are no changes - update the result
            print(f"\033[32m✓ Working tree is clean\033[0m")
        return result

    # There are uncommitted changes - need to handle them
    print(f"\033[33m⚠ Uncommitted changes detected in worktree\033[0m")

    if not result.work_committed:
        # Agent honestly reported they didn't commit - prompt them to do so
        print(f"\033[36m→ Prompting agent to commit changes...\033[0m")

        commit_prompt = """You indicated you haven't committed your work yet.

Please commit your changes now:
1. Run `git add -A` to stage all changes
2. Run `git commit -m "your descriptive commit message"` to commit

Your work will be lost if not committed before the worktree is cleaned up."""

        try:
            commit_result, _, _ = await _run_executor_agent(commit_prompt, options)
            # Check if changes are now committed
            if not _check_uncommitted_changes(worktree_path):
                print(f"\033[32m✓ Agent committed changes successfully\033[0m")
                return ExecutorResult(
                    status=result.status,
                    what_was_done=result.what_was_done,
                    blockers=result.blockers,
                    notes=result.notes,
                    efficiency_notes=result.efficiency_notes,
                    work_committed=True,
                    traces_updated=result.traces_updated
                )
        except Exception as e:
            print(f"\033[33mWarning: Commit prompt failed: {e}\033[0m")

    # Fallback: auto-commit
    print(f"\033[33m→ Auto-committing changes as fallback...\033[0m")
    commit_message = f"Executor work: {result.what_was_done[:100]}" if result.what_was_done else "Executor work (auto-commit)"

    if _auto_commit_changes(worktree_path, commit_message):
        print(f"\033[32m✓ Auto-commit successful\033[0m")
        return ExecutorResult(
            status=result.status,
            what_was_done=result.what_was_done,
            blockers=result.blockers,
            notes=(result.notes or "") + " [Changes auto-committed]",
            efficiency_notes=result.efficiency_notes,
            work_committed=True,
            traces_updated=result.traces_updated
        )
    else:
        print(f"\033[31m✗ Auto-commit failed - changes may be lost\033[0m")
        return result


async def run_executor(
    iteration_intent: str,
    spec_content: str,
    memory: str = "",
    work_item_id: Optional[str] = None,
    run_id: Optional[str] = None,
    worktree_path: Optional[str] = None,
) -> dict:
    """
    Run the Executor agent.

    Args:
        iteration_intent: What the planner assigned for this iteration
        spec_content: The specification content (for reference)
        memory: Project memory content
        work_item_id: Optional work item ID from Trace (for parallel execution)
        run_id: Optional run ID (required if work_item_id is provided, for worktree path isolation)
        worktree_path: Optional pre-created worktree path (orchestrator-managed mode).
                       When provided, the executor uses this path directly and does NOT
                       handle merge or cleanup - the orchestrator handles those.

    Returns:
        dict with keys: 'result' (ExecutorResult), 'full_output' (str), 'messages' (list)
    """
    # Build the prompt
    prompt_parts = [
        "# Iteration Intent",
        "",
        iteration_intent,
        "",
    ]

    if work_item_id:
        prompt_parts.append(f"**Assigned Work Item:** {work_item_id}")
        prompt_parts.append("")

    prompt_parts.extend([
        "---",
        "",
    ])

    if memory:
        prompt_parts.append("# Project Memory")
        prompt_parts.append("")
        prompt_parts.append(memory)
        prompt_parts.append("")
        prompt_parts.append("---")
        prompt_parts.append("")

    prompt_parts.extend([
        "# Spec (for reference)",
        "",
        spec_content,
        "",
        "---",
        "",
        "# Your Task",
        "",
        "1. Review the iteration intent to understand what to work on",
        "2. Use `trc show <id>` to get details on specific tasks if needed",
        "3. Do the work (read files, make changes, test, etc.)",
        "4. Leave comments on tasks as you work (when available)",
    ])

    prompt = "\n".join(prompt_parts)

    # Configure the agent with structured output
    options = ClaudeAgentOptions(
        model=AGENT_MODEL,
        allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt=EXECUTOR_SYSTEM_PROMPT,
        output_format={
            "type": "json_schema",
            "schema": ExecutorResult.model_json_schema()
        }
    )

    # Mode 1: Orchestrator-managed worktree (parallel execution)
    # When worktree_path is provided, use it directly - no merge/cleanup
    if worktree_path:
        return await _run_executor_with_orchestrator_worktree(prompt, options, worktree_path)

    # Mode 2: No git isolation (single executor, no work_item_id)
    if not work_item_id:
        return await _run_executor_without_isolation(prompt, options)

    # Mode 3: Executor-managed worktree (backward compatibility)
    # Use GitBranchManager for git isolation with guaranteed cleanup
    # run_id is required for worktree path isolation in parallel execution
    effective_run_id = run_id or "default"

    git_manager = GitBranchManager(
        work_item_id=work_item_id,
        run_id=effective_run_id,
        cwd=os.getcwd()
    )

    return await _run_executor_with_git_isolation(prompt, options, git_manager)


async def _run_executor_with_orchestrator_worktree(
    prompt: str,
    options: ClaudeAgentOptions,
    worktree_path: str,
) -> dict:
    """Run executor in an orchestrator-managed worktree.

    In this mode:
    - Worktree already exists (created by orchestrator)
    - Executor works and commits in the worktree
    - Executor does NOT merge or cleanup (orchestrator handles those)

    This is the preferred mode for parallel execution because:
    - All worktrees are created before any executor runs
    - All merges happen serially after all executors complete
    - All cleanup is guaranteed even if executors fail

    Args:
        prompt: The prompt to send to the agent
        options: Agent options
        worktree_path: Path to the pre-created worktree

    Returns:
        dict with executor results
    """
    # Create options with cwd set to worktree path
    options_with_cwd = ClaudeAgentOptions(
        model=options.model,
        allowed_tools=options.tools,
        permission_mode=options.permission_mode,
        system_prompt=options.system_prompt,
        output_format=options.output_format,
        cwd=worktree_path,
    )

    try:
        result, full_text, messages = await _run_executor_agent(prompt, options_with_cwd)
    except Exception as e:
        print(f"\033[33mWarning: Agent query ended with error: {e}\033[0m")
        result = None
        full_text = ""
        messages = []

    # If we didn't get a valid result, create a default
    if result is None:
        print(f"\033[33mWarning: No structured output received, using default Completed\033[0m")
        result = ExecutorResult(
            status="Completed",
            what_was_done="Work completed (no structured output received)",
            work_committed=False,
            traces_updated=False
        )

    # Verify and remediate work_committed status
    # This is critical - uncommitted changes will be lost when worktree is cleaned up
    result = await _verify_and_remediate_commit(result, options_with_cwd, worktree_path)

    # NOTE: We do NOT merge or cleanup here - the orchestrator handles that
    # This allows:
    # 1. All executors to complete before any merge
    # 2. Merges to happen serially (no race conditions)
    # 3. Guaranteed cleanup even if some executors fail

    return _build_executor_response(result, full_text, messages)


async def _run_executor_without_isolation(prompt: str, options: ClaudeAgentOptions) -> dict:
    """Run executor without git worktree isolation.

    Args:
        prompt: The prompt to send to the agent
        options: Agent options

    Returns:
        dict with executor results
    """
    try:
        result, full_text, messages = await _run_executor_agent(prompt, options)
    except Exception as e:
        print(f"\033[33mWarning: Agent query ended with error: {e}\033[0m")
        result = None
        full_text = ""
        messages = []

    if result is None:
        print(f"\033[33mWarning: No structured output received, using default Completed\033[0m")
        result = ExecutorResult(
            status="Completed",
            what_was_done="Work completed (no structured output received)",
            work_committed=False,
            traces_updated=False
        )

    return _build_executor_response(result, full_text, messages)


async def _run_executor_with_git_isolation(
    prompt: str,
    options: ClaudeAgentOptions,
    git_manager: GitBranchManager
) -> dict:
    """Run executor with git worktree isolation using GitBranchManager.

    Uses context manager pattern for guaranteed cleanup.

    IMPORTANT: This function does NOT use os.chdir() because that mutates shared
    process state and causes race conditions when multiple executors run in parallel.
    Instead, we pass the worktree path via the cwd parameter to ClaudeAgentOptions.

    Args:
        prompt: The prompt to send to the agent
        options: Agent options
        git_manager: GitBranchManager instance for worktree operations

    Returns:
        dict with executor results
    """
    result = None
    full_text = ""
    messages = []

    try:
        # Use context manager for guaranteed cleanup
        with git_manager:
            worktree_path = git_manager.worktree_path

            # Create new options with cwd set to worktree path
            # This avoids os.chdir() which causes race conditions in parallel execution
            options_with_cwd = ClaudeAgentOptions(
                model=options.model,
                allowed_tools=options.tools,
                permission_mode=options.permission_mode,
                system_prompt=options.system_prompt,
                output_format=options.output_format,
                cwd=worktree_path,
            )

            try:
                result, full_text, messages = await _run_executor_agent(prompt, options_with_cwd)
            except Exception as e:
                print(f"\033[33mWarning: Agent query ended with error: {e}\033[0m")
                result = None
                full_text = ""
                messages = []

            # If we didn't get a valid result, create a default
            if result is None:
                print(f"\033[33mWarning: No structured output received, using default Completed\033[0m")
                result = ExecutorResult(
                    status="Completed",
                    what_was_done="Work completed (no structured output received)",
                    work_committed=False,
                    traces_updated=False
                )

            # Verify and remediate work_committed status
            # Use options_with_cwd so any follow-up agent calls also work in the worktree
            result = await _verify_and_remediate_commit(
                result, options_with_cwd, git_manager.worktree_path
            )

            # Handle merge/cleanup based on status
            if result.status == "Completed":
                result = await _handle_completed_status(result, options_with_cwd, git_manager)
            else:
                # Status is Blocked or Uncertain - worktree will be cleaned up by context manager
                result = _handle_non_completed_status(result)

    except RuntimeError as e:
        # GitBranchManager failed to create worktree
        error_result = ExecutorResult(
            status="Blocked",
            what_was_done="Failed to create git worktree",
            blockers=str(e),
            notes="Cannot proceed without worktree isolation",
            work_committed=False,
            traces_updated=False
        )
        return _build_executor_response(error_result, "", [])

    return _build_executor_response(result, full_text, messages)


async def _handle_completed_status(
    result: ExecutorResult,
    options: ClaudeAgentOptions,
    git_manager: GitBranchManager
) -> ExecutorResult:
    """Handle Completed status: attempt merge and conflict resolution.

    Args:
        result: The executor result
        options: Agent options for conflict resolution
        git_manager: GitBranchManager instance

    Returns:
        Updated ExecutorResult
    """
    merge_success, merge_error = git_manager.merge_to_main()

    if merge_success:
        # Merge succeeded - cleanup handled by context manager
        print(f"\033[32m✓ Merged successfully\033[0m")
        return result

    # Merge failed - attempt resolution
    print(f"\033[33m⚠ Merge conflict detected. Attempting resolution...\033[0m")

    conflict_prompt = f"""# Merge Conflict Resolution

You attempted to merge your work but encountered a merge conflict:

{merge_error}

## Your Task

1. Examine the conflicted files using git status and reading the files
2. Resolve the conflicts (edit files to remove conflict markers and fix the code)
3. Stage the resolved files with `git add <file>`
4. Complete the merge with `git commit` (it will use the default merge message)
"""

    try:
        resolution_result, _, _ = await _run_executor_agent(conflict_prompt, options)
    except Exception as e:
        print(f"\033[33mWarning: Conflict resolution agent ended with error: {e}\033[0m")
        resolution_result = None

    # Check if conflicts are actually resolved
    if resolution_result and resolution_result.status == "Completed":
        has_conflicts, _ = git_manager.check_merge_conflicts()
        if not has_conflicts:
            # Conflicts resolved - retry merge
            merge_success, merge_error = git_manager.merge_to_main()

    if merge_success:
        print(f"\033[32m✓ Merge conflicts resolved and merged successfully\033[0m")
        return result
    else:
        # Resolution failed
        return ExecutorResult(
            status="Blocked",
            what_was_done="Work completed but merge conflict resolution failed",
            blockers=merge_error,
            notes="Attempted automatic conflict resolution but failed. Worktree and branch abandoned.",
            efficiency_notes=result.efficiency_notes,
            work_committed=result.work_committed,
            traces_updated=result.traces_updated
        )


def _handle_non_completed_status(result: ExecutorResult) -> ExecutorResult:
    """Handle Blocked or Uncertain status: add abandonment note.

    Args:
        result: The executor result

    Returns:
        Updated ExecutorResult with abandonment note
    """
    if result.notes:
        return ExecutorResult(
            status=result.status,
            what_was_done=result.what_was_done,
            blockers=result.blockers,
            notes=f"{result.notes}. Worktree and branch abandoned due to {result.status} status.",
            efficiency_notes=result.efficiency_notes,
            work_committed=result.work_committed,
            traces_updated=result.traces_updated
        )
    else:
        return ExecutorResult(
            status=result.status,
            what_was_done=result.what_was_done,
            blockers=result.blockers,
            notes=f"Worktree and branch abandoned due to {result.status} status",
            efficiency_notes=result.efficiency_notes,
            work_committed=result.work_committed,
            traces_updated=result.traces_updated
        )


def _build_executor_response(result: ExecutorResult, full_text: str, messages: list) -> dict:
    """Build the executor response dictionary.

    Args:
        result: ExecutorResult
        full_text: Full agent output
        messages: Raw messages list

    Returns:
        dict with executor results and legacy fields
    """
    return {
        "result": result,
        "full_output": full_text,
        "messages": messages,
        # Legacy fields for backward compatibility
        "status": result.status,
        "summary": f"Status: {result.status}\nWhat was done: {result.what_was_done}\nBlockers: {result.blockers or 'None'}\nNotes: {result.notes or 'None'}\nEfficiency Notes: {result.efficiency_notes or 'None'}",
        "efficiency_notes": result.efficiency_notes,
    }


async def main():
    """Test the executor agent."""
    spec = """
    # Test Spec

    Build a simple hello world Python script.

    ## Acceptance Criteria
    - [ ] Python script that prints "Hello, World!"
    - [ ] Script is executable
    """

    intent = "Create a hello.py script that prints 'Hello, World!'"

    result = await run_executor(iteration_intent=intent, spec_content=spec)
    print("\nResult:", result["result"])
    print("\nStatus:", result["status"])


if __name__ == "__main__":
    asyncio.run(main())
