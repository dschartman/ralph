"""Planner agent: Maintain plan and decide what to work on next."""

import asyncio
from typing import Optional
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


PLANNER_SYSTEM_PROMPT = """You are the Planner agent in the Ralph multi-agent system.

Your ONLY job is to maintain a plan and decide what to work on next.

## Your Responsibilities

1. Curate project memory (if feedback contains efficiency notes):
   - Read current memory
   - Extract efficiency notes from executor/verifier feedback
   - Add valuable new insights to memory
   - Deduplicate similar entries
   - Remove stale/outdated entries
   - Keep memory concise (quick reference, not documentation)
   - Write updated memory back to memory.md
2. Read the spec to understand the goal
3. Review current task state in Trace (trc list, trc show)
4. Review feedback from the last iteration (executor summary, verifier assessment)
5. Update tasks in Trace if needed:
   - Create new tasks if gaps are found (including test gaps flagged by Verifier)
   - Break down tasks that are too large into testable pieces
   - Close tasks that are complete
   - Reprioritize based on what you've learned
6. Output iteration intent: What should be worked on in this iteration?

## Task Decomposition

When breaking down work:
- **Testable pieces**: Each task should have a verifiable outcome
- **Integration boundaries**: Separate tasks at natural seams (API endpoints, module boundaries, I/O operations)
- **Respond to Verifier feedback**: If Verifier recommends acceptance tests, incorporate them as tasks

Don't prescribe specific tests—that's the Executor's job. Your job is to create tasks with clear, testable outcomes.

## Your Boundaries

- You DO NOT do the work yourself
- You DO NOT judge if the spec is satisfied (that's the Verifier's job)
- You DO decide what tasks to create/update and what to work on next

## Trace Commands Reference

Use these commands via Bash to manage tasks:

**Viewing Tasks:**
- `trc ready` — Show unblocked tasks ready to work on (START HERE)
- `trc list` — Show full backlog (excludes closed tasks)
- `trc show <id>` — Show task details including description and comments

**Creating Tasks:**
- `trc create "title" --description "context"` — Create a new task (--description is REQUIRED)
- `trc create "subtask" --description "details" --parent <id>` — Create a subtask under a parent task

**Closing Tasks:**
- `trc close <id>` — Mark a task as complete

**Key Rules:**
- Always use `--description` when creating tasks (preserves context across iterations)
- Use `trc ready` to see what's actually workable (not blocked)
- Use `--parent <id>` to create hierarchical task breakdowns
- Comments from executor are visible in `trc show <id>`

## Project Memory Management

Project memory is accumulated knowledge about how to work efficiently in this project. It persists across iterations and runs.

**Location:** `~/.ralph/projects/<project-id>/memory.md`

**When to Curate:**
- At the start of each iteration (if feedback contains efficiency notes)
- Do this BEFORE reviewing tasks or planning work

**What Makes Good Memory:**
- **Actionable** — tells you what to DO, not what happened
- **Efficiency-focused** — saves discovery/exploration time
- **Project-specific** — not general knowledge
- **Concise** — one line, scannable
- **Durable** — true across iterations, not ephemeral state

**Examples of GOOD entries:**
```
- Use UV for packages: `uv run pytest`, `uv add <pkg>` (not pip)
- Tests live in tests/, run with `uv run pytest -v`
- State stored in ~/.ralph/projects/<uuid>/, not local .ralph/
- Use Grep tool for code search instead of bash grep
- trc ready shows unblocked tasks, trc list shows all
```

**Examples of BAD entries:**
```
- The project uses Python  # too obvious
- I ran 15 bash commands  # logging, not actionable
- Tests passed  # ephemeral state
- Task ralph-xyz completed  # Trace's job
```

**The test:** Would this save an agent 2+ tool calls next iteration? If yes, it's good memory.

**Curation Process:**
1. Read current memory from `~/.ralph/projects/<project-id>/memory.md`
2. Check feedback for "Efficiency Notes:" sections
3. Add valuable new insights in the same concise format
4. Remove duplicates (keep the most complete version)
5. Remove stale/outdated entries
6. Write updated memory back using Write tool
7. Note what memory changes you made in your output

## Output Format

End your response with a clear iteration intent:

ITERATION_INTENT: [1-2 sentence description of what should be worked on this iteration]

Be specific about which tasks or areas should be addressed.
"""


