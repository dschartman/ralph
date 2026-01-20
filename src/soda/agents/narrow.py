"""Narrow agent pattern implementation.

The narrow agent pattern provides single-shot agent invocation with:
- Structured output validation against Pydantic schemas
- Optional tool restriction via allowlist
- Full conversation capture to JSONL files
- Error handling with retry for transient errors
"""

import asyncio
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from soda.errors import RetryHandler
from soda.outputs import OutputCapture
from soda.validation import StructuredOutputValidator


T = TypeVar("T", bound=BaseModel)


class NarrowAgent:
    """Single-shot agent with structured output.

    The narrow agent pattern executes a single prompt and returns
    structured output matching the provided schema. Supports optional
    tool restriction and captures all conversations to JSONL files.

    Attributes:
        output_dir: Directory for JSONL output capture files.

    Example:
        >>> class AnalysisResult(BaseModel):
        ...     findings: list[str]
        ...     severity: str
        ...
        >>> agent = NarrowAgent()
        >>> result = await agent.invoke(
        ...     prompt="Analyze this code for security issues",
        ...     output_schema=AnalysisResult,
        ...     tools=["Read", "Grep"]
        ... )
        >>> print(result.findings)
        ['SQL injection vulnerability in line 42']
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        """Initialize the narrow agent.

        Args:
            output_dir: Directory for output capture. Defaults to 'outputs/'.
        """
        self.output_dir = output_dir if output_dir is not None else Path("outputs")
        self._output_capture = OutputCapture(output_dir=self.output_dir)
        self._validator = StructuredOutputValidator()
        self._retry_handler = RetryHandler(base_delay=0.1)  # Fast retries for tests

    async def invoke(
        self,
        prompt: str,
        output_schema: Type[T],
        tools: Optional[list[str]] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> T:
        """Invoke the agent with a prompt and return structured output.

        Args:
            prompt: The prompt to send to the agent.
            output_schema: Pydantic model class for output validation.
            tools: Optional list of allowed tools. None means all tools.
            model: Optional model override. Defaults to claude-sonnet.
            system_prompt: Optional system prompt to guide agent behavior.

        Returns:
            Parsed output matching the provided schema.

        Raises:
            StructuredOutputValidationError: If output doesn't match schema.
            FatalError: If a fatal error occurs (e.g., invalid API key).
            MaxRetriesExhaustedError: If max retries are exhausted.
        """
        # Execute with async retry handling
        raw_output = await self._retry_handler.execute_with_retry_async(
            lambda: self._call_agent(
                prompt=prompt, tools=tools, model=model, system_prompt=system_prompt
            )
        )

        # Validate and parse output
        result = self._validator.validate(raw_output, output_schema)

        # Capture output (non-blocking, errors swallowed)
        self._capture_output(prompt, raw_output)

        return result

    async def _call_agent(
        self,
        prompt: str,
        tools: Optional[list[str]] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Call the underlying Claude agent.

        This method handles the actual Claude SDK invocation.
        Override this method for testing or custom agent behavior.

        Args:
            prompt: The prompt to send.
            tools: Optional tool allowlist.
            model: Optional model override.
            system_prompt: Optional system prompt for the agent.

        Returns:
            Raw JSON string output from the agent.
        """
        # Import here to avoid import errors when SDK not installed
        from claude_agent_sdk import query, ClaudeAgentOptions

        options = ClaudeAgentOptions(
            allowed_tools=tools or [],
            model=model,
            permission_mode="bypassPermissions",
            system_prompt=system_prompt,
        )

        # Collect response
        response_text = ""
        async for message in query(prompt=prompt, options=options):
            # Extract text content from assistant messages
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        response_text += block.text

        return response_text

    def _capture_output(self, prompt: str, raw_output: str) -> None:
        """Capture output to JSONL file.

        This is non-blocking and swallows all errors to ensure
        capture failures don't affect the agent result.

        Args:
            prompt: The original prompt (for summary).
            raw_output: The raw output to capture.
        """
        try:
            # Truncate prompt for summary
            prompt_summary = prompt[:100] + "..." if len(prompt) > 100 else prompt

            self._output_capture.capture(
                agent_type="narrow",
                prompt_summary=prompt_summary,
                output=raw_output,
            )
        except Exception:
            # Swallow all capture errors
            pass
