"""Tests for the walked agent pattern.

The walked agent maintains conversation context across multiple prompts,
allowing for multi-turn interactions where context persists.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile

from soda.types import Message, AgentConfig


class TestWalkedAgentInterface:
    """Test WalkedAgent interface and basic functionality."""

    def test_walked_agent_can_be_imported(self):
        """WHEN WalkedAgent is imported THEN it is available."""
        from soda.agents.walked import WalkedAgent
        assert WalkedAgent is not None

    def test_walked_agent_can_be_instantiated(self):
        """WHEN WalkedAgent is instantiated THEN it creates an object."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        assert agent is not None

    def test_walked_agent_has_required_methods(self):
        """WHEN WalkedAgent is created THEN it has start, send, and end methods."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        assert hasattr(agent, 'start')
        assert hasattr(agent, 'send')
        assert hasattr(agent, 'end')
        assert callable(agent.start)
        assert callable(agent.send)
        assert callable(agent.end)


class TestWalkedAgentStart:
    """Test WalkedAgent.start() functionality."""

    def test_start_initializes_conversation(self):
        """WHEN start() is called THEN conversation state is initialized."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        agent.start()
        # Should have empty messages list after start
        assert agent._messages == []
        assert agent._started is True

    def test_start_can_receive_system_prompt(self):
        """WHEN start() is called with system_prompt THEN it is stored."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        agent.start(system_prompt="You are a helpful assistant.")
        assert agent._system_prompt == "You are a helpful assistant."

    def test_start_twice_raises_error(self):
        """WHEN start() is called twice THEN it raises an error."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        agent.start()
        with pytest.raises(RuntimeError, match="already started"):
            agent.start()


class TestWalkedAgentSend:
    """Test WalkedAgent.send() functionality."""

    def test_send_before_start_raises_error(self):
        """WHEN send() is called before start() THEN it raises an error."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        with pytest.raises(RuntimeError, match="not started"):
            agent.send("Hello")

    def test_send_returns_response(self):
        """WHEN send() is called THEN it returns a response string."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()

        # Mock the internal _invoke_agent method
        agent._invoke_agent = Mock(return_value="Hello! How can I help you?")

        response = agent.send("Hello")

        assert isinstance(response, str)
        assert response == "Hello! How can I help you?"

    def test_send_captures_messages(self):
        """WHEN send() is called THEN both user and assistant messages are captured."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()

        agent._invoke_agent = Mock(return_value="I am here to help.")

        agent.send("Who are you?")

        assert len(agent._messages) == 2
        assert agent._messages[0].role == "user"
        assert agent._messages[0].content == "Who are you?"
        assert agent._messages[1].role == "assistant"
        assert agent._messages[1].content == "I am here to help."

    def test_multiple_sends_maintain_context(self):
        """WHEN multiple prompts are sent THEN all messages are accumulated."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()

        agent._invoke_agent = Mock(side_effect=["First response", "Second response"])

        agent.send("First message")
        agent.send("Second message")

        assert len(agent._messages) == 4
        assert agent._messages[0].content == "First message"
        assert agent._messages[1].content == "First response"
        assert agent._messages[2].content == "Second message"
        assert agent._messages[3].content == "Second response"


class TestWalkedAgentEnd:
    """Test WalkedAgent.end() functionality."""

    def test_end_before_start_raises_error(self):
        """WHEN end() is called before start() THEN it raises an error."""
        from soda.agents.walked import WalkedAgent
        agent = WalkedAgent()
        with pytest.raises(RuntimeError, match="not started"):
            agent.end()

    def test_end_returns_message_list(self):
        """WHEN end() is called THEN it returns list of Messages."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()
        agent._invoke_agent = Mock(return_value="Response")
        agent.send("Hello")

        messages = agent.end()

        assert isinstance(messages, list)
        assert len(messages) == 2
        assert all(isinstance(m, Message) for m in messages)

    def test_end_captures_to_jsonl(self):
        """WHEN end() is called THEN conversation is captured to JSONL file."""
        from soda.agents.walked import WalkedAgent

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "outputs"
            agent = WalkedAgent(output_dir=output_dir)
            agent.start()
            agent._invoke_agent = Mock(return_value="Hi there!")
            agent.send("Hello")
            agent.end()

            # Check that output directory was created
            assert output_dir.exists()

            # Check that a JSONL file was created
            jsonl_files = list(output_dir.glob("*.jsonl"))
            assert len(jsonl_files) >= 1

    def test_end_marks_conversation_as_ended(self):
        """WHEN end() is called THEN conversation cannot be continued."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()
        agent._invoke_agent = Mock(return_value="Response")
        agent.send("Hello")
        agent.end()

        with pytest.raises(RuntimeError, match="already ended"):
            agent.send("More")

    def test_end_twice_raises_error(self):
        """WHEN end() is called twice THEN it raises an error."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start()
        agent.end()

        with pytest.raises(RuntimeError, match="already ended"):
            agent.end()


class TestWalkedAgentContextPersistence:
    """Test that walked agent properly maintains context across exchanges."""

    def test_context_persists_across_sends(self):
        """WHEN multiple prompts are sent THEN agent receives full context."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        agent.start(system_prompt="Remember everything I tell you.")

        # Track what messages the agent is called with
        call_messages = []

        def mock_invoke(messages, system_prompt):
            call_messages.append(list(messages))
            return f"Received {len(messages)} messages"

        agent._invoke_agent = mock_invoke

        agent.send("My name is Alice")
        agent.send("What is my name?")

        # Second call should include all previous messages
        assert len(call_messages) == 2
        assert len(call_messages[0]) == 1  # First call: 1 user message
        assert len(call_messages[1]) == 3  # Second call: user, assistant, user


class TestWalkedAgentWithRetry:
    """Test that walked agent uses retry handler for transient errors."""

    def test_uses_retry_handler(self):
        """WHEN WalkedAgent is created THEN it uses RetryHandler."""
        from soda.agents.walked import WalkedAgent
        from soda.errors import RetryHandler

        agent = WalkedAgent()
        assert hasattr(agent, '_retry_handler')
        assert isinstance(agent._retry_handler, RetryHandler)


class TestWalkedAgentConfig:
    """Test WalkedAgent configuration options."""

    def test_accepts_custom_config(self):
        """WHEN WalkedAgent receives custom config THEN it uses that config."""
        from soda.agents.walked import WalkedAgent

        config = AgentConfig(model="claude-sonnet-4-20250514", max_tokens=8000)
        agent = WalkedAgent(config=config)

        assert agent._config.model == "claude-sonnet-4-20250514"
        assert agent._config.max_tokens == 8000

    def test_uses_default_config_if_none_provided(self):
        """WHEN no config provided THEN uses default AgentConfig."""
        from soda.agents.walked import WalkedAgent

        agent = WalkedAgent()
        assert agent._config is not None
        assert agent._config.model == "claude-sonnet-4-20250514"


class TestWalkedAgentOutputCapture:
    """Test that output capture is non-blocking."""

    def test_output_capture_failure_does_not_affect_result(self):
        """WHEN output capture fails THEN end() still returns messages."""
        from soda.agents.walked import WalkedAgent
        from soda.outputs.capture import OutputCapture

        agent = WalkedAgent()
        agent.start()
        agent._invoke_agent = Mock(return_value="Response")
        agent.send("Hello")

        # Make capture fail
        agent._output_capture.capture = Mock(side_effect=Exception("Capture failed"))

        # Should still succeed
        messages = agent.end()
        assert len(messages) == 2
