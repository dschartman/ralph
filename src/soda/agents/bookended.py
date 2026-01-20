"""Bookended agent pattern implementation.

The bookended agent pattern executes setup prompts before the main work prompt,
and wrap-up prompts after, all within the same conversation context.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from soda.errors import RetryHandler
from soda.outputs.capture import OutputCapture
from soda.types import AgentConfig, Message


@dataclass
class BookendedResult:
    """Result of a bookended agent invocation.

    Attributes:
        setup_responses: List of responses from setup prompts.
        work_response: Response from the main work prompt.
        wrapup_responses: List of responses from wrap-up prompts.
        messages: Full conversation history (all messages in order).
    """

    setup_responses: list[str]
    work_response: str
    wrapup_responses: list[str]
    messages: list[Message] = field(default_factory=list)


class BookendedAgent:
    """Bookended agent that executes setup, work, and wrap-up prompts in sequence.

    The bookended agent pattern is designed for tasks that require:
    - Setup phase: Establish context, load data, set constraints
    - Work phase: Execute the main task
    - Wrap-up phase: Summarize, verify, or finalize results

    All phases execute within the same conversation context, so the agent
    maintains awareness of the full interaction history.

    Example:
        >>> agent = BookendedAgent()
        >>> result = agent.run(
        ...     setup_prompts=["Load the user data.", "Review the requirements."],
        ...     work_prompt="Generate a report based on the data.",
        ...     wrapup_prompts=["Verify the report is complete."]
        ... )
        >>> print(result.work_response)

    Attributes:
        _config: Agent configuration (model, max_tokens, etc.)
        _retry_handler: Handler for retrying transient errors.
        _output_capture: Handler for capturing output to JSONL.
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        output_dir: Optional[Path] = None,
        retry_handler: Optional[RetryHandler] = None,
    ) -> None:
        """Initialize the bookended agent.

        Args:
            config: Agent configuration. Defaults to AgentConfig with defaults.
            output_dir: Directory for output capture. Defaults to 'outputs/'.
            retry_handler: Handler for retrying transient errors. Defaults to
                RetryHandler with standard settings.
        """
        self._config = config if config is not None else AgentConfig()
        self._retry_handler = retry_handler if retry_handler is not None else RetryHandler()
        self._output_capture = OutputCapture(output_dir=output_dir)

    def run(
        self,
        setup_prompts: list[str],
        work_prompt: str,
        wrapup_prompts: list[str],
        system_prompt: Optional[str] = None,
    ) -> BookendedResult:
        """Execute the bookended agent pattern.

        Runs setup prompts, then the main work prompt, then wrap-up prompts,
        all within the same conversation context. The full conversation is
        captured to a JSONL file when complete.

        Args:
            setup_prompts: List of prompts to execute before the main work.
            work_prompt: The main work prompt to execute.
            wrapup_prompts: List of prompts to execute after the main work.
            system_prompt: Optional system prompt to guide agent behavior.

        Returns:
            BookendedResult containing responses from each phase and the full
            conversation history.
        """
        messages: list[Message] = []
        setup_responses: list[str] = []
        wrapup_responses: list[str] = []

        # Execute setup prompts
        for prompt in setup_prompts:
            response = self._send_prompt(prompt, messages, system_prompt)
            setup_responses.append(response)

        # Execute main work prompt
        work_response = self._send_prompt(work_prompt, messages, system_prompt)

        # Execute wrap-up prompts
        for prompt in wrapup_prompts:
            response = self._send_prompt(prompt, messages, system_prompt)
            wrapup_responses.append(response)

        # Capture output (non-blocking)
        self._capture_output(messages, system_prompt)

        return BookendedResult(
            setup_responses=setup_responses,
            work_response=work_response,
            wrapup_responses=wrapup_responses,
            messages=list(messages),
        )

    def _send_prompt(
        self,
        prompt: str,
        messages: list[Message],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a prompt and update the message history.

        Args:
            prompt: The user message to send.
            messages: The message history (will be mutated).
            system_prompt: Optional system prompt for the agent.

        Returns:
            The agent's response as a string.
        """
        # Add user message to history
        user_message = Message(role="user", content=prompt)
        messages.append(user_message)

        # Get response from agent (includes all previous context)
        response = self._invoke_agent(messages, system_prompt)

        # Add assistant response to history
        assistant_message = Message(role="assistant", content=response)
        messages.append(assistant_message)

        return response

    def _invoke_agent(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None
    ) -> str:
        """Invoke the agent with the current conversation context.

        This method is designed to be overridden in tests or subclasses.
        The default implementation is a placeholder that should be replaced
        with actual Claude API integration.

        Args:
            messages: List of messages to send to the agent.
            system_prompt: Optional system prompt for the agent.

        Returns:
            The agent's response as a string.
        """
        # This is a placeholder implementation.
        # In production, this would call the Claude Agent SDK.
        # For testing, this method is mocked.
        raise NotImplementedError(
            "Agent invocation not implemented. "
            "Override _invoke_agent or mock it in tests."
        )

    def _capture_output(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
    ) -> None:
        """Capture the conversation output to JSONL.

        This method is non-blocking - any errors during capture are
        silently ignored to ensure the agent result is always returned.

        Args:
            messages: The conversation messages.
            system_prompt: Optional system prompt used.
        """
        try:
            # Build prompt summary from first message
            prompt_summary = ""
            if messages:
                first_content = messages[0].content
                prompt_summary = first_content[:100] if len(first_content) > 100 else first_content

            # Convert messages to serializable format
            messages_data = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]

            output_data = {
                "system_prompt": system_prompt,
                "messages": messages_data,
            }

            self._output_capture.capture(
                agent_type="bookended",
                prompt_summary=prompt_summary,
                output=output_data
            )
        except Exception:
            # Capture is non-blocking - swallow all errors
            pass
