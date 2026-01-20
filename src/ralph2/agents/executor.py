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

Your job is to do the work assigned to you.

## Your Responsibilities

1. Read your assigned work item from Trace (`trc show <id>`) to understand what you should do
2. Do ONLY that work—nothing else. Stay focused on your assigned task.
3. Use the appropriate approach:
   - **Code work**: Write a failing test first, then make it pass
   - **Non-code work** (docs, research, configs): Do directly
4. Keep Trace updated as you work (comments, subtasks, status)
5. Commit your work to the branch before finishing

## CRITICAL: Stay Focused on Your Assigned Work Item

You are assigned ONE specific work item. Your job is to complete THAT task and nothing else.
- Do NOT do work outside your assigned task scope
- Do NOT try to complete the entire iteration or spec
- If you discover related work needed, create a subtask or leave a comment—don't do it yourself

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

## CRITICAL: What "Completed" Means

**Completed = Verified by Tests**

You may ONLY report status "Completed" when:
1. You have written tests for the work (if applicable)
2. You have RUN the tests (`uv run pytest` or equivalent)
3. The tests PASS

**If you cannot run tests:**
- Tests require external resources → Status: **Blocked**, not Completed
- Tests are too slow → Status: **Blocked**, not Completed
- No test framework exists → Status: **Blocked**, not Completed

**The pattern "I made a fix, needs verification" = Blocked, NOT Completed**

Never punt verification to the Verifier. The Verifier checks spec satisfaction, not your work quality. You own verification of your own work.

## Investigation Tasks

Investigation/research tasks are valid work. When assigned "Investigate: X":

