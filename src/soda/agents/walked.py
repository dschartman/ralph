"""Walked agent pattern implementation.

The walked agent pattern maintains conversation context across multiple prompts,
allowing for multi-turn interactions where context persists between exchanges.
"""

from pathlib import Path
from typing import Callable, Optional

from soda.errors import RetryHandler
from soda.outputs.capture import OutputCapture
from soda.types import AgentConfig, Message


class WalkedAgent:
    """Walked agent that maintains conversation context across multiple prompts.

    The walked agent pattern is designed for multi-turn conversations where
    context needs to persist across multiple exchanges. It provides three
    main operations:

    - start(): Initialize a new conversation
    - send(): Send a prompt and receive a response while maintaining context
    - end(): End the conversation and capture the full transcript

    Example:
        >>> agent = WalkedAgent()
        >>> agent.start(system_prompt="You are a helpful assistant.")
        >>> response1 = agent.send("My name is Alice.")
        >>> response2 = agent.send("What is my name?")
        >>> # response2 should remember that the name is Alice
        >>> messages = agent.end()

    Attributes:
        _config: Agent configuration (model, max_tokens, etc.)
        _messages: List of messages in the conversation
        _system_prompt: Optional system prompt for the conversation
        _started: Whether the conversation has been started
        _ended: Whether the conversation has been ended
        _retry_handler: Handler for retrying transient errors
        _output_capture: Handler for capturing output to JSONL
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        output_dir: Optional[Path] = None,
        retry_handler: Optional[RetryHandler] = None,
    ) -> None:
        """Initialize the walked agent.

        Args:
            config: Agent configuration. Defaults to AgentConfig with defaults.
            output_dir: Directory for output capture. Defaults to 'outputs/'.
            retry_handler: Handler for retrying transient errors. Defaults to
                RetryHandler with standard settings.
        """
        self._config = config if config is not None else AgentConfig()
        self._messages: list[Message] = []
        self._system_prompt: Optional[str] = None
        self._started: bool = False
        self._ended: bool = False
        self._retry_handler = retry_handler if retry_handler is not None else RetryHandler()
        self._output_capture = OutputCapture(output_dir=output_dir)

    def start(self, system_prompt: Optional[str] = None) -> None:
        """Start a walked conversation.

        Initializes the conversation state and optionally sets a system prompt
        that will be used for all subsequent exchanges.

        Args:
            system_prompt: Optional system prompt to guide agent behavior.

        Raises:
            RuntimeError: If the conversation has already been started.
        """
        if self._started:
            raise RuntimeError("Conversation already started. Call end() first to start a new conversation.")

        self._messages = []
        self._system_prompt = system_prompt
        self._started = True
        self._ended = False

    def send(self, prompt: str) -> str:
        """Send a prompt to the agent and receive a response.

        The prompt is added to the conversation history, along with the
        response. All previous messages are included as context for each
        new prompt, allowing the agent to maintain context across exchanges.

        Args:
            prompt: The user message to send.

        Returns:
            The assistant's response as a string.

        Raises:
            RuntimeError: If the conversation has not been started or has
                already been ended.
        """
        if not self._started:
            raise RuntimeError("Conversation not started. Call start() first.")
        if self._ended:
            raise RuntimeError("Conversation already ended. Call start() to begin a new conversation.")

        # Add user message to history
        user_message = Message(role="user", content=prompt)
        self._messages.append(user_message)

        # Get response from agent (includes all previous context)
        response = self._invoke_agent(self._messages, self._system_prompt)

        # Add assistant response to history
        assistant_message = Message(role="assistant", content=response)
        self._messages.append(assistant_message)

        return response

    def end(self) -> list[Message]:
        """End the conversation and capture the full transcript.

        Marks the conversation as ended, captures the full transcript to
        a JSONL file (non-blocking), and returns all messages.

        Returns:
            List of all messages in the conversation.

        Raises:
            RuntimeError: If the conversation has not been started or has
                already been ended.
        """
        if not self._started:
            raise RuntimeError("Conversation not started. Call start() first.")
        if self._ended:
            raise RuntimeError("Conversation already ended.")

        self._ended = True

        # Capture output (non-blocking, swallows errors)
        self._capture_output()

        return list(self._messages)

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

    def _capture_output(self) -> None:
        """Capture the conversation output to JSONL.

        This method is non-blocking - any errors during capture are
        silently ignored to ensure the agent result is always returned.
        """
        try:
            # Build prompt summary from first message
            prompt_summary = ""
            if self._messages:
                first_content = self._messages[0].content
                prompt_summary = first_content[:100] if len(first_content) > 100 else first_content

            # Convert messages to serializable format
            messages_data = [
                {"role": msg.role, "content": msg.content}
                for msg in self._messages
            ]

            output_data = {
                "system_prompt": self._system_prompt,
                "messages": messages_data,
            }

            self._output_capture.capture(
                agent_type="walked",
                prompt_summary=prompt_summary,
                output=output_data
            )
        except Exception:
            # Capture is non-blocking - swallow all errors
            pass
