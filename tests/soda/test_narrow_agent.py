"""Tests for NarrowAgent pattern.

These tests verify the narrow agent pattern - single-shot agent with
structured output, optional tool restriction, and conversation capture.
"""

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from soda.types import StructuredOutput


class TestNarrowAgentImport:
    """Test that NarrowAgent can be imported."""

    def test_import_narrow_agent(self):
        """WHEN importing NarrowAgent THEN it should succeed."""
        from soda.agents.narrow import NarrowAgent
        assert NarrowAgent is not None

    def test_narrow_agent_is_class(self):
        """WHEN importing NarrowAgent THEN it should be a class."""
        from soda.agents.narrow import NarrowAgent
        assert isinstance(NarrowAgent, type)


class TestNarrowAgentInstantiation:
    """Test NarrowAgent instantiation."""

    def test_create_narrow_agent_default(self):
        """WHEN creating NarrowAgent with defaults THEN it succeeds."""
        from soda.agents.narrow import NarrowAgent
        agent = NarrowAgent()
        assert agent is not None

    def test_create_narrow_agent_with_output_dir(self):
        """WHEN creating NarrowAgent with output_dir THEN it's set."""
        from soda.agents.narrow import NarrowAgent
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = NarrowAgent(output_dir=Path(tmpdir))
            assert agent.output_dir == Path(tmpdir)


class TestNarrowAgentInterface:
    """Test NarrowAgent has the expected interface."""

    def test_narrow_agent_has_invoke_method(self):
        """WHEN creating NarrowAgent THEN it has invoke method."""
        from soda.agents.narrow import NarrowAgent
        agent = NarrowAgent()
        assert hasattr(agent, 'invoke')
        assert callable(agent.invoke)


# Define test output schemas
class SimpleOutput(StructuredOutput):
    """Simple test output schema."""
    result: str


class ScoredOutput(StructuredOutput):
    """Output schema with a score."""
    result: str
    score: int


class AnalysisOutput(StructuredOutput):
    """Output schema for analysis results."""
    findings: list[str]
    severity: str
    recommendation: Optional[str] = None


class TestNarrowAgentInvoke:
    """Test NarrowAgent.invoke() behavior."""

    @pytest.mark.asyncio
    async def test_invoke_returns_structured_output(self):
        """WHEN invoke() succeeds THEN it returns parsed Pydantic model."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        # Mock the Claude SDK to return a valid response
        mock_response = '{"result": "success"}'
        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput
            )

        assert isinstance(result, SimpleOutput)
        assert result.result == "success"

    @pytest.mark.asyncio
    async def test_invoke_returns_complex_output(self):
        """WHEN invoke() returns complex data THEN it's properly parsed."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        mock_response = json.dumps({
            "findings": ["Issue 1", "Issue 2"],
            "severity": "high",
            "recommendation": "Fix immediately"
        })
        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await agent.invoke(
                prompt="Analyze the code",
                output_schema=AnalysisOutput
            )

        assert isinstance(result, AnalysisOutput)
        assert result.findings == ["Issue 1", "Issue 2"]
        assert result.severity == "high"
        assert result.recommendation == "Fix immediately"

    @pytest.mark.asyncio
    async def test_invoke_passes_prompt_to_agent(self):
        """WHEN invoke() called THEN prompt is passed to underlying agent."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="My test prompt",
                output_schema=SimpleOutput
            )

        # Verify prompt was passed
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert "My test prompt" in str(call_args)


class TestNarrowAgentToolRestriction:
    """Test NarrowAgent tool allowlist functionality."""

    @pytest.mark.asyncio
    async def test_invoke_without_tools_uses_all_tools(self):
        """WHEN invoke() called without tools THEN all tools are available."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                tools=None
            )

        # Verify tools was None (all tools)
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('tools') is None

    @pytest.mark.asyncio
    async def test_invoke_with_tools_restricts_tools(self):
        """WHEN invoke() called with tools THEN only those tools are available."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                tools=["Read", "Write"]
            )

        # Verify tools were passed
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('tools') == ["Read", "Write"]

    @pytest.mark.asyncio
    async def test_invoke_with_empty_tools_list(self):
        """WHEN invoke() called with empty tools list THEN agent has no tools."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                tools=[]
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('tools') == []


