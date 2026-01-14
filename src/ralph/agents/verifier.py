"""Verifier agent: Determine if spec is satisfied."""

import asyncio
from typing import Optional

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


VERIFIER_SYSTEM_PROMPT = """You are the Verifier. Your ONE job: determine if the spec is satisfied.

## What You Do

1. Find ALL acceptance criteria in the spec (look for [ ] and [x] checkboxes)
2. For each criterion, verify it against reality
3. DONE = EVERY criterion is verified satisfied. No exceptions.

## Verification Requires Observation

You can only verify what you can observe. If verification requires external
resources (API credentials, test environments, external services), you cannot
verify—you can only note that verification is blocked.

**Capability vs. Behavior:**
- "System CAN create stories" = capability = verify with unit tests, code inspection
- "Agent classifies X as Y" = behavior = requires real agent execution to verify
- "Agent uses judgment to..." = behavior = requires real agent execution to verify

**For behavioral criteria:**
- Mocked tests prove infrastructure works, NOT that behavior is correct
- Tests that mock LLM responses do NOT verify agent decision-making
- If the test pre-programs what the agent "would" do, it's not behavioral verification

If you cannot observe the actual behavior, the criterion is UNVERIFIABLE with
current resources—not satisfied, not unsatisfied, UNVERIFIABLE.

## Verification Approach

Prefer automated evidence over manual checks:
- Run existing tests, type checkers, linters where available
- For capability criteria: if tests pass and cover the criterion → trust them
- For behavioral criteria: only trust tests that use real external systems (not mocked)
- If no automated evidence → verify manually (read code, run commands, inspect output)

## When to Use STUCK

Use STUCK (not CONTINUE) when:
- Criteria require external resources that are not available
- You've confirmed infrastructure works but cannot verify behavior
- Further iterations cannot produce verification without external input

STUCK is the correct response to external dependency blockers.
CONTINUE would create an infinite loop (no new information will appear).
DONE would be dishonest (unverified ≠ verified).

## Output Format

VERIFIER_ASSESSMENT:
Outcome: [DONE | CONTINUE | STUCK]
Criteria Status:
- [criterion]: ✓ satisfied / ✗ not satisfied / ⊘ unverifiable (evidence)
...
Gaps (if CONTINUE): [list unsatisfied criteria by name]
Blocker (if STUCK): [specific resources needed]
Required Configuration (if STUCK):
- [credential or resource 1]
- [credential or resource 2]
Recommendation (if STUCK): [how user should provide these to unblock]
Efficiency Notes: [Insights that would save time in future iterations, or "None"]

## Rules

- DONE requires 100% of acceptance criteria VERIFIED satisfied
- Unverifiable criteria block DONE—use STUCK with clear requirements
- Partial completion = CONTINUE
- External dependency blockers = STUCK (not CONTINUE)
- "Good enough" is not DONE
- "Looks done" is not DONE—only "is done" counts
- The spec is the contract. Verify literally.
- You do NOT know what was "worked on" — you only see the spec and current state
- Hold the line. Be stubborn. That's your job.
"""


def parse_verifier_output(full_text: str) -> dict:
    """
    Parse verifier output to extract outcome, assessment, and efficiency notes.

    Handles markdown formatting (e.g., **Outcome: DONE**).

    Args:
        full_text: The full output text from the verifier agent

    Returns:
        dict with keys: 'outcome', 'assessment', 'efficiency_notes'
    """
    outcome = "CONTINUE"  # Default
    assessment = None
    efficiency_notes = None

    # Look for VERIFIER_ASSESSMENT in the output
    assessment_start = full_text.find("VERIFIER_ASSESSMENT:")

    if assessment_start != -1:
        assessment = full_text[assessment_start:].strip()

        # Try to extract outcome and efficiency notes
        for line in assessment.split("\n"):
            # Strip markdown bold markers (model sometimes outputs **Outcome: DONE**)
            clean_line = line.strip().strip("*")
            if "Outcome:" in clean_line:
                outcome_text = clean_line.split("Outcome:", 1)[1].strip().strip("*")
                # Extract the outcome
                if "DONE" in outcome_text:
                    outcome = "DONE"
                elif "STUCK" in outcome_text:
                    outcome = "STUCK"
                elif "CONTINUE" in outcome_text:
                    outcome = "CONTINUE"
            elif "Efficiency Notes:" in clean_line:
                efficiency_notes = clean_line.split("Efficiency Notes:", 1)[1].strip().strip("*").strip()
                # Treat explicit "None" as None
                if efficiency_notes == "None":
                    efficiency_notes = None
    else:
        # Fallback: create an assessment
        assessment = "VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nReasoning: Verification incomplete\n"

    return {
        "outcome": outcome,
        "assessment": assessment,
        "efficiency_notes": efficiency_notes,
    }


async def run_verifier(
    spec_content: str,
    memory: str = "",
) -> dict:
    """
    Run the Verifier agent.

    Args:
        spec_content: The specification content
        memory: Project memory content

    Returns:
        dict with keys: 'outcome' (str), 'assessment' (str), 'full_output' (str), 'efficiency_notes' (Optional[str])
    """
    # Build the prompt - Verifier only sees spec, no iteration context
    prompt_parts = [
        "# Spec",
        "",
        spec_content,
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
        "# Your Task",
        "",
        "1. Find ALL acceptance criteria in the spec ([ ] and [x] checkboxes)",
        "2. For each criterion, verify it against reality",
        "3. DONE only if EVERY criterion is satisfied",
        "4. End with: VERIFIER_ASSESSMENT listing each criterion's status",
    ])

    prompt = "\n".join(prompt_parts)

    # Run the verifier agent
    full_output = []
    messages = []
    outcome = "CONTINUE"  # Default
    assessment = None

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Bash", "Glob", "Grep"],
                permission_mode="bypassPermissions",
                system_prompt=VERIFIER_SYSTEM_PROMPT,
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

    # Extract the assessment and outcome from the full output
    full_text = "\n".join(full_output)
    parsed = parse_verifier_output(full_text)

    return {
        "outcome": parsed["outcome"],
        "assessment": parsed["assessment"],
        "full_output": full_text,
        "efficiency_notes": parsed["efficiency_notes"],
        "messages": messages,
    }


async def main():
    """Test the verifier agent."""
    spec = """
    # Test Spec

    Build a simple hello world Python script.

    ## Acceptance Criteria
    - [ ] Python script that prints "Hello, World!"
    - [ ] Script is executable
    """

    result = await run_verifier(spec_content=spec)
    print("Outcome:", result["outcome"])
    print("\nAssessment:")
    print(result["assessment"])
    print("\nFull Output:")
    print(result["full_output"])


if __name__ == "__main__":
    asyncio.run(main())
