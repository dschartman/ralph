"""Verifier agent: Determine if spec is satisfied."""

import asyncio
import subprocess
from typing import Optional

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage

from ralph2.agents.models import VerifierResult
from ralph2.agents.streaming import stream_agent_output
from ralph2.agents.constants import AGENT_MODEL


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

## Choosing the Outcome

**CONTINUE** = There is still implementable work to do
- Some criteria are not satisfied AND can be implemented
- Use CONTINUE even if some criteria are unverifiable—as long as there's other work to do

**STUCK** = ALL remaining work requires external blockers
- Every unsatisfied criterion requires something the executor cannot provide (credentials, human decisions, external access)
- There is NO implementable work left—only blocked work
- STUCK means "I literally cannot make progress without external input"

**DONE** = Every criterion is verified satisfied
- 100% of acceptance criteria are verified (not assumed, not mocked—verified)

**The key distinction:**
- "Can't verify behavior YET" + "other work remains" = CONTINUE
- "Can't verify behavior" + "no other work possible" = STUCK
- If the CLI isn't built, the integration test isn't written, or reports aren't being saved—that's implementable work. Use CONTINUE.

## Rules

- DONE requires 100% of acceptance criteria VERIFIED satisfied
- Partial completion = CONTINUE (there's work to do)
- Unverifiable criteria do NOT automatically mean STUCK—only if there's no other implementable work
- STUCK requires ALL remaining work to be blocked by external dependencies
- "Good enough" is not DONE
- "Looks done" is not DONE—only "is done" counts
- The spec is the contract. Verify literally.
- You do NOT know what was "worked on" — you only see the spec and current state
- Hold the line. Be stubborn. That's your job.
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
                    print(f"\033[32m✓ Verifier outcome: {result.outcome}\033[0m")
                elif message.subtype == "error_max_structured_output_retries":
                    print(f"\033[31m✗ Failed to get structured output after retries\033[0m")

    full_text = "\n".join(full_output)

    # If we didn't get a valid result, create a default
    if result is None:
        print(f"\033[33mWarning: No structured output received, using default CONTINUE\033[0m")
        result = VerifierResult(
            outcome="CONTINUE",
            criteria_status=[],
            gaps=["No structured output received from verifier"]
        )

    # Post verdict as comment on root work item if provided
    if root_work_item_id:
        # Build a human-readable assessment
        assessment_lines = [f"Outcome: {result.outcome}"]
        assessment_lines.append("Criteria Status:")
        for cs in result.criteria_status:
            status_symbol = "✓" if cs.status == "satisfied" else ("✗" if cs.status == "not_satisfied" else "⊘")
            assessment_lines.append(f"- [{status_symbol}] {cs.criterion}: {cs.evidence}")
        if result.gaps:
            assessment_lines.append(f"Gaps: {', '.join(result.gaps)}")
        if result.blocker:
            assessment_lines.append(f"Blocker: {result.blocker}")
        if result.efficiency_notes:
            assessment_lines.append(f"Efficiency Notes: {result.efficiency_notes}")

        comment_text = "\n".join(assessment_lines)

        try:
            # Use trc comment to post the verdict
            proc_result = subprocess.run(
                ["trc", "comment", root_work_item_id, comment_text, "--source", "verifier"],
                capture_output=True,
                text=True,
                check=False
            )
            if proc_result.returncode == 0:
                print(f"\033[32m✓ Posted verdict to {root_work_item_id}\033[0m")
            else:
                print(f"\033[33mWarning: Failed to post verdict comment: {proc_result.stderr}\033[0m")
        except Exception as e:
            print(f"\033[33mWarning: Failed to post verdict comment: {e}\033[0m")

    # Build legacy assessment string for backward compatibility
    legacy_assessment_lines = [f"Outcome: {result.outcome}"]
    legacy_assessment_lines.append("Criteria Status:")
    for cs in result.criteria_status:
        status_symbol = "✓" if cs.status == "satisfied" else ("✗" if cs.status == "not_satisfied" else "⊘")
        legacy_assessment_lines.append(f"- {cs.criterion}: {status_symbol} {cs.status} ({cs.evidence})")
    if result.gaps:
        legacy_assessment_lines.append(f"Gaps: {', '.join(result.gaps)}")
    if result.blocker:
        legacy_assessment_lines.append(f"Blocker: {result.blocker}")
    if result.efficiency_notes:
        legacy_assessment_lines.append(f"Efficiency Notes: {result.efficiency_notes}")

    return {
        "result": result,
        "full_output": full_text,
        "messages": messages,
        # Legacy fields for backward compatibility
        "outcome": result.outcome,
        "assessment": "\n".join(legacy_assessment_lines),
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
    print("\nOutcome:", result["outcome"])
    print("\nAssessment:")
    print(result["assessment"])


if __name__ == "__main__":
    asyncio.run(main())
