"""Tests for verifier crash handling.

Verifies that:
1. Verifier errors are retried with exponential backoff
2. After all retries fail, UNCERTAIN outcome is used (not CONTINUE)
3. Crashed verifier does not silently pass iterations
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
import os
from pathlib import Path

from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext


class TestVerifierCrashHandling:
    """Test that verifier crashes are handled safely."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project context."""
        # Create a spec file
        spec_file = tmp_path / "Ralph2file"
        spec_file.write_text("# Test Spec\n\nTest specification content.")

        # Create project context
        project_dir = tmp_path / ".ralph2"
        project_dir.mkdir()

        ctx = ProjectContext(project_root=tmp_path)
        return ctx, str(spec_file)

    @pytest.mark.asyncio
    async def test_verifier_crash_results_in_uncertain_not_continue(self, temp_project):
        """Test that verifier crash results in UNCERTAIN outcome, not CONTINUE.

        This is critical - a crashed verifier should not silently pass an iteration.
        """
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        # Track what outcomes are recorded
        recorded_outcomes = []

        original_process = runner._process_verifier_result

        def tracking_process(iteration_ctx, result):
            if isinstance(result, Exception):
                recorded_outcomes.append(("exception", str(result)))
            else:
                recorded_outcomes.append(("success", result.get("outcome")))
            return original_process(iteration_ctx, result)

        runner._process_verifier_result = tracking_process

        # Create mock iteration context
        mock_ctx = MagicMock()
        mock_ctx.iteration_id = 1

        # Simulate a verifier exception
        error = Exception("Verifier agent crashed")
        assessment = runner._process_verifier_result(mock_ctx, error)

        # CRITICAL: The outcome should be UNCERTAIN, not CONTINUE
        assert "UNCERTAIN" in assessment, "Crashed verifier should use UNCERTAIN outcome"
        assert "CONTINUE" not in assessment.split("Outcome:")[1].split("\n")[0], \
            "Crashed verifier should NOT use CONTINUE outcome"

        runner.close()

    @pytest.mark.asyncio
    async def test_verifier_retries_on_error(self, temp_project):
        """Test that verifier is retried on transient errors."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def mock_verifier(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception(f"Transient error {call_count[0]}")
            return {
                "outcome": "CONTINUE",
                "assessment": "Success on retry",
                "messages": []
            }

        mock_ctx = MagicMock()
        mock_ctx.iteration_id = 1

        with patch('ralph2.runner.run_verifier', side_effect=mock_verifier):
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Speed up test
                result = await runner._run_verifier_with_retry(mock_ctx, max_retries=3)

        # Should have been called 3 times (2 failures, 1 success)
        assert call_count[0] == 3, f"Expected 3 calls, got {call_count[0]}"

        # Should have succeeded on the third attempt
        assert isinstance(result, dict), "Should return successful result"
        assert result["outcome"] == "CONTINUE"

        runner.close()

    @pytest.mark.asyncio
    async def test_verifier_returns_error_after_max_retries(self, temp_project):
        """Test that verifier returns the error after all retries are exhausted."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def always_fail(**kwargs):
            call_count[0] += 1
            raise Exception(f"Persistent error {call_count[0]}")

        mock_ctx = MagicMock()
        mock_ctx.iteration_id = 1

        with patch('ralph2.runner.run_verifier', side_effect=always_fail):
            with patch('asyncio.sleep', new_callable=AsyncMock):  # Speed up test
                result = await runner._run_verifier_with_retry(mock_ctx, max_retries=3)

        # Should have been called max_retries times
        assert call_count[0] == 3, f"Expected 3 calls, got {call_count[0]}"

        # Should return an Exception, not a result dict
        assert isinstance(result, Exception), "Should return Exception after max retries"
        assert "Persistent error" in str(result)

        runner.close()

    @pytest.mark.asyncio
    async def test_verifier_success_on_first_try(self, temp_project):
        """Test that verifier returns immediately on first successful call."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def succeed_immediately(**kwargs):
            call_count[0] += 1
            return {
                "outcome": "DONE",
                "assessment": "All criteria satisfied",
                "messages": []
            }

        mock_ctx = MagicMock()
        mock_ctx.iteration_id = 1

        with patch('ralph2.runner.run_verifier', side_effect=succeed_immediately):
            result = await runner._run_verifier_with_retry(mock_ctx, max_retries=3)

        # Should only be called once
        assert call_count[0] == 1, f"Expected 1 call, got {call_count[0]}"

        # Should return successful result
        assert isinstance(result, dict)
        assert result["outcome"] == "DONE"

        runner.close()
