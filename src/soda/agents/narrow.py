"""Narrow agent pattern implementation.

The narrow agent pattern provides single-shot agent invocation with:
- Structured output validation against Pydantic schemas
- Optional tool restriction via allowlist
- Full conversation capture to JSONL files
- Error handling with retry for transient errors
- Optional streaming output for real-time progress

Uses Claude Agent SDK's native structured output support for guaranteed
schema conformance.

IMPORTANT: Due to a bug in the Claude Agent SDK (PR #364), cancel scopes
can leak between agent invocations. To work around this, each agent
invocation runs in a fresh thread with its own event loop, providing
complete isolation from cancel scope corruption.
"""

import asyncio
import concurrent.futures
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel

from soda.errors import FatalError, RetryHandler
from soda.outputs import OutputCapture
from soda.validation import StructuredOutputValidator

if TYPE_CHECKING:
    from soda.agents.streaming import StreamingCallback


class StreamingCallbackProtocol(Protocol):
    """Protocol for streaming callbacks."""

    def on_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Called when a tool is invoked."""
        ...

    def on_tool_result(
        self, success: bool = True, error_message: Optional[str] = None
    ) -> None:
        """Called when a tool returns a result."""
        ...

    def on_text(self, text: str) -> None:
        """Called when the agent produces text output."""
        ...


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
        streaming_callback: Optional[StreamingCallbackProtocol] = None,
    ) -> T:
        """Invoke the agent with a prompt and return structured output.

        Uses Claude Agent SDK's native structured output support for
        guaranteed schema conformance. The SDK handles JSON schema
        enforcement; we just validate the result with Pydantic.

        IMPORTANT: Each invocation runs in a separate thread with a fresh
        event loop to work around SDK cancel scope bugs (PR #364).

        Args:
            prompt: The prompt to send to the agent.
            output_schema: Pydantic model class for output validation.
            tools: Optional list of allowed tools. None means all tools.
            model: Optional model override. Defaults to claude-sonnet.
            system_prompt: Optional system prompt to guide agent behavior.
            streaming_callback: Optional callback for real-time streaming output.
                If provided, tool calls and results are streamed to the console.

        Returns:
            Parsed output matching the provided schema.

        Raises:
            StructuredOutputValidationError: If output doesn't match schema.
            FatalError: If a fatal error occurs (e.g., invalid API key,
                structured output extraction failed).
            MaxRetriesExhaustedError: If max retries are exhausted.
        """
        # Run agent in a separate thread with fresh event loop to isolate
        # from cancel scope corruption (SDK bug PR #364). This ensures
        # each agent invocation has a completely clean async context.
        loop = asyncio.get_running_loop()

        def run_in_fresh_loop() -> dict[str, Any]:
            """Run the agent call in a fresh event loop."""
            return asyncio.run(
                self._invoke_with_retry(
                    prompt=prompt,
                    output_schema=output_schema,
                    tools=tools,
                    model=model,
                    system_prompt=system_prompt,
                    streaming_callback=streaming_callback,
                )
            )

        # Run in thread pool to get fresh event loop isolation
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = loop.run_in_executor(executor, run_in_fresh_loop)
            structured_output = await future

        # Validate with Pydantic (SDK already enforced schema, but this
        # gives us type safety and handles any edge cases)
        result = output_schema.model_validate(structured_output)

        # Capture output (non-blocking, errors swallowed)
        import json
        self._capture_output(prompt, json.dumps(structured_output))

        return result

    async def _invoke_with_retry(
        self,
        prompt: str,
        output_schema: Type[T],
        tools: Optional[list[str]] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        streaming_callback: Optional[StreamingCallbackProtocol] = None,
    ) -> dict[str, Any]:
        """Internal method that handles retry logic for agent invocation.

        This runs in a fresh event loop via the thread pool.
        """
        return await self._retry_handler.execute_with_retry_async(
            lambda: self._call_agent(
                prompt=prompt,
                output_schema=output_schema,
                tools=tools,
                model=model,
                system_prompt=system_prompt,
                streaming_callback=streaming_callback,
            )
        )

    async def _call_agent(
        self,
        prompt: str,
        output_schema: Type[T],
        tools: Optional[list[str]] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        streaming_callback: Optional[StreamingCallbackProtocol] = None,
    ) -> dict[str, Any]:
        """Call the underlying Claude agent with structured output.

        This method handles the actual Claude SDK invocation with native
        structured output support for guaranteed schema conformance.
        Override this method for testing or custom agent behavior.

        Args:
            prompt: The prompt to send.
            output_schema: Pydantic model class for structured output.
            tools: Optional tool allowlist.
            model: Optional model override.
            system_prompt: Optional system prompt for the agent.
            streaming_callback: Optional callback for streaming output.

        Returns:
            Structured output dict from the agent (validated by SDK).

        Raises:
            FatalError: If structured output extraction fails after retries.
        """
        # Import here to avoid import errors when SDK not installed
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import (
            AssistantMessage,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        options = ClaudeAgentOptions(
            allowed_tools=tools or [],
            model=model,
            permission_mode="bypassPermissions",
            system_prompt=system_prompt,
            output_format={
                "type": "json_schema",
                "schema": output_schema.model_json_schema(),
            },
        )

        # Process messages and look for structured output
        # We manually handle cleanup to avoid cancel scope errors from the SDK.
        # The SDK has a bug where async generator cleanup can run in a different
        # task than where it was created, causing anyio cancel scope errors.
        # If we already have structured_output, cleanup errors are not fatal.
        structured_output: Optional[dict[str, Any]] = None
        messages_gen = query(prompt=prompt, options=options)
        try:
            async for message in messages_gen:
                # Stream tool calls and text if callback provided
                if streaming_callback is not None:
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                streaming_callback.on_tool_call(
                                    block.name,
                                    block.input if hasattr(block, "input") else {},
                                )
                            elif isinstance(block, TextBlock):
                                streaming_callback.on_text(block.text)
                    elif isinstance(message, ToolResultBlock):
                        # Tool results indicate success (errors come through differently)
                        streaming_callback.on_tool_result(success=True)

                # Check for the final result with structured output
                if isinstance(message, ResultMessage):
                    if message.structured_output:
                        structured_output = message.structured_output
                    elif message.subtype == "error_max_structured_output_retries":
                        raise FatalError(
                            "Failed to get structured output after SDK retries",
                            status_code=500,
                        )
        finally:
            # Clean up the async generator. Since we run in an isolated event
            # loop (fresh thread), any cancel scope corruption from SDK bugs
            # (PR #364) is contained and won't leak to subsequent invocations.
            # Suppress all cleanup errors - they don't affect the result.
            try:
                await messages_gen.aclose()
            except (RuntimeError, GeneratorExit, asyncio.CancelledError):
                # SDK cleanup bugs - suppress and move on. The isolated event
                # loop will be destroyed after this invocation anyway.
                pass

        if structured_output is None:
            raise FatalError(
                "No structured output received from agent",
                status_code=500,
            )

        return structured_output

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
