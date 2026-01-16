"""Specialist agents: Provide focused feedback on specific aspects of the codebase."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
import re

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock


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

    @abstractmethod
    async def run(
        self,
        spec_content: str,
        memory: str = "",
    ) -> Dict:
        """Run the specialist analysis.

        Args:
            spec_content: The specification content
            memory: Project memory content

        Returns:
            dict with keys:
                - specialist_name (str): Name of the specialist
                - feedback (list): List of feedback items
                - full_output (str): Complete output text
                - messages (list): Raw message history
        """
        pass


class CodeReviewerSpecialist(Specialist):
    """Code Reviewer specialist: Analyzes code for maintainability and quality."""

    SYSTEM_PROMPT = """You are the Code Reviewer specialist in the Ralph2 multi-agent system.

Your ONLY job is to analyze the codebase for maintainability and code quality issues.

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

## Output Format

End your response with:

SPECIALIST_FEEDBACK:
Feedback items:
- [P0] Critical issue description (if any)
- [P1] High priority issue description
- [P2] Medium priority issue description
...

**Guidelines:**
- Be specific about the location (file, function, line range)
- Explain the impact (why it matters)
- Suggest the fix direction (not the full implementation)
- Skip issues that are already in the backlog
- Focus on high-leverage issues (don't nitpick trivial style)

**Example:**

SPECIALIST_FEEDBACK:
Feedback items:
- [P0] src/auth.py:45-60: Password hashing uses MD5 (insecure). Switch to bcrypt or argon2.
- [P1] src/api/endpoints.py: No error handling for database queries. Add try/except and return appropriate HTTP status codes.
- [P2] tests/test_api.py: Test coverage is 45% for API module. Add tests for error cases and edge conditions.
"""

    def __init__(self):
        """Initialize Code Reviewer specialist."""
        super().__init__(
            name="code_reviewer",
            allowed_tools=["Read", "Glob", "Grep", "Bash"]
        )

    async def run(
        self,
        spec_content: str,
        memory: str = "",
    ) -> Dict:
        """Run code review analysis.

        Args:
            spec_content: The specification content
            memory: Project memory content

        Returns:
            dict with keys: specialist_name, feedback, full_output, messages
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

        prompt_parts.extend([
            "# Your Task",
            "",
            "1. Review the codebase for maintainability and quality issues",
            "2. Focus on high-leverage improvements (not trivial style issues)",
            "3. Check for: clarity, abstractions, error handling, test coverage, technical debt",
            "4. End with: SPECIALIST_FEEDBACK listing prioritized feedback items",
        ])

        prompt = "\n".join(prompt_parts)

        # Run the specialist agent
        full_output = []
        messages = []

        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    allowed_tools=self.allowed_tools,
                    permission_mode="bypassPermissions",
                    system_prompt=self.SYSTEM_PROMPT,
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

        # Parse feedback items from output
        full_text = "\n".join(full_output)
        feedback_items = self._parse_feedback(full_text)

        return {
            "specialist_name": self.name,
            "feedback": feedback_items,
            "full_output": full_text,
            "messages": messages,
        }

    def _parse_feedback(self, text: str) -> List[str]:
        """Parse feedback items from specialist output.

        Args:
            text: The full output text

        Returns:
            List of feedback item strings
        """
        feedback_items = []

        # Look for SPECIALIST_FEEDBACK section
        feedback_match = re.search(r'SPECIALIST_FEEDBACK:(.*?)(?=$)', text, re.DOTALL)
        if not feedback_match:
            return feedback_items

        feedback_text = feedback_match.group(1)

        # Extract feedback items (lines starting with - or * followed by [P#] or text)
        # Pattern: - [P#] description OR - description
        for line in feedback_text.split("\n"):
            line = line.strip()
            # Match lines starting with - or * (bullet points)
            if line.startswith(("-", "*")) and len(line) > 2:
                # Remove the bullet point
                item = line[1:].strip()
                # Skip empty lines and section headers
                if item and not item.endswith(":"):
                    feedback_items.append(item)

        return feedback_items


async def run_specialist(
    specialist: Specialist,
    spec_content: str,
    memory: str = "",
) -> Dict:
    """Run a specialist and return its feedback.

    This is a helper function that wraps specialist execution with error handling.

    Args:
        specialist: The specialist instance to run
        spec_content: The specification content
        memory: Project memory content

    Returns:
        dict with keys: specialist_name, feedback, full_output, messages
        On error, returns dict with specialist_name and error key
    """
    try:
        return await specialist.run(spec_content=spec_content, memory=memory)
    except Exception as e:
        return {
            "specialist_name": specialist.name,
            "error": str(e),
            "feedback": [],
            "full_output": "",
            "messages": [],
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

    print("\nFeedback items:")
    for item in result["feedback"]:
        print(f"  - {item}")


if __name__ == "__main__":
    asyncio.run(main())
