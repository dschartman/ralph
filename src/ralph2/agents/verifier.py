"""Verifier agent: Determine if spec is satisfied."""

import asyncio
import subprocess
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage

from ralph2.agents.models import VerifierResult
from ralph2.agents.streaming import stream_agent_output
from ralph2.agents.constants import AGENT_MODEL


VERIFIER_SYSTEM_PROMPT = """You are the Verifier. Your ONE job: assess whether the spec is satisfied.

## Your Role

You are an ASSESSOR, not a decision-maker. You determine the current state of spec satisfaction.
The Planner decides what to do next based on your assessment.

## What You Do

1. Find ALL acceptance criteria in the spec (look for [ ] and [x] checkboxes)
2. For each criterion, verify it against reality
3. Report which are satisfied, not satisfied, or unverifiable
4. Count and summarize the results

## Verification Requires Observation

You can only verify what you can observe. If verification requires external
resources (API credentials, test environments, external services), mark that
criterion as UNVERIFIABLE.

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

## Spec Satisfaction Assessment

After checking all criteria, report:

- **yes** = ALL criteria are verified satisfied (100%)
- **partially** = SOME criteria satisfied, some not satisfied or unverifiable
- **no** = NO criteria are satisfied (or critical criteria are not met)
- **unverifiable** = Cannot determine satisfaction (all criteria require external resources)

## Rules

- Be objective. Report what IS, not what should be.
- "Good enough" is not "yes" — only 100% satisfaction is "yes"
- "Looks done" is not verified — only observed evidence counts
- The spec is the contract. Verify literally.
- You do NOT know what was "worked on" — you only see the spec and current state
- Hold the line. Be stubborn. That's your job.

## What You Do NOT Do

- You do NOT decide CONTINUE/DONE/STUCK (that's the Planner's job)
- You do NOT recommend next steps (that's the Planner's job)
- You ONLY assess and report the current state of spec satisfaction

## Efficiency Notes

After verification, note what would help verify this spec faster next time:

**Ask yourself:** "What shortcut would I tell another verifier?"

Good efficiency notes are:
- **Verification shortcuts**: "Run `uv run pytest -v` to check all test criteria at once"
- **Evidence locations**: "CLI criteria can be verified with `--help` flags"
- **Gotchas discovered**: "Config validation only triggers when .env is missing, not when vars are empty"

Examples:
- "All 9 review categories are defined in models.py:ReviewCategory enum"
- "Integration test at tests/test_integration.py covers the real MR scenario"
- "Retry logic is in gitlab_client.py with @retry decorators - grep for them"

Fill in the `efficiency_notes` field with 1-2 concrete verification insights.
"""


async def run_verifier(
    spec_content: str,
    memory: str = "",
    root_work_item_id: Optional[str] = None,
) -> dict:
    """
    Run the Verifier agent.

    Args:
        spec_content: The specification content
        memory: Project memory content
        root_work_item_id: Optional root work item ID to post verdict as comment

    Returns:
        dict with keys: 'result' (VerifierResult), 'full_output' (str), 'messages' (list)
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
    ])

    prompt = "\n".join(prompt_parts)

    # Configure the agent with structured output
    options = ClaudeAgentOptions(
        model=AGENT_MODEL,
        allowed_tools=["Read", "Bash", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt=VERIFIER_SYSTEM_PROMPT,
        output_format={
            "type": "json_schema",
            "schema": VerifierResult.model_json_schema()
        }
    )

    # Run the verifier agent
    full_output = []
    messages = []
    result: Optional[VerifierResult] = None

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
                    result = VerifierResult.model_validate(message.structured_output)
                    print(f"\033[32m✓ Verifier assessment: spec_satisfied={result.spec_satisfied} ({result.satisfied_count}/{result.total_count} criteria)\033[0m")
                elif message.subtype == "error_max_structured_output_retries":
                    print(f"\033[31m✗ Failed to get structured output after retries\033[0m")

    full_text = "\n".join(full_output)

    # If we didn't get a valid result, create a default
    if result is None:
        print(f"\033[33mWarning: No structured output received, using default unverifiable\033[0m")
        result = VerifierResult(
            spec_satisfied="unverifiable",
            criteria_status=[],
            satisfied_count=0,
            total_count=0,
            gaps=["No structured output received from verifier"]
        )

    # Post assessment as comment on root work item if provided
    if root_work_item_id:
        # Build a human-readable assessment
        assessment_lines = [f"Spec Satisfied: {result.spec_satisfied} ({result.satisfied_count}/{result.total_count} criteria)"]
        assessment_lines.append("Criteria Status:")
        for cs in result.criteria_status:
            status_symbol = "✓" if cs.status == "satisfied" else ("✗" if cs.status == "not_satisfied" else "⊘")
            assessment_lines.append(f"- [{status_symbol}] {cs.criterion}: {cs.evidence}")
        if result.gaps:
            assessment_lines.append(f"Gaps: {', '.join(result.gaps)}")
        if result.unverifiable_criteria:
            assessment_lines.append(f"Unverifiable: {', '.join(result.unverifiable_criteria)}")
        if result.efficiency_notes:
            assessment_lines.append(f"Efficiency Notes: {result.efficiency_notes}")

        comment_text = "\n".join(assessment_lines)

        try:
            # Use trc comment to post the assessment
            proc_result = subprocess.run(
                ["trc", "comment", root_work_item_id, comment_text, "--source", "verifier"],
                capture_output=True,
                text=True,
                check=False
            )
            if proc_result.returncode == 0:
                print(f"\033[32m✓ Posted assessment to {root_work_item_id}\033[0m")
            else:
                print(f"\033[33mWarning: Failed to post assessment comment: {proc_result.stderr}\033[0m")
        except Exception as e:
            print(f"\033[33mWarning: Failed to post assessment comment: {e}\033[0m")

    # Build assessment string for runner consumption
    assessment_lines = [f"Spec Satisfied: {result.spec_satisfied} ({result.satisfied_count}/{result.total_count} criteria)"]
    assessment_lines.append("Criteria Status:")
    for cs in result.criteria_status:
        status_symbol = "✓" if cs.status == "satisfied" else ("✗" if cs.status == "not_satisfied" else "⊘")
        assessment_lines.append(f"- {cs.criterion}: {status_symbol} {cs.status} ({cs.evidence})")
    if result.gaps:
        assessment_lines.append(f"Gaps: {', '.join(result.gaps)}")
    if result.unverifiable_criteria:
        assessment_lines.append(f"Unverifiable: {', '.join(result.unverifiable_criteria)}")
    if result.efficiency_notes:
        assessment_lines.append(f"Efficiency Notes: {result.efficiency_notes}")

    return {
        "result": result,
        "full_output": full_text,
        "messages": messages,
        # Fields for runner/planner consumption
        "spec_satisfied": result.spec_satisfied,
        "assessment": "\n".join(assessment_lines),
        "efficiency_notes": result.efficiency_notes,
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
    print("\nResult:", result["result"])
    print("\nSpec Satisfied:", result["spec_satisfied"])
    print("\nAssessment:")
    print(result["assessment"])


if __name__ == "__main__":
    asyncio.run(main())
