"""Specialist agents: Provide focused feedback on specific aspects of the codebase."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, List

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import ResultMessage

from ralph2.agents.models import SpecialistResult, FeedbackItem
from ralph2.agents.streaming import stream_agent_output
from ralph2.agents.constants import AGENT_MODEL


class Specialist(ABC):
    """Base class for all specialist agents.

    Specialists are read-only feedback generators that analyze the codebase
    and provide focused feedback on specific aspects (code quality, security,
    performance, etc.).
    """

    def __init__(self, name: str, allowed_tools: List[str]):
        """Initialize specialist.

        Args:
            name: Identifier for this specialist (e.g., "code_reviewer")
            allowed_tools: List of tools this specialist can use (read-only tools only)
        """
        self.name = name
        self.allowed_tools = allowed_tools

    @property
    @abstractmethod
    def SYSTEM_PROMPT(self) -> str:
        """The system prompt for this specialist."""
        pass

    async def run(
        self,
        spec_content: str,
        memory: str = "",
        root_work_item_id: str = "",
    ) -> Dict:
        """Run the specialist analysis.

        Args:
            spec_content: The specification content
            memory: Project memory content
            root_work_item_id: Root work item ID for checking existing backlog

        Returns:
            dict with keys:
                - result (SpecialistResult): The structured result
                - full_output (str): Complete output text
                - messages (list): Raw message history
        """
        # Build the prompt
        prompt_parts = [
            "# Spec (for context)",
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

        if root_work_item_id:
            prompt_parts.append(f"# Backlog Root: {root_work_item_id}")
            prompt_parts.append("")
            prompt_parts.append(f"Use `trc tree {root_work_item_id}` to see existing work items before generating feedback.")
            prompt_parts.append("")
            prompt_parts.append("---")
            prompt_parts.append("")

        prompt_parts.extend([
            "# Your Task",
            "",
            "1. First, check the existing backlog using `trc tree` (if root provided)",
            "2. Review the codebase for issues within your specialty",
            "3. Skip any issues already in the backlog",
            "4. Provide specific, actionable feedback for NEW issues only",
        ])

        prompt = "\n".join(prompt_parts)

        # Configure the agent with structured output
        options = ClaudeAgentOptions(
            model=AGENT_MODEL,
            allowed_tools=self.allowed_tools,
            permission_mode="bypassPermissions",
            system_prompt=self.SYSTEM_PROMPT,
            output_format={
                "type": "json_schema",
                "schema": SpecialistResult.model_json_schema()
            }
        )

        # Run the specialist agent
        full_output = []
        messages = []
        result: Optional[SpecialistResult] = None

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
                        result = SpecialistResult.model_validate(message.structured_output)
                        print(f"\033[32m✓ {self.name}: {len(result.feedback_items)} feedback items\033[0m")
                    elif message.subtype == "error_max_structured_output_retries":
                        print(f"\033[31m✗ Failed to get structured output after retries\033[0m")

        full_text = "\n".join(full_output)

        # If we didn't get a valid result, create a default
        if result is None:
            print(f"\033[33mWarning: No structured output received from {self.name}\033[0m")
            result = SpecialistResult(
                specialist_name=self.name,
                feedback_items=[]
            )

        # Build legacy feedback list for backward compatibility
        legacy_feedback = []
        for item in result.feedback_items:
            legacy_feedback.append(f"[{item.priority}] {item.location}: {item.issue}. {item.impact}. {item.suggestion}")

        return {
            "result": result,
            "full_output": full_text,
            "messages": messages,
            # Legacy fields for backward compatibility
            "specialist_name": result.specialist_name,
            "feedback": legacy_feedback,
        }


class CodeReviewerSpecialist(Specialist):
    """Code Reviewer specialist: Analyzes code for maintainability and quality."""

    SYSTEM_PROMPT = """You are the Code Reviewer specialist in the Ralph2 multi-agent system.

Your job is to analyze the codebase for maintainability and code quality issues.

## Critical: Check Backlog First

Before generating any feedback, you MUST check the existing backlog:

```bash
trc tree <root_work_item_id>  # See all existing work items
```

**Before reporting any issue:**
1. Run `trc tree` to see what's already tracked
2. Check if the issue (or a semantically similar one) is already in the backlog
3. If it's already tracked, DO NOT report it again
4. Only report genuinely NEW issues not already captured

This is critical for efficiency - duplicate work items waste iteration cycles.

## Your Responsibilities

1. Review the codebase for:
   - Code clarity and readability
   - Proper abstractions and separation of concerns
   - Error handling and edge cases
   - Test coverage gaps
   - Technical debt
   - Code duplication
   - Magic numbers and hard-coded values
   - Missing type hints (for Python)
   - Docstring completeness

2. Provide actionable feedback as work items with priority

## Your Boundaries

- You DO NOT implement fixes (that's the Executor's job)
- You DO NOT verify spec compliance (that's the Verifier's job)
- You DO focus on maintainability and code quality

## Priority Guidelines

- **P0 (Critical)**: Security vulnerabilities, critical bugs, data loss risks
- **P1 (High)**: Maintainability blockers, significant technical debt
- **P2 (Medium)**: Code quality improvements, test coverage gaps
- **P3 (Low)**: Style issues, minor refactorings, documentation gaps

## Guidelines

- Be specific about the location (file, function, line range)
- Explain the impact (why it matters)
- Suggest the fix direction (not the full implementation)
- Focus on high-leverage issues (don't nitpick trivial style)
- Return an empty feedback list if all issues are already in the backlog
"""

    def __init__(self):
        """Initialize Code Reviewer specialist."""
        super().__init__(
            name="code_reviewer",
            allowed_tools=["Read", "Glob", "Grep", "Bash"]
        )


async def run_specialist(
    specialist: Specialist,
    spec_content: str,
    memory: str = "",
    root_work_item_id: str = "",
) -> Dict:
    """Run a specialist and return its feedback.

    This is a helper function that wraps specialist execution with error handling.

    Args:
        specialist: The specialist instance to run
        spec_content: The specification content
        memory: Project memory content
        root_work_item_id: Root work item ID for checking existing backlog

    Returns:
        dict with keys: result, full_output, messages, specialist_name, feedback
        On error, returns dict with specialist_name and error key
    """
    try:
        return await specialist.run(
            spec_content=spec_content,
            memory=memory,
            root_work_item_id=root_work_item_id
        )
    except Exception as e:
        return {
            "specialist_name": specialist.name,
            "error": str(e),
            "feedback": [],
            "full_output": "",
            "messages": [],
            "result": SpecialistResult(
                specialist_name=specialist.name,
                feedback_items=[]
            ),
        }


async def main():
    """Test the Code Reviewer specialist."""
    spec = """
    # Test Spec

    Build a simple user authentication system.

    ## Acceptance Criteria
    - [ ] Users can register with email and password
    - [ ] Users can login
    - [ ] Passwords are securely hashed
    """

    reviewer = CodeReviewerSpecialist()
    result = await reviewer.run(spec_content=spec, memory="")

    print("\nResult:", result["result"])
    print("\nFeedback items:")
    for item in result["feedback"]:
        print(f"  - {item}")


if __name__ == "__main__":
    asyncio.run(main())
