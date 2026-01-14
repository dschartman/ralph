"""Executor agent: Do the assigned work."""

import asyncio
from typing import Optional

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


EXECUTOR_SYSTEM_PROMPT = """You are the Executor agent in the Ralph multi-agent system.

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
) -> dict:
    """
    Run the Executor agent.

    Args:
        iteration_intent: What the planner assigned for this iteration
        spec_content: The specification content (for reference)
        memory: Project memory content

    Returns:
        dict with keys: 'status' (str), 'summary' (str), 'full_output' (str), 'efficiency_notes' (Optional[str])
    """
    # Build the prompt
    prompt_parts = [
        "# Iteration Intent",
        "",
        iteration_intent,
        "",
        "---",
        "",
    ]

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
