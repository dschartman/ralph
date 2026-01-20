"""Tests for the bookended agent pattern.

The bookended agent executes setup prompts before the main work prompt,
and wrap-up prompts after, all in the same conversation context.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
import json
import tempfile

from soda.types import Message, AgentConfig


class TestBookendedAgentInterface:
    """Test BookendedAgent interface and basic functionality."""

    def test_bookended_agent_can_be_imported(self):
        """WHEN BookendedAgent is imported THEN it is available."""
        from soda.agents.bookended import BookendedAgent
        assert BookendedAgent is not None

    def test_bookended_agent_can_be_instantiated(self):
        """WHEN BookendedAgent is instantiated THEN it creates an object."""
        from soda.agents.bookended import BookendedAgent
        agent = BookendedAgent()
        assert agent is not None

    def test_bookended_agent_has_required_method(self):
        """WHEN BookendedAgent is created THEN it has run method."""
        from soda.agents.bookended import BookendedAgent
        agent = BookendedAgent()
        assert hasattr(agent, 'run')
        assert callable(agent.run)


class TestBookendedAgentRun:
    """Test BookendedAgent.run() functionality."""

    def test_run_returns_bookended_result(self):
        """WHEN run() is called THEN it returns a BookendedResult."""
        from soda.agents.bookended import BookendedAgent, BookendedResult

        agent = BookendedAgent()
        agent._invoke_agent = Mock(side_effect=["setup1", "setup2", "main response", "wrapup1"])

        result = agent.run(
            setup_prompts=["setup prompt 1", "setup prompt 2"],
            work_prompt="main work",
            wrapup_prompts=["wrapup prompt 1"]
        )

        assert isinstance(result, BookendedResult)
        assert result.setup_responses == ["setup1", "setup2"]
        assert result.work_response == "main response"
        assert result.wrapup_responses == ["wrapup1"]

    def test_run_without_setup_prompts(self):
        """WHEN run() is called without setup prompts THEN it works."""
        from soda.agents.bookended import BookendedAgent, BookendedResult

        agent = BookendedAgent()
        agent._invoke_agent = Mock(side_effect=["main response", "wrapup"])

        result = agent.run(
            setup_prompts=[],
            work_prompt="main work",
            wrapup_prompts=["wrapup"]
        )

        assert result.setup_responses == []
        assert result.work_response == "main response"
        assert result.wrapup_responses == ["wrapup"]

    def test_run_without_wrapup_prompts(self):
        """WHEN run() is called without wrapup prompts THEN it works."""
        from soda.agents.bookended import BookendedAgent, BookendedResult

        agent = BookendedAgent()
        agent._invoke_agent = Mock(side_effect=["setup", "main response"])

        result = agent.run(
            setup_prompts=["setup"],
            work_prompt="main work",
            wrapup_prompts=[]
        )

        assert result.setup_responses == ["setup"]
        assert result.work_response == "main response"
        assert result.wrapup_responses == []

    def test_run_returns_all_messages(self):
        """WHEN run() completes THEN result includes all messages."""
        from soda.agents.bookended import BookendedAgent

        agent = BookendedAgent()
        agent._invoke_agent = Mock(side_effect=["s1", "work", "w1"])

        result = agent.run(
            setup_prompts=["setup 1"],
            work_prompt="main work",
            wrapup_prompts=["wrapup 1"]
        )

        # 6 messages: setup_user, setup_assistant, work_user, work_assistant, wrapup_user, wrapup_assistant
        assert len(result.messages) == 6
        assert result.messages[0].role == "user"
        assert result.messages[0].content == "setup 1"
        assert result.messages[1].role == "assistant"
        assert result.messages[1].content == "s1"


class TestBookendedAgentContextPersistence:
    """Test that bookended agent properly maintains context across phases."""

    def test_context_persists_through_setup_work_wrapup(self):
        """WHEN setup, work, wrapup are executed THEN context is maintained."""
        from soda.agents.bookended import BookendedAgent

        agent = BookendedAgent()

        # Track what messages the agent receives at each call
        call_messages = []

        def mock_invoke(messages, system_prompt):
            call_messages.append(len(messages))
            return f"Response to {len(messages)} messages"

        agent._invoke_agent = mock_invoke

        result = agent.run(
            setup_prompts=["setup 1", "setup 2"],
            work_prompt="main work",
            wrapup_prompts=["wrapup 1"]
        )

        # First setup: 1 message
        # Second setup: 3 messages (user, assistant, user)
        # Work: 5 messages (+ user, assistant, + user)
        # Wrapup: 7 messages (+ user, assistant, + user)
        assert call_messages == [1, 3, 5, 7]

    def test_system_prompt_passed_to_all_invocations(self):
        """WHEN system prompt is provided THEN it is passed to all invocations."""
        from soda.agents.bookended import BookendedAgent

        agent = BookendedAgent()

        system_prompts_received = []

        def mock_invoke(messages, system_prompt):
            system_prompts_received.append(system_prompt)
            return "response"

        agent._invoke_agent = mock_invoke

        result = agent.run(
            setup_prompts=["setup"],
            work_prompt="work",
            wrapup_prompts=["wrapup"],
            system_prompt="You are a helpful assistant."
        )

        assert all(sp == "You are a helpful assistant." for sp in system_prompts_received)
        assert len(system_prompts_received) == 3


class TestBookendedAgentOutputCapture:
    """Test that bookended agent captures output to JSONL."""

    def test_run_captures_to_jsonl(self):
        """WHEN run() completes THEN conversation is captured to JSONL file."""
        from soda.agents.bookended import BookendedAgent

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "outputs"
            agent = BookendedAgent(output_dir=output_dir)
            agent._invoke_agent = Mock(side_effect=["s1", "work", "w1"])

            result = agent.run(
                setup_prompts=["setup"],
                work_prompt="work",
                wrapup_prompts=["wrapup"]
            )

            # Check that output directory was created
            assert output_dir.exists()

            # Check that a JSONL file was created
            jsonl_files = list(output_dir.glob("*.jsonl"))
            assert len(jsonl_files) >= 1

    def test_jsonl_includes_agent_type_bookended(self):
        """WHEN output is captured THEN agent_type is 'bookended'."""
        from soda.agents.bookended import BookendedAgent

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "outputs"
            agent = BookendedAgent(output_dir=output_dir)
            agent._invoke_agent = Mock(side_effect=["s1", "work", "w1"])

            result = agent.run(
                setup_prompts=["setup"],
                work_prompt="work",
                wrapup_prompts=["wrapup"]
            )

            # Read the JSONL file
            jsonl_files = list(output_dir.glob("*.jsonl"))
            with open(jsonl_files[0]) as f:
                record = json.loads(f.readline())

            assert record["agent_type"] == "bookended"

    def test_output_capture_failure_does_not_affect_result(self):
        """WHEN output capture fails THEN run() still returns result."""
        from soda.agents.bookended import BookendedAgent

        agent = BookendedAgent()
        agent._invoke_agent = Mock(side_effect=["s1", "work", "w1"])
        agent._output_capture.capture = Mock(side_effect=Exception("Capture failed"))

        # Should still succeed
        result = agent.run(
            setup_prompts=["setup"],
            work_prompt="work",
            wrapup_prompts=["wrapup"]
        )

        assert result.work_response == "work"


class TestBookendedAgentConfig:
    """Test BookendedAgent configuration options."""

    def test_accepts_custom_config(self):
        """WHEN BookendedAgent receives custom config THEN it uses that config."""
        from soda.agents.bookended import BookendedAgent

        config = AgentConfig(model="claude-sonnet-4-20250514", max_tokens=8000)
        agent = BookendedAgent(config=config)

        assert agent._config.model == "claude-sonnet-4-20250514"
        assert agent._config.max_tokens == 8000

    def test_uses_default_config_if_none_provided(self):
        """WHEN no config provided THEN uses default AgentConfig."""
        from soda.agents.bookended import BookendedAgent

        agent = BookendedAgent()
        assert agent._config is not None
        assert agent._config.model == "claude-sonnet-4-20250514"


class TestBookendedAgentWithRetry:
    """Test that bookended agent uses retry handler for transient errors."""

    def test_uses_retry_handler(self):
        """WHEN BookendedAgent is created THEN it uses RetryHandler."""
        from soda.agents.bookended import BookendedAgent
        from soda.errors import RetryHandler

        agent = BookendedAgent()
        assert hasattr(agent, '_retry_handler')
        assert isinstance(agent._retry_handler, RetryHandler)


class TestBookendedAgentExport:
    """Test that BookendedAgent is properly exported."""

    def test_can_import_from_agents_module(self):
        """WHEN importing from soda.agents THEN BookendedAgent is available."""
        from soda.agents import BookendedAgent
        assert BookendedAgent is not None

    def test_can_import_bookended_result(self):
        """WHEN importing from soda.agents.bookended THEN BookendedResult is available."""
        from soda.agents.bookended import BookendedResult
        assert BookendedResult is not None