**Your deliverable is information, not code:**
1. Reproduce the issue (run failing code, capture full output/traceback)
2. Analyze the error chain (what triggers what?)
3. Identify the actual root cause (not symptoms)
4. Document findings in a Trace comment
5. Recommend fix approach (but don't implement unless assigned)

**Investigation output structure:**
```
## Findings for: <issue>

**Reproduction:**
- Command: `<what you ran>`
- Error: `<exact error message>`

**Root Cause:**
<explanation of why this happens>

**Recommended Fix:**
<approach to fix, not full implementation>
```

**Status after investigation:**
- Completed = You identified root cause and documented findings
- Blocked = You cannot reproduce or need external resources
- Uncertain = Multiple possible causes, need guidance on which to pursue

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

## Efficiency Notes

Before finishing, reflect on what you learned that would help future iterations:

**Ask yourself:** "What do I wish I'd known when I started?"

Good efficiency notes are:
- **Specific**: "Run tests with `uv run pytest tests/ -v`" not "tests exist"
- **Actionable**: Tell someone what to DO, not what you discovered
- **Project-specific**: Not general knowledge, but THIS project's patterns

Examples of GOOD efficiency notes:
- "Project structure: src/mr_reviewer/{cli,config,models,gitlab_client,agent}.py"
- "Use `uv run mr-reviewer --help` to test CLI changes"
- "GitLab client is in gitlab_client.py, uses python-gitlab library"
- "Settings loaded via pydantic-settings from .env file"

Examples of BAD efficiency notes (too vague):
- "The project has good structure"
- "Tests are helpful"
- "Read the code first"

Fill in the `efficiency_notes` field in your output with 2-3 concrete insights.

## Before You Finish

Before reporting your final status, verify:
1. **Traces updated**: All relevant tasks have comments documenting your work
2. **Work committed**: All changes are committed to the branch (`git status` shows clean)

Your structured output will ask you to confirm both of these.

## Valid Exit Conditions

- **Completed**: Tests written, tests RUN, tests PASS, changes committed
- **Blocked**: Can't proceed OR can't verify (missing deps, external resources, can't run tests)
- **Uncertain**: Not sure if approach is correct, need guidance

All three are valid outcomes. Don't force completion. "Blocked" because you can't verify is preferable to "Completed" without verification.
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


async def _gather_efficiency_notes(
    result: ExecutorResult,
    options: ClaudeAgentOptions,
) -> ExecutorResult:
    """Gather efficiency notes from the agent after work is complete.

    This runs as a follow-up in the same session, while the agent still has
    full context of what it just did. This produces better learnings than
    asking upfront in the system prompt.

    Args:
        result: The executor result (may already have efficiency_notes)
        options: Agent options for follow-up prompts

    Returns:
        Updated ExecutorResult with enriched efficiency_notes
    """
    # Skip if agent already provided substantial efficiency notes
    if result.efficiency_notes and len(result.efficiency_notes) > 100:
        return result

    print(f"\033[36m→ Gathering efficiency notes...\033[0m")

    reflection_prompt = """Now that you've completed the work, I have a few quick reflection questions to help future iterations:

1. **What would have saved you time?**
   Think about what you had to discover or figure out. What do you wish you'd known when you started?

2. **What project patterns did you find?**
   Any specific file locations, import patterns, test commands, or conventions that were useful?

3. **Any gotchas or surprises?**
   Anything that almost tripped you up or was different from what you expected?

Please respond with 2-4 bullet points of concrete, actionable insights. Be specific - mention file paths, commands, or patterns by name.

Example good responses:
- "Project uses src/app/{routes,models,services}.py structure - start there for any feature work"
- "Run tests with `uv run pytest -xvs` - the -x flag stops on first failure which speeds up debugging"
- "Config is in .env but loaded via pydantic-settings in config.py - check Settings class for required vars"
"""

    try:
        # Create options without structured output for free-form response
        reflection_options = ClaudeAgentOptions(
            model=options.model,
            allowed_tools=[],  # No tools needed for reflection
            permission_mode=options.permission_mode,
            system_prompt="You are reflecting on work you just completed. Be concise and specific.",
            cwd=options.cwd,
        )

        full_output = []
        async with ClaudeSDKClient(options=reflection_options) as client:
            await client.query(reflection_prompt)

            async for message in client.receive_response():
                stream_agent_output(message, full_output)

        reflection_text = "\n".join(full_output).strip()

        if reflection_text:
            # Combine with any existing efficiency notes
            if result.efficiency_notes:
                combined_notes = f"{result.efficiency_notes}\n\n{reflection_text}"
            else:
                combined_notes = reflection_text

            print(f"\033[32m✓ Gathered efficiency notes\033[0m")

            return ExecutorResult(
                status=result.status,
                what_was_done=result.what_was_done,
                blockers=result.blockers,
                notes=result.notes,
                efficiency_notes=combined_notes,
                work_committed=result.work_committed,
                traces_updated=result.traces_updated
            )

    except Exception as e:
        print(f"\033[33m⚠ Could not gather efficiency notes: {e}\033[0m")

    return result


async def run_executor(
    iteration_intent: Optional[str] = None,
    spec_content: str = "",
    memory: str = "",
    work_item_id: Optional[str] = None,
    run_id: Optional[str] = None,
    worktree_path: Optional[str] = None,
) -> dict:
    """
    Run the Executor agent.

    Args:
        iteration_intent: What the planner assigned for this iteration (used for single executor mode)
        spec_content: The specification content (for reference)
        memory: Project memory content
        work_item_id: Work item ID from Trace - when provided, executor focuses ONLY on this task
        run_id: Optional run ID (required if work_item_id is provided, for worktree path isolation)
        worktree_path: Optional pre-created worktree path (orchestrator-managed mode).
                       When provided, the executor uses this path directly and does NOT
                       handle merge or cleanup - the orchestrator handles those.

    Returns:
        dict with keys: 'result' (ExecutorResult), 'full_output' (str), 'messages' (list)
    """
    # Build the prompt based on whether we have a specific work item or general intent
    prompt_parts = []

    if work_item_id:
        # Focused mode: executor works ONLY on this specific Trace work item
        prompt_parts.extend([
            "# Your Assigned Work Item",
            "",
            f"**Work Item ID:** `{work_item_id}`",
            "",
            f"Run `trc show {work_item_id}` to see the full task details, then complete that task.",
            "",
            "**Important:** Focus ONLY on this work item. Do not do other work.",
            "",
            "---",
            "",
        ])
    elif iteration_intent:
        # General mode: executor works on iteration intent (single executor, no parallelism)
        prompt_parts.extend([
            "# Iteration Intent",
            "",
            iteration_intent,
            "",
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

    if spec_content:
        prompt_parts.extend([
            "# Spec (for reference)",
            "",
            spec_content,
            "",
            "---",
            "",
        ])

    prompt_parts.append("# Your Task")
    prompt_parts.append("")

    if work_item_id:
        # Focused mode: work on specific Trace item
        prompt_parts.extend([
            f"1. Run `trc show {work_item_id}` to read your assigned task",
            "2. Do ONLY that work (read files, make changes, test, etc.)",
            "3. Leave comments on the task as you work (`trc comment <id> 'message' --source executor`)",
            "4. Close the task when complete (`trc close <id>`)",
            "",
            "**Stay focused on your assigned work item. Do not do other work.**",
        ])
    else:
        # General mode: work on iteration intent
        prompt_parts.extend([
            "1. Review the iteration intent to understand what to work on",
            "2. Use `trc show <id>` to get details on specific tasks if needed",
            "3. Do the work (read files, make changes, test, etc.)",
            "4. Leave comments on tasks as you work",
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

    # Gather efficiency notes while context is fresh
    result = await _gather_efficiency_notes(result, options_with_cwd)

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

            # Gather efficiency notes while context is fresh
            result = await _gather_efficiency_notes(result, options_with_cwd)

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


async def _attempt_conflict_resolution(
    original_result: ExecutorResult,
    merge_error: str,
    options: ClaudeAgentOptions,
    git_manager: GitBranchManager
) -> ExecutorResult:
    """Attempt to resolve merge conflicts by invoking the executor agent.

    Args:
        original_result: The original executor result before merge attempt
        merge_error: Error message from failed merge
        options: Agent options for conflict resolution
        git_manager: GitBranchManager instance

    Returns:
        ExecutorResult - either the original result if resolution succeeds,
        or a Blocked result if resolution fails
    """
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
    merge_success = False
    if resolution_result and resolution_result.status == "Completed":
        has_conflicts, _ = git_manager.check_merge_conflicts()
        if not has_conflicts:
            # Conflicts resolved - retry merge
            merge_success, merge_error = git_manager.merge_to_main()

    if merge_success:
        print(f"\033[32m✓ Merge conflicts resolved and merged successfully\033[0m")
        return original_result
    else:
        # Resolution failed
        return ExecutorResult(
            status="Blocked",
            what_was_done="Work completed but merge conflict resolution failed",
            blockers=merge_error,
            notes="Attempted automatic conflict resolution but failed. Worktree and branch abandoned.",
            efficiency_notes=original_result.efficiency_notes,
            work_committed=original_result.work_committed,
            traces_updated=original_result.traces_updated
        )


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
    return await _attempt_conflict_resolution(result, merge_error, options, git_manager)


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
