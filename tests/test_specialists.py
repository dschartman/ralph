"""Tests for Specialist framework and Code Reviewer."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

from src.ralph2.agents.specialist import (
    Specialist,
    CodeReviewerSpecialist,
    run_specialist,
)
from claude_agent_sdk.types import AssistantMessage, TextBlock


class TestSpecialistBase:
    """Test the Specialist base class."""

    def test_specialist_is_abstract(self):
        """Specialist base class should not be directly instantiable."""
        # Attempting to instantiate directly should raise TypeError
        with pytest.raises(TypeError):
            Specialist()

    def test_specialist_requires_run_method(self):
        """Subclasses must implement the run() method."""
        # Create a subclass that doesn't implement run()
        class IncompleteSpecialist(Specialist):
            pass

        with pytest.raises(TypeError):
            IncompleteSpecialist()


class TestCodeReviewerSpecialist:
    """Test the Code Reviewer specialist."""

    @pytest.mark.asyncio
    async def test_code_reviewer_initialization(self):
        """Code Reviewer should initialize with name and tools."""
        reviewer = CodeReviewerSpecialist()

        assert reviewer.name == "code_reviewer"
        assert reviewer.allowed_tools == ["Read", "Glob", "Grep", "Bash"]

    @pytest.mark.asyncio
    async def test_code_reviewer_analyzes_code(self):
        """Code Reviewer should analyze code and produce feedback."""
        reviewer = CodeReviewerSpecialist()

        spec_content = """
        # Test Spec

        Build a user authentication system.

        ## Acceptance Criteria
        - [ ] Users can register
        - [ ] Users can login
        """

        memory = "Use UV for package management"

        # Mock the Claude SDK query function
        # Create proper TextBlock mocks
        text_block_1 = Mock()
        text_block_1.text = "Analyzing codebase for maintainability issues..."
        text_block_1.__class__ = TextBlock

        text_block_2 = Mock()
        text_block_2.text = "SPECIALIST_FEEDBACK:\nFeedback items:\n- Add type hints to functions\n- Extract magic numbers to constants"
        text_block_2.__class__ = TextBlock

        # Create AssistantMessage mocks
        msg1 = Mock()
        msg1.__class__ = AssistantMessage
        msg1.content = [text_block_1]
        msg1.model_dump = Mock(return_value={"type": "assistant", "content": "Analyzing..."})

        msg2 = Mock()
        msg2.__class__ = AssistantMessage
        msg2.content = [text_block_2]
        msg2.model_dump = Mock(return_value={"type": "assistant", "content": "SPECIALIST_FEEDBACK..."})

        mock_messages = [msg1, msg2]

        async def mock_query(*args, **kwargs):
            for msg in mock_messages:
                yield msg

        with patch("src.ralph2.agents.specialist.query", side_effect=mock_query):
            result = await reviewer.run(spec_content=spec_content, memory=memory)

        # Should return feedback with items
        assert result["specialist_name"] == "code_reviewer"
        assert "feedback" in result
        assert len(result["feedback"]) == 2  # Two feedback items
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_code_reviewer_parses_feedback_items(self):
        """Code Reviewer should parse feedback items from output."""
        reviewer = CodeReviewerSpecialist()

        spec_content = "# Test Spec\n\nBuild something."

        # Create proper TextBlock mock with feedback
        text_block = Mock()
        text_block.__class__ = TextBlock
        text_block.text = """
SPECIALIST_FEEDBACK:
Feedback items:
- [P1] Add error handling to API endpoints
- [P2] Improve test coverage in auth module
- [P0] Fix critical security vulnerability in password hashing
"""

        # Create AssistantMessage mock
        msg = Mock()
        msg.__class__ = AssistantMessage
        msg.content = [text_block]
        msg.model_dump = Mock(return_value={"type": "assistant", "content": "Done"})

        mock_messages = [msg]

        async def mock_query(*args, **kwargs):
            for msg in mock_messages:
                yield msg

        with patch("src.ralph2.agents.specialist.query", side_effect=mock_query):
            result = await reviewer.run(spec_content=spec_content, memory="")

        # Should parse 3 feedback items with priorities
        assert len(result["feedback"]) == 3

        # Check that priorities are extracted
        items_with_p0 = [item for item in result["feedback"] if "P0" in item or "critical" in item.lower()]
        assert len(items_with_p0) >= 1


class TestRunSpecialist:
    """Test the run_specialist helper function."""

    @pytest.mark.asyncio
    async def test_run_specialist_invokes_specialist(self):
        """run_specialist should invoke the specialist's run method."""
        mock_specialist = Mock()
        mock_specialist.run = AsyncMock(return_value={
            "specialist_name": "test",
            "feedback": ["item1"],
            "messages": []
        })

        result = await run_specialist(
            specialist=mock_specialist,
            spec_content="# Test",
            memory="test memory"
        )

        mock_specialist.run.assert_called_once()
        assert result["specialist_name"] == "test"
        assert result["feedback"] == ["item1"]

    @pytest.mark.asyncio
    async def test_run_specialist_handles_errors(self):
        """run_specialist should handle errors gracefully."""
        mock_specialist = Mock()
        mock_specialist.run = AsyncMock(side_effect=Exception("Test error"))
        mock_specialist.name = "failing_specialist"

        result = await run_specialist(
            specialist=mock_specialist,
            spec_content="# Test",
            memory=""
        )

        # Should return error result
        assert result["specialist_name"] == "failing_specialist"
        assert "error" in result
        assert "Test error" in result["error"]
