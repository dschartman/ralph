"""Planner agent: Maintain plan and decide what to work on next."""

import asyncio
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage

from ralph2.agents.models import PlannerResult
from ralph2.agents.streaming import stream_agent_output
from ralph2.agents.constants import AGENT_MODEL


PLANNER_SYSTEM_PROMPT = """You are the Planner agent in the Ralph2 multi-agent system.

Your job is to maintain a plan, decide what to work on next, and determine when to continue/stop.

## Your Responsibilities

1. Curate project memory (if feedback contains efficiency notes):
   - Read current memory
   - Extract efficiency notes from executor/verifier/specialist feedback
   - Add valuable new insights to memory
   - Deduplicate similar entries
   - Remove stale/outdated entries
   - Keep memory concise (quick reference, not documentation)
   - Write updated memory back to memory.md

2. Read the spec to understand the goal

3. Review current task state in Trace (trc list, trc show)

4. Review feedback from the last iteration:
   - Executor summary (what was done)
   - Verifier assessment (spec compliance check)
   - Specialist feedback (code quality, maintainability)

5. Update tasks in Trace if needed:
   - Create new tasks if gaps are found (from Verifier or Specialists)
   - Break down tasks that are too large into testable pieces
   - Close tasks that are complete
   - Reprioritize based on what you've learned

6. Make termination decision: CONTINUE, DONE, or STUCK

7. Plan iteration work (if CONTINUE)

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

## Priority Scale

Trace uses a 0-4 priority scale that guides your planning decisions:

- **Critical (P0)**: MUST be addressed before declaring DONE. Blocks spec completion.
- **High (P1)**: MUST be addressed before declaring DONE. Required for spec satisfaction.
- **Medium (P2)**: Default priority. Address at your discretion based on impact and feasibility.
- **Low (P3)**: MAY be deferred. Nice-to-have improvements.
- **Backlog (P4)**: MAY be deferred. Future work or ideas.

**Your Discretion**: You have flexibility with Medium (P2) and below. Focus on Critical/High priorities first, then tackle Medium work that moves the spec forward. Low and Backlog items can remain unaddressed—not everything needs to be completed.

## Project Memory Management

Project memory is accumulated knowledge about how to work efficiently in this project. It persists across iterations and runs.

**Location:** `~/.ralph2/projects/<project-id>/memory.md`

**When to Curate:**
- At the start of each iteration (if feedback contains efficiency notes)
- Do this BEFORE reviewing tasks or planning work

**What Makes Good Memory:**
- **Actionable** — tells you what to DO, not what happened
- **Efficiency-focused** — saves discovery/exploration time
- **Project-specific** — not general knowledge
- **Concise** — one line, scannable
- **Durable** — true across iterations, not ephemeral state

**The test:** Would this save an agent 2+ tool calls next iteration? If yes, it's good memory.

## Milestone Completion

When you decide DONE, you MUST complete the milestone by organizing remaining work:

**Your Milestone Completion Steps:**
1. Read all open children under the root work item using `trc tree <root-id>`
2. If no open children exist, skip to step 6
3. Categorize remaining work into logical groups (max 5 categories)
4. For each category with items, create a new parent work item
5. Reparent each open child to its appropriate category parent
6. Close the root work item using `trc close <root-id>`

## Termination Decision

After reviewing all feedback, you MUST decide:

**CONTINUE** = There is implementable work remaining
- Verifier reports spec_satisfied is "no" or "partially" with gaps that can be addressed
- Specialists found issues that can be fixed
- Tasks remain in the backlog
- Use CONTINUE even if some work is blocked—as long as there's other work to do

**DONE** = Spec is satisfied AND no critical work remains
- Verifier reports spec_satisfied: "yes" (all criteria verified satisfied)
- All critical/high priority tasks are complete
- Specialists found no critical issues (or they're all resolved)
- Spec acceptance criteria are fully met

**STUCK** = Cannot make progress without external input
- Verifier reports spec_satisfied: "unverifiable" AND there's no other implementable work
- Every remaining task requires external resources (credentials, clarification, access)
- No implementable work is left
- You must specify what's blocking progress and what's needed to unblock

**Using Verifier Assessment:**
The Verifier reports spec_satisfied as: yes, no, partially, or unverifiable
- "yes" → All criteria satisfied → Consider DONE (if no critical work remains)
- "partially" → Some criteria satisfied → CONTINUE (address gaps)
- "no" → Criteria not satisfied → CONTINUE (implement requirements)
- "unverifiable" → Cannot determine → Check if other work is possible (CONTINUE) or blocked (STUCK)

**The key distinction:**
- Can work be done with what we have? → CONTINUE
- Is the spec satisfied (verifier says "yes") and no critical work remains? → DONE
- Is every remaining task blocked by external dependencies? → STUCK
"""