async def run_planner(
    spec_content: str,
    last_executor_summary: Optional[str] = None,
    last_verifier_assessment: Optional[str] = None,
    human_inputs: Optional[list[str]] = None,
    memory: str = "",
    project_id: Optional[str] = None,
) -> dict:
    """
    Run the Planner agent.

    Args:
        spec_content: The specification content
        last_executor_summary: Summary from the last executor run (if any)
        last_verifier_assessment: Assessment from the last verifier run (if any)
        human_inputs: List of human input messages (if any)
        memory: Project memory content
        project_id: The project UUID (needed for memory file path)

    Returns:
        dict with keys: 'intent' (str), 'full_output' (str)
    """
    # Build the prompt
    prompt_parts = [
        "# Spec",
        "",
        spec_content,
        "",
        "---",
        "",
    ]

    # Add memory section (even if empty, so planner knows about memory system)
    prompt_parts.append("# Project Memory")
    prompt_parts.append("")
    if project_id:
        from ralph.project import get_memory_path
        memory_path = get_memory_path(project_id)
        prompt_parts.append(f"Memory file: `{memory_path}`")
        prompt_parts.append("")
    if memory:
        prompt_parts.append("Current memory content:")
        prompt_parts.append("")
        prompt_parts.append(memory)
    else:
        prompt_parts.append("(No memory entries yet)")
    prompt_parts.append("")
    prompt_parts.append("---")
    prompt_parts.append("")

    if human_inputs:
        prompt_parts.append("# Human Input")
        prompt_parts.append("")
        for input_msg in human_inputs:
            prompt_parts.append(f"- {input_msg}")
        prompt_parts.append("")
        prompt_parts.append("---")
        prompt_parts.append("")

    if last_executor_summary or last_verifier_assessment:
        prompt_parts.append("# Feedback from Last Iteration")
        prompt_parts.append("")

        if last_executor_summary:
            prompt_parts.append("## Executor Summary")
            prompt_parts.append("")
            prompt_parts.append(last_executor_summary)
            prompt_parts.append("")

        if last_verifier_assessment:
            prompt_parts.append("## Verifier Assessment")
            prompt_parts.append("")
            prompt_parts.append(last_verifier_assessment)
            prompt_parts.append("")

        prompt_parts.append("---")
        prompt_parts.append("")

    prompt_parts.extend([
        "# Your Task",
        "",
        "1. If feedback contains efficiency notes, curate project memory:",
        "   - Read current memory.md",
        "   - Add new insights from efficiency notes",
        "   - Deduplicate and remove stale entries",
        "   - Write updated memory back",
        "2. Run `trc list` to see all tasks",
        "3. Run `trc show <id>` on any tasks you need more detail on",
        "4. Update tasks as needed (create, close, update descriptions)",
        "5. Decide what should be worked on in this iteration",
        "6. End with: ITERATION_INTENT: [your intent]",
    ])

    prompt = "\n".join(prompt_parts)

    # Run the planner agent
    full_output = []
    messages = []
    intent = None

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Bash", "Read", "Write"],
                permission_mode="bypassPermissions",
                system_prompt=PLANNER_SYSTEM_PROMPT,
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
                # Extract intent from the result
                result_text = message.result if isinstance(message.result, str) else str(message.result)
                full_output.append(result_text)
    except Exception as e:
        # Preserve partial output even if SDK throws late exception
        print(f"\033[33mWarning: Agent query ended with error: {e}\033[0m")

    # Extract the intent from the full output
    full_text = "\n".join(full_output)

    # Look for ITERATION_INTENT in the output
    for line in full_text.split("\n"):
        if line.startswith("ITERATION_INTENT:"):
            intent = line.replace("ITERATION_INTENT:", "").strip()
            break

    if not intent:
        # Fallback: use the last non-empty line
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        if lines:
            intent = lines[-1]
        else:
            intent = "Continue working on tasks"

    return {
        "intent": intent,
        "full_output": full_text,
        "messages": messages,
    }


async def main():
    """Test the planner agent."""
    spec = """
    # Test Spec

    Build a simple hello world Python script.

    ## Acceptance Criteria
    - [ ] Python script that prints "Hello, World!"
    - [ ] Script is executable
    """

    result = await run_planner(spec_content=spec)
    print("Intent:", result["intent"])
    print("\nFull Output:")
    print(result["full_output"])


if __name__ == "__main__":
    asyncio.run(main())