class TestNarrowAgentOutputCapture:
    """Test that NarrowAgent captures outputs to JSONL."""

    @pytest.mark.asyncio
    async def test_invoke_captures_output(self):
        """WHEN invoke() completes THEN output is captured to JSONL file."""
        from soda.agents.narrow import NarrowAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            agent = NarrowAgent(output_dir=output_dir)

            with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = '{"result": "captured"}'

                await agent.invoke(
                    prompt="Test prompt for capture",
                    output_schema=SimpleOutput
                )

            # Verify JSONL file was created
            jsonl_files = list(output_dir.glob("*.jsonl"))
            assert len(jsonl_files) == 1

            # Verify content
            with open(jsonl_files[0]) as f:
                record = json.loads(f.readline())

            assert record["agent_type"] == "narrow"
            assert "Test prompt" in record["prompt_summary"]
            assert "timestamp" in record

    @pytest.mark.asyncio
    async def test_invoke_captures_prompt_summary(self):
        """WHEN invoke() completes THEN prompt summary is captured."""
        from soda.agents.narrow import NarrowAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            agent = NarrowAgent(output_dir=output_dir)

            long_prompt = "This is a very long prompt that should be truncated " * 10

            with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = '{"result": "success"}'

                await agent.invoke(
                    prompt=long_prompt,
                    output_schema=SimpleOutput
                )

            jsonl_files = list(output_dir.glob("*.jsonl"))
            with open(jsonl_files[0]) as f:
                record = json.loads(f.readline())

            # Prompt summary should be truncated (first 100 chars or so)
            assert len(record["prompt_summary"]) <= 103  # 100 + "..."

    @pytest.mark.asyncio
    async def test_capture_failure_does_not_affect_result(self):
        """WHEN output capture fails THEN invoke() still returns result."""
        from soda.agents.narrow import NarrowAgent
        from soda.outputs import OutputCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            agent = NarrowAgent(output_dir=output_dir)

            with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
                mock_call.return_value = '{"result": "still works"}'

                # Make capture fail
                with patch.object(OutputCapture, 'capture', side_effect=Exception("Capture failed")):
                    result = await agent.invoke(
                        prompt="Test prompt",
                        output_schema=SimpleOutput
                    )

            # Result should still be returned
            assert result.result == "still works"


class TestNarrowAgentValidation:
    """Test NarrowAgent schema validation."""

    @pytest.mark.asyncio
    async def test_invalid_output_raises_validation_error(self):
        """WHEN agent returns invalid output THEN validation error is raised."""
        from soda.agents.narrow import NarrowAgent
        from soda.validation import StructuredOutputValidationError

        agent = NarrowAgent()

        # Return output missing required field
        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"wrong_field": "value"}'

            with pytest.raises(StructuredOutputValidationError) as exc_info:
                await agent.invoke(
                    prompt="Test prompt",
                    output_schema=SimpleOutput
                )

        assert "result" in str(exc_info.value).lower() or "field" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_json_raises_validation_error(self):
        """WHEN agent returns invalid JSON THEN validation error is raised."""
        from soda.agents.narrow import NarrowAgent
        from soda.validation import StructuredOutputValidationError

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = 'not valid json at all'

            with pytest.raises(StructuredOutputValidationError) as exc_info:
                await agent.invoke(
                    prompt="Test prompt",
                    output_schema=SimpleOutput
                )

        assert "json" in str(exc_info.value).lower()