async def run_planner(
    spec_content: str,
    last_executor_summary: Optional[str] = None,
    last_verifier_assessment: Optional[str] = None,
    last_specialist_feedback: Optional[str] = None,
    human_inputs: Optional[list[str]] = None,
    memory: str = "",
    project_id: Optional[str] = None,
    root_work_item_id: Optional[str] = None,
) -> dict:
    """
    Run the Planner agent.

    Args:
        spec_content: The specification content
        last_executor_summary: Summary from the last executor run (if any)
        last_verifier_assessment: Assessment from the last verifier run (if any)
        last_specialist_feedback: Feedback from specialists (if any)
        human_inputs: List of human input messages (if any)
        memory: Project memory content
        project_id: The project UUID (needed for memory file path)
        root_work_item_id: Root work item ID (spec milestone in Trace)

    Returns:
        dict with keys: 'result' (PlannerResult), 'full_output' (str), 'messages' (list)
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

    # Add root work item ID if available
    if root_work_item_id:
        prompt_parts.append("# Root Work Item")
        prompt_parts.append("")
        prompt_parts.append(f"Root work item ID: `{root_work_item_id}`")
        prompt_parts.append("")
        prompt_parts.append("(Use this ID for milestone completion when declaring DONE)")
        prompt_parts.append("")
        prompt_parts.append("---")
        prompt_parts.append("")

    # Add memory section (even if empty, so planner knows about memory system)
    prompt_parts.append("# Project Memory")
    prompt_parts.append("")
    if project_id:
        from ralph2.project import get_memory_path
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

    if last_executor_summary or last_verifier_assessment or last_specialist_feedback:
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

        if last_specialist_feedback:
            prompt_parts.append("## Specialist Feedback")
            prompt_parts.append("")
            prompt_parts.append(last_specialist_feedback)
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
        "4. Review Verifier assessment and Specialist feedback",
        "5. Update tasks as needed (create, close, update descriptions based on feedback)",
        "6. Make termination decision: CONTINUE, DONE, or STUCK",
        "7. If DONE, complete the milestone (organize remaining work, close root)",
        "8. If CONTINUE, decide what should be worked on in this iteration",
    ])

    prompt = "\n".join(prompt_parts)

    # Configure the agent with structured output
    options = ClaudeAgentOptions(
        model=AGENT_MODEL,
        allowed_tools=["Bash", "Read", "Write"],
        permission_mode="bypassPermissions",
        system_prompt=PLANNER_SYSTEM_PROMPT,
        output_format={
            "type": "json_schema",
            "schema": PlannerResult.model_json_schema()
        }
    )

    # Run the planner agent
    full_output = []
    messages = []
    result: Optional[PlannerResult] = None

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
                    result = PlannerResult.model_validate(message.structured_output)
                    print(f"\033[32m✓ Planner decision: {result.decision}\033[0m")
                elif message.subtype == "error_max_structured_output_retries":
                    print(f"\033[31m✗ Failed to get structured output after retries\033[0m")

    full_text = "\n".join(full_output)

    # If we didn't get a valid result, create a default
    if result is None:
        print(f"\033[33mWarning: No structured output received, using default CONTINUE\033[0m")
        result = PlannerResult(
            decision="CONTINUE",
            reason="No structured output received from planner, defaulting to CONTINUE",
            iteration_intent="Continue working on tasks"
        )

    return {
        "result": result,
        "full_output": full_text,
        "messages": messages,
        # Legacy fields for backward compatibility
        "intent": result.iteration_intent,
        "decision": {
            "decision": result.decision,
            "reason": result.reason,
            "blocker": result.blocker,
        },
        "iteration_plan": result.iteration_plan.model_dump() if result.iteration_plan else None,
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
    print("\nResult:", result["result"])
    print("\nIntent:", result["intent"])
    print("\nDecision:", result["decision"])


if __name__ == "__main__":
    asyncio.run(main())
