"""Executor agent: Do the assigned work."""

import asyncio
import subprocess
from typing import Optional

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


def _git_run(command: list[str]) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(command, capture_output=True, text=True)


def _create_feature_branch(work_item_id: str) -> bool:
    """Create and checkout a feature branch for the work item.

    Returns:
        True if successful, False otherwise
    """
    branch_name = f"ralph2/{work_item_id}"
    result = _git_run(["git", "checkout", "-b", branch_name])
    return result.returncode == 0


def _merge_to_main(work_item_id: str) -> tuple[bool, str]:
    """Merge feature branch to main.

    Returns:
        (success, error_message)
    """
    branch_name = f"ralph2/{work_item_id}"

    # Checkout main
    result = _git_run(["git", "checkout", "main"])
    if result.returncode != 0:
        return False, f"Failed to checkout main: {result.stderr}"

    # Merge feature branch
    result = _git_run(["git", "merge", branch_name])
    if result.returncode != 0:
        # Merge conflict or error - return conflict info for resolution attempt
        return False, f"Merge conflict: {result.stderr}"

    return True, ""


def _check_merge_conflicts() -> tuple[bool, str]:
    """Check if there are unresolved merge conflicts.

    Returns:
        (has_conflicts, conflict_info)
    """
    # Check git status for conflicts
    result = _git_run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        return True, "Failed to check git status"

    # Look for conflict markers (UU = both modified)
    lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
    conflicts = [line for line in lines if line.startswith('UU ') or line.startswith('AA ') or line.startswith('DD ')]

    if conflicts:
        conflict_files = [line[3:] for line in conflicts]
        return True, f"Conflicts in: {', '.join(conflict_files)}"

    return False, ""


def _delete_feature_branch(work_item_id: str) -> bool:
    """Delete the feature branch.

    Returns:
        True if successful, False otherwise
    """
    branch_name = f"ralph2/{work_item_id}"

    # First checkout main to avoid deleting the current branch
    _git_run(["git", "checkout", "main"])

    # Delete the branch
    result = _git_run(["git", "branch", "-D", branch_name])
    return result.returncode == 0


EXECUTOR_SYSTEM_PROMPT = """You are the Executor agent in the Temper multi-agent system.

Your ONLY job is to do the work assigned to you by the Planner.

## Your Responsibilities

1. Read the iteration intent to understand what you should work on
2. Read task details from Trace (trc show <id>) as needed
3. Do the work using the appropriate approach:
   - **Code work**: Write a failing test first, then make it pass
   - **Non-code work** (docs, research, configs): Do directly
4. Leave comments on tasks in Trace when:
   - You complete work on a task
   - You discover something important
   - You encounter a blocker
5. Note what you learned and any blockers

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
- One-off scripts explicitly marked as disposable

If unsure whether something needs a test: if it has behavior that can break, test it.

## Your Boundaries

- You DO NOT decide what to work on (the Planner does that)
- You DO NOT judge if the spec is satisfied (the Verifier does that)
- You DO the work: read, edit, test, comment

## Trace Commands for Executor

Use these commands via Bash to work with tasks:

**Viewing Tasks:**
- `trc show <id>` — Get task details including description and comments

**Leaving Comments:**
- `trc comment <id> "message" --source executor` — Leave a comment on a task

**When to Leave Comments:**
- After completing work on a task (what was done, any issues encountered)
- When you discover something important (unexpected behavior, missing dependencies, etc.)
- When you encounter a blocker (what's blocking you, what's needed to proceed)

**Closing Tasks:**
- `trc close <id>` — Mark a task as complete (only when fully finished)

**Key Rules:**
- Comments persist across iterations and are visible to the Planner
- Use comments to preserve context about your work
- Be specific about what you did and what you learned
- Always include `--source executor` when commenting

## Recognizing Verification Boundaries

Some work can be verified with tests you write (infrastructure/capability).
Some work requires real external systems to verify (behavior).

**Infrastructure work** (you can fully verify):
- API clients, data models, configuration loading
- Test with mocks—proves the plumbing works

**Behavioral work** (requires real systems to verify):
- Agent decision-making, classification accuracy
- LLM judgment calls, response quality
- These need real API credentials and test environments

When you complete infrastructure but cannot verify behavior:
- Report Status: **Blocked** (not Completed)
- Document exactly what resources are needed for behavioral verification
- This is correct and expected—not a failure

Example: "Infrastructure complete. Behavioral verification requires ANTHROPIC_API_KEY
and test Slack workspace. Tests written but skipped until credentials provided."

## Valid Exit Conditions

You should stop when ANY of these is true:
- **Completed**: You finished the assigned work AND it can be verified with available resources
- **Blocked**: You can't proceed—missing dependency, unclear requirement, OR behavioral verification needs external resources
- **Uncertain**: You're not sure if your approach is correct and need guidance

All three are valid and useful outcomes. Don't force completion.
Blocked for external dependencies is expected and correct—document what's needed.

## Output Format

End your response with a clear summary:

EXECUTOR_SUMMARY:
Status: [Completed | Blocked | Uncertain]
What was done: [brief description]
Blockers: [if any]
Notes: [anything learned or worth mentioning]
Efficiency Notes: [Insights that would save time in future iterations, or "None"]
"""


