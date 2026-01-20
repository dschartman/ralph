"""Tests for soda package scaffolding.

These tests verify the foundational package structure is correctly set up.
"""

import pytest


class TestPackageImports:
    """Test that package imports work correctly."""

    def test_import_soda(self):
        """WHEN importing soda THEN it should succeed."""
        import soda
        assert soda is not None

    def test_soda_has_version(self):
        """WHEN importing soda THEN it should have a version."""
        import soda
        assert hasattr(soda, "__version__")
        assert soda.__version__ == "0.1.0"

    def test_soda_hello(self):
        """WHEN calling soda.hello() THEN it returns expected greeting."""
        import soda
        assert soda.hello() == "Hello from soda!"

    def test_import_soda_agents(self):
        """WHEN importing soda.agents THEN it should succeed."""
        import soda.agents
        assert soda.agents is not None

    def test_import_soda_outputs(self):
        """WHEN importing soda.outputs THEN it should succeed."""
        import soda.outputs
        assert soda.outputs is not None

    def test_import_soda_types(self):
        """WHEN importing soda.types THEN it should succeed."""
        import soda.types
        assert soda.types is not None


class TestTypeDefinitions:
    """Test that type definitions are properly defined."""

    def test_agent_config_exists(self):
        """WHEN importing AgentConfig THEN it should be a Pydantic model."""
        from soda.types import AgentConfig
        from pydantic import BaseModel
        assert issubclass(AgentConfig, BaseModel)

    def test_agent_config_default_values(self):
        """WHEN creating AgentConfig with defaults THEN defaults are set."""
        from soda.types import AgentConfig
        config = AgentConfig()
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 16000
        assert config.tools is None

    def test_agent_config_custom_values(self):
        """WHEN creating AgentConfig with custom values THEN they are set."""
        from soda.types import AgentConfig
        config = AgentConfig(
            model="claude-opus-4-20250514",
            max_tokens=8000,
            tools=["read", "write"]
        )
        assert config.model == "claude-opus-4-20250514"
        assert config.max_tokens == 8000
        assert config.tools == ["read", "write"]

    def test_structured_output_exists(self):
        """WHEN importing StructuredOutput THEN it should be a Pydantic model."""
        from soda.types import StructuredOutput
        from pydantic import BaseModel
        assert issubclass(StructuredOutput, BaseModel)

    def test_structured_output_subclass(self):
        """WHEN subclassing StructuredOutput THEN custom fields work."""
        from soda.types import StructuredOutput

        class MyOutput(StructuredOutput):
            result: str
            score: int

        output = MyOutput(result="success", score=100)
        assert output.result == "success"
        assert output.score == 100

    def test_agent_invocation_exists(self):
        """WHEN importing AgentInvocation THEN it should be a Pydantic model."""
        from soda.types import AgentInvocation, AgentConfig
        from pydantic import BaseModel
        assert issubclass(AgentInvocation, BaseModel)

        invocation = AgentInvocation(
            timestamp="2024-01-20T12:00:00Z",
            agent_type="narrow",
            prompt_summary="Test prompt",
            config=AgentConfig()
        )
        assert invocation.agent_type == "narrow"

    def test_message_exists(self):
        """WHEN importing Message THEN it should be a Pydantic model."""
        from soda.types import Message
        from pydantic import BaseModel
        assert issubclass(Message, BaseModel)

        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_conversation_exists(self):
        """WHEN importing Conversation THEN it should be a Pydantic model."""
        from soda.types import Conversation, AgentInvocation, AgentConfig, Message
        from pydantic import BaseModel
        assert issubclass(Conversation, BaseModel)

        conv = Conversation(
            invocation=AgentInvocation(
                timestamp="2024-01-20T12:00:00Z",
                agent_type="walked",
                prompt_summary="Test",
                config=AgentConfig()
            ),
            messages=[Message(role="user", content="Hello")]
        )
        assert conv.invocation.agent_type == "walked"
        assert len(conv.messages) == 1

    def test_agent_error_exists(self):
        """WHEN importing AgentError THEN it should be a Pydantic model."""
        from soda.types import AgentError
        from pydantic import BaseModel
        assert issubclass(AgentError, BaseModel)

        error = AgentError(
            error_type="transient",
            message="Rate limit exceeded",
            retry_count=1
        )
        assert error.error_type == "transient"
        assert error.retry_count == 1

    def test_validation_error_exists(self):
        """WHEN importing ValidationError THEN it should be a Pydantic model."""
        from soda.types import ValidationError
        from pydantic import BaseModel
        assert issubclass(ValidationError, BaseModel)

        val_error = ValidationError(
            field="result",
            error="field required"
        )
        assert val_error.field == "result"