class TestNarrowAgentErrorHandling:
    """Test NarrowAgent error handling and retry behavior."""

    @pytest.mark.asyncio
    async def test_transient_error_is_retried(self):
        """WHEN transient error occurs THEN invoke() retries."""
        from soda.agents.narrow import NarrowAgent
        from soda.errors import TransientError

        agent = NarrowAgent()

        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TransientError("Rate limited", status_code=429)
            return '{"result": "success"}'

        with patch.object(agent, '_call_agent', side_effect=mock_call):
            result = await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput
            )

        assert result.result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_fatal_error_halts_immediately(self):
        """WHEN fatal error occurs THEN invoke() halts immediately."""
        from soda.agents.narrow import NarrowAgent
        from soda.errors import FatalError

        agent = NarrowAgent()

        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise FatalError("Invalid API key", status_code=401)

        with patch.object(agent, '_call_agent', side_effect=mock_call):
            with pytest.raises(FatalError):
                await agent.invoke(
                    prompt="Test prompt",
                    output_schema=SimpleOutput
                )

        # Should not retry
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises_error(self):
        """WHEN max retries exhausted THEN appropriate error is raised."""
        from soda.agents.narrow import NarrowAgent
        from soda.errors import MaxRetriesExhaustedError, TransientError

        agent = NarrowAgent()

        async def mock_call(*args, **kwargs):
            raise TransientError("Always fails", status_code=500)

        with patch.object(agent, '_call_agent', side_effect=mock_call):
            with pytest.raises(MaxRetriesExhaustedError):
                await agent.invoke(
                    prompt="Test prompt",
                    output_schema=SimpleOutput
                )


class TestNarrowAgentModel:
    """Test NarrowAgent model configuration."""

    @pytest.mark.asyncio
    async def test_invoke_uses_default_model(self):
        """WHEN invoke() called without model THEN model is None (SDK default)."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput
            )

        call_kwargs = mock_call.call_args.kwargs
        # When no model specified, we pass None to let SDK use its default
        assert call_kwargs.get('model') is None

    @pytest.mark.asyncio
    async def test_invoke_with_custom_model(self):
        """WHEN invoke() called with model THEN that model is used."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                model="claude-opus-4-20250514"
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('model') == "claude-opus-4-20250514"


class TestNarrowAgentSystemPrompt:
    """Test NarrowAgent system_prompt parameter functionality."""

    @pytest.mark.asyncio
    async def test_invoke_without_system_prompt(self):
        """WHEN invoke() called without system_prompt THEN it is None."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('system_prompt') is None

    @pytest.mark.asyncio
    async def test_invoke_with_system_prompt(self):
        """WHEN invoke() called with system_prompt THEN it is passed to agent."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        test_system_prompt = "You are a helpful assistant that follows instructions carefully."

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                system_prompt=test_system_prompt
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('system_prompt') == test_system_prompt

    @pytest.mark.asyncio
    async def test_invoke_with_long_system_prompt(self):
        """WHEN invoke() called with long system_prompt THEN it is passed fully."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        # Simulate ORIENT-style system prompt (long, detailed instructions)
        long_system_prompt = """You are the ORIENT agent in the SODA loop.

Your responsibilities:
1. Verify claims against the codebase
2. Assess spec satisfaction
3. Update task breakdown
4. Plan the iteration

Key behaviors:
- When claims say a task is closed, verify the code actually implements it
- When a task is marked closed but code doesn't implement it, flag discrepancy
- When assessing spec, evaluate each acceptance criterion individually
""" * 10  # Make it even longer

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                system_prompt=long_system_prompt
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('system_prompt') == long_system_prompt

    @pytest.mark.asyncio
    async def test_invoke_with_all_parameters(self):
        """WHEN invoke() called with all parameters THEN all are passed."""
        from soda.agents.narrow import NarrowAgent

        agent = NarrowAgent()

        with patch.object(agent, '_call_agent', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"result": "success"}'

            await agent.invoke(
                prompt="Test prompt",
                output_schema=SimpleOutput,
                tools=["Read", "Grep"],
                model="claude-sonnet-4-20250514",
                system_prompt="You are an analysis agent."
            )

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs.get('prompt') == "Test prompt"
        assert call_kwargs.get('tools') == ["Read", "Grep"]
        assert call_kwargs.get('model') == "claude-sonnet-4-20250514"
        assert call_kwargs.get('system_prompt') == "You are an analysis agent."