async def run_executor(
    iteration_intent: str,
    spec_content: str,
    memory: str = "",
    work_item_id: Optional[str] = None,
) -> dict:
    """
    Run the Executor agent.

    Args:
        iteration_intent: What the planner assigned for this iteration
        spec_content: The specification content (for reference)
        memory: Project memory content
        work_item_id: Optional work item ID from Trace (for parallel execution)

    Returns:
        dict with keys: 'status' (str), 'summary' (str), 'full_output' (str), 'efficiency_notes' (Optional[str])
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
        "5. End with: EXECUTOR_SUMMARY with status, what was done, blockers, and notes",
    ])

    prompt = "\n".join(prompt_parts)

    # Git isolation: Create feature branch if work_item_id is provided
    if work_item_id:
        if not _create_feature_branch(work_item_id):
            return {
                "status": "Blocked",
                "summary": f"EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Failed to create feature branch\nBlockers: Git branch creation failed for ralph2/{work_item_id}\nNotes: Cannot proceed without branch isolation\nEfficiency Notes: None",
                "full_output": "",
                "efficiency_notes": None,
                "messages": [],
            }

    # Run the executor agent
    full_output = []
    messages = []
    status = "Completed"  # Default
    summary = None

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
                permission_mode="bypassPermissions",
                system_prompt=EXECUTOR_SYSTEM_PROMPT,
            )
        ):
            # Save raw message
            messages.append(message.model_dump() if hasattr(message, "model_dump") else str(message))

            # Stream output to terminal
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"\033[36m{block.text}\033[0m")  # Cyan for text
                        full_output.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_info = f"▶ {block.name}"
                        if hasattr(block, 'input') and block.input:
                            if 'command' in block.input:
                                tool_info += f": {block.input['command'][:80]}"
                            elif 'file_path' in block.input:
                                tool_info += f": {block.input['file_path']}"
                        print(f"\033[33m{tool_info}\033[0m")  # Yellow for tools
            elif isinstance(message, ToolResultBlock):
                print(f"\033[32m  ✓\033[0m")  # Green checkmark for results

            # Look for the result
            if hasattr(message, "result"):
                result_text = message.result if isinstance(message.result, str) else str(message.result)
                full_output.append(result_text)
    except Exception as e:
        # Preserve partial output even if SDK throws late exception
        print(f"\033[33mWarning: Agent query ended with error: {e}\033[0m")

    # Extract the summary and status from the full output
    full_text = "\n".join(full_output)

    # Look for EXECUTOR_SUMMARY in the output
    summary_start = full_text.find("EXECUTOR_SUMMARY:")
    efficiency_notes = None

    if summary_start != -1:
        summary = full_text[summary_start:].strip()

        # Try to extract status and efficiency notes
        for line in summary.split("\n"):
            if line.startswith("Status:"):
                status_text = line.replace("Status:", "").strip()
                # Extract first word
                if "Completed" in status_text:
                    status = "Completed"
                elif "Blocked" in status_text:
                    status = "Blocked"
                elif "Uncertain" in status_text:
                    status = "Uncertain"
            elif line.startswith("Efficiency Notes:"):
                efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                # Treat explicit "None" as None
                if efficiency_notes == "None":
                    efficiency_notes = None
    else:
        # Fallback: create a summary
        summary = "EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work completed\n"

    # Git isolation: Handle merge/delete based on status
    if work_item_id:
        if status == "Completed":
            # Attempt to merge to main
            merge_success, merge_error = _merge_to_main(work_item_id)
            if not merge_success:
                # Merge failed - attempt resolution before abandoning
                print(f"\033[33m⚠ Merge conflict detected. Attempting resolution...\033[0m")

                # Build conflict resolution prompt
                conflict_prompt = f"""# Merge Conflict Resolution

