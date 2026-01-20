"""Tests for Verifier commenting on root work item."""

import pytest
from unittest.mock import MagicMock, patch, call
from ralph2.agents.verifier import run_verifier


class TestVerifierCommenting:
    """Test that verifier posts verdict as comment on root work item."""

    @pytest.mark.asyncio
    async def test_verifier_posts_verdict_comment_on_root_work_item(self):
        """Test that verifier calls trc comment with root work item ID and verdict."""
        bash_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            # Capture all bash commands for verification
            if isinstance(cmd, list):
                bash_commands.append(' '.join(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                msg = MagicMock(spec=AssistantMessage)
                msg.content = [MagicMock(
                    spec=TextBlock,
                    text="VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nCriteria Status:\n- Test criterion: ✗ not satisfied\nGaps: Missing feature X\nEfficiency Notes: None"
                )]
                msg.result = "Assessment complete"
                yield msg

            with patch('ralph2.agents.verifier.query', side_effect=mock_query):
                result = await run_verifier(
                    spec_content="# Test Spec\n\n## Acceptance Criteria\n- [ ] Test criterion",
                    memory="",
                    root_work_item_id="ralph-test123"
                )

        # Verify trc comment was called with root work item ID and verdict
        trc_comment_calls = [cmd for cmd in bash_commands if 'trc comment' in cmd and 'ralph-test123' in cmd]
        assert len(trc_comment_calls) > 0, f"Expected trc comment call for root work item, but found: {bash_commands}"

        # Verify the comment includes --source verifier
        trc_call = trc_comment_calls[0]
        assert '--source verifier' in trc_call, f"Expected --source verifier in trc comment, got: {trc_call}"

        # Verify the comment includes the verdict (should contain VERIFIER_ASSESSMENT or outcome)
        assert 'CONTINUE' in trc_call or 'VERIFIER_ASSESSMENT' in trc_call, f"Expected verdict in comment, got: {trc_call}"

    @pytest.mark.asyncio
    async def test_verifier_includes_full_assessment_in_comment(self):
        """Test that verifier includes the full assessment text in the comment."""
        bash_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                bash_commands.append(' '.join(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                msg = MagicMock(spec=AssistantMessage)
                msg.content = [MagicMock(
                    spec=TextBlock,
                    text="VERIFIER_ASSESSMENT:\nOutcome: DONE\nCriteria Status:\n- All criteria: ✓ satisfied\nGaps: None\nEfficiency Notes: None"
                )]
                msg.result = "Assessment complete"
                yield msg

            with patch('ralph2.agents.verifier.query', side_effect=mock_query):
                result = await run_verifier(
                    spec_content="# Test Spec\n\n## Acceptance Criteria\n- [x] All criteria",
                    memory="",
                    root_work_item_id="ralph-done"
                )

        # Find the trc comment call
        trc_comment_calls = [cmd for cmd in bash_commands if 'trc comment ralph-done' in cmd]
        assert len(trc_comment_calls) > 0, "Expected trc comment call"

        trc_call = trc_comment_calls[0]
        # The assessment should be in the comment (may be escaped or quoted)
        assert 'DONE' in trc_call, f"Expected DONE outcome in comment, got: {trc_call}"

    @pytest.mark.asyncio
    async def test_verifier_still_works_without_root_work_item_id(self):
        """Test that verifier works in backward compatibility mode without root_work_item_id."""
        bash_commands = []

        def mock_subprocess_run(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                bash_commands.append(' '.join(cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            async def mock_query(*args, **kwargs):
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                msg = MagicMock(spec=AssistantMessage)
                msg.content = [MagicMock(
                    spec=TextBlock,
                    text="VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nCriteria Status:\n- Test: ✗ not satisfied\nGaps: Missing\nEfficiency Notes: None"
                )]
                msg.result = "Assessment complete"
                yield msg

            with patch('ralph2.agents.verifier.query', side_effect=mock_query):
                # Call without root_work_item_id (backward compatibility)
                result = await run_verifier(
                    spec_content="# Test Spec\n\n## Acceptance Criteria\n- [ ] Test",
                    memory=""
                )

        # Verify no trc comment was called (backward compatibility)
        trc_comment_calls = [cmd for cmd in bash_commands if 'trc comment' in cmd]
        assert len(trc_comment_calls) == 0, f"Expected no trc comment without root_work_item_id, but found: {trc_comment_calls}"

        # Verify the verifier still returned a valid result
        assert result["outcome"] == "CONTINUE"
        assert "VERIFIER_ASSESSMENT" in result["assessment"]