You attempted to merge your work but encountered a merge conflict:

{merge_error}

## Your Task

1. Examine the conflicted files using git status and reading the files
2. Resolve the conflicts (edit files to remove conflict markers and fix the code)
3. Stage the resolved files with `git add <file>`
4. Complete the merge with `git commit` (it will use the default merge message)
5. Report status in EXECUTOR_SUMMARY

If you cannot resolve the conflicts, report Status: Blocked with details about why.
"""

                # Invoke agent for conflict resolution
                conflict_messages = []
                conflict_output = []
                resolution_status = "Blocked"  # Default to blocked

                try:
                    async for message in query(
                        prompt=conflict_prompt,
                        options=ClaudeAgentOptions(
                            allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
                            permission_mode="bypassPermissions",
                            system_prompt=EXECUTOR_SYSTEM_PROMPT,
                        )
                    ):
                        conflict_messages.append(message.model_dump() if hasattr(message, "model_dump") else str(message))

                        # Stream output
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, TextBlock):
                                    print(f"\033[36m{block.text}\033[0m")
                                    conflict_output.append(block.text)
                                elif isinstance(block, ToolUseBlock):
                                    tool_info = f"▶ {block.name}"
                                    if hasattr(block, 'input') and block.input:
                                        if 'command' in block.input:
                                            tool_info += f": {block.input['command'][:80]}"
                                        elif 'file_path' in block.input:
                                            tool_info += f": {block.input['file_path']}"
                                    print(f"\033[33m{tool_info}\033[0m")
                        elif isinstance(message, ToolResultBlock):
                            print(f"\033[32m  ✓\033[0m")

                        if hasattr(message, "result"):
                            result_text = message.result if isinstance(message.result, str) else str(message.result)
                            conflict_output.append(result_text)
                except Exception as e:
                    print(f"\033[33mWarning: Conflict resolution agent ended with error: {e}\033[0m")

                # Check resolution result
                conflict_text = "\n".join(conflict_output)
                resolution_summary_start = conflict_text.find("EXECUTOR_SUMMARY:")

                if resolution_summary_start != -1:
                    resolution_summary = conflict_text[resolution_summary_start:].strip()
                    for line in resolution_summary.split("\n"):
                        if line.startswith("Status:"):
                            status_text = line.replace("Status:", "").strip()
                            if "Completed" in status_text:
                                resolution_status = "Completed"
                            elif "Blocked" in status_text:
                                resolution_status = "Blocked"
                            elif "Uncertain" in status_text:
                                resolution_status = "Uncertain"

                # If resolution succeeded, retry merge
                if resolution_status == "Completed":
                    # Check if conflicts are actually resolved
                    has_conflicts, conflict_info = _check_merge_conflicts()
                    if not has_conflicts:
                        # Conflicts resolved - retry merge
                        merge_success, merge_error = _merge_to_main(work_item_id)

                # Final status check
                if not merge_success:
                    # Resolution failed - abandon branch
                    status = "Blocked"
                    summary = f"EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Work completed but merge conflict resolution failed\nBlockers: {merge_error}\nNotes: Attempted automatic conflict resolution but failed. Feature branch ralph2/{work_item_id} abandoned.\nEfficiency Notes: {efficiency_notes or 'None'}"
                    _delete_feature_branch(work_item_id)
                else:
                    # Resolution succeeded!
                    print(f"\033[32m✓ Merge conflicts resolved and merged successfully\033[0m")
        else:
            # Status is Blocked or Uncertain - abandon the branch
            _delete_feature_branch(work_item_id)
            # Update summary to note branch abandonment
            if "Efficiency Notes:" not in summary:
                summary += f"\nNotes: Feature branch ralph2/{work_item_id} abandoned due to {status} status"

    return {
        "status": status,
        "summary": summary,
        "full_output": full_text,
        "efficiency_notes": efficiency_notes,
        "messages": messages,
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
    print("Status:", result["status"])
    print("\nSummary:")
    print(result["summary"])
    print("\nFull Output:")
    print(result["full_output"])


if __name__ == "__main__":
    asyncio.run(main())
