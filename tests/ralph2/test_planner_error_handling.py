"""Tests for planner error handling.

Verifies that:
1. Recoverable errors are retried with exponential backoff
2. Fatal errors fail immediately without retry
3. Error classification correctly distinguishes recoverable from fatal
4. Pre-iteration health checks clean stale worktrees
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from ralph2.runner import Ralph2Runner
from ralph2.project import ProjectContext


class TestErrorClassification:
    """Test error classification logic."""

    @pytest.fixture
    def runner(self, tmp_path):
        """Create a runner for testing."""
        spec_file = tmp_path / "Ralph2file"
        spec_file.write_text("# Test Spec\n\nTest specification.")
        ctx = ProjectContext(project_root=tmp_path)
        return Ralph2Runner(str(spec_file), ctx)

    def test_rate_limit_error_is_recoverable(self, runner):
        """Rate limit errors should be recoverable."""
        error = Exception("Rate limit exceeded: 429 Too Many Requests")
        assert runner._is_recoverable_error(error) is True
        runner.close()

    def test_overloaded_error_is_recoverable(self, runner):
        """Overloaded service errors should be recoverable."""
        error = Exception("Service overloaded, please try again")
        assert runner._is_recoverable_error(error) is True
        runner.close()

    def test_timeout_error_is_recoverable(self, runner):
        """Timeout errors should be recoverable."""
        error = Exception("Request timeout after 30 seconds")
        assert runner._is_recoverable_error(error) is True
        runner.close()

    def test_connection_error_is_recoverable(self, runner):
        """Connection errors should be recoverable."""
        error = Exception("Connection refused to api.anthropic.com")
        assert runner._is_recoverable_error(error) is True
        runner.close()

    def test_503_error_is_recoverable(self, runner):
        """503 Service Unavailable errors should be recoverable."""
        error = Exception("HTTP 503 Service Unavailable")
        assert runner._is_recoverable_error(error) is True
        runner.close()

    def test_api_key_error_is_fatal(self, runner):
        """API key errors should be fatal."""
        error = Exception("Invalid API key provided")
        assert runner._is_recoverable_error(error) is False
        runner.close()

    def test_authentication_error_is_fatal(self, runner):
        """Authentication errors should be fatal."""
        error = Exception("Authentication failed: invalid credentials")
        assert runner._is_recoverable_error(error) is False
        runner.close()

    def test_401_error_is_fatal(self, runner):
        """401 Unauthorized errors should be fatal."""
        error = Exception("HTTP 401 Unauthorized")
        assert runner._is_recoverable_error(error) is False
        runner.close()

    def test_permission_denied_is_fatal(self, runner):
        """Permission denied errors should be fatal."""
        error = Exception("Permission denied: cannot access resource")
        assert runner._is_recoverable_error(error) is False
        runner.close()

    def test_file_not_found_is_fatal(self, runner):
        """File not found errors should be fatal."""
        error = Exception("File not found: /path/to/spec")
        assert runner._is_recoverable_error(error) is False
        runner.close()

    def test_unknown_error_defaults_to_recoverable(self, runner):
        """Unknown errors should default to recoverable (safer for retry)."""
        error = Exception("Some weird error that doesn't match any pattern")
        assert runner._is_recoverable_error(error) is True
        runner.close()


class TestPlannerRetry:
    """Test planner retry logic."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project context."""
        spec_file = tmp_path / "Ralph2file"
        spec_file.write_text("# Test Spec\n\nTest specification.")
        ctx = ProjectContext(project_root=tmp_path)
        return ctx, str(spec_file)

    @pytest.mark.asyncio
    async def test_planner_retries_on_recoverable_error(self, temp_project):
        """Test that planner retries on recoverable errors."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def mock_planner(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Rate limit exceeded")
            return {
                "intent": "Test intent",
                "decision": {"decision": "CONTINUE", "reason": "Work needed"},
                "messages": []
            }

        mock_ctx = MagicMock()
        mock_ctx.last_executor_summary = None
        mock_ctx.last_verifier_assessment = None
        mock_ctx.last_specialist_feedback = None

        with patch('ralph2.runner.run_planner', side_effect=mock_planner):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result, error = await runner._run_planner_with_retry(mock_ctx, [], max_retries=3)

        # Should have been called 3 times (2 failures, 1 success)
        assert call_count[0] == 3
        assert result is not None
        assert error is None

        runner.close()

    @pytest.mark.asyncio
    async def test_planner_fails_immediately_on_fatal_error(self, temp_project):
        """Test that planner fails immediately on fatal errors without retry."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def mock_planner(**kwargs):
            call_count[0] += 1
            raise Exception("Invalid API key")

        mock_ctx = MagicMock()
        mock_ctx.last_executor_summary = None
        mock_ctx.last_verifier_assessment = None
        mock_ctx.last_specialist_feedback = None

        with patch('ralph2.runner.run_planner', side_effect=mock_planner):
            result, error = await runner._run_planner_with_retry(mock_ctx, [], max_retries=3)

        # Should have been called only once (fatal error, no retry)
        assert call_count[0] == 1
        assert result is None
        assert error is not None
        assert "API key" in str(error)

        runner.close()

    @pytest.mark.asyncio
    async def test_planner_returns_error_after_max_retries(self, temp_project):
        """Test that planner returns error after exhausting all retries."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def always_fail(**kwargs):
            call_count[0] += 1
            raise Exception("Connection timeout")

        mock_ctx = MagicMock()
        mock_ctx.last_executor_summary = None
        mock_ctx.last_verifier_assessment = None
        mock_ctx.last_specialist_feedback = None

        with patch('ralph2.runner.run_planner', side_effect=always_fail):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result, error = await runner._run_planner_with_retry(mock_ctx, [], max_retries=3)

        # Should have been called max_retries times
        assert call_count[0] == 3
        assert result is None
        assert error is not None

        runner.close()

    @pytest.mark.asyncio
    async def test_planner_succeeds_on_first_try(self, temp_project):
        """Test that planner returns immediately on first successful call."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        call_count = [0]

        async def succeed_immediately(**kwargs):
            call_count[0] += 1
            return {
                "intent": "Test intent",
                "decision": {"decision": "DONE", "reason": "Complete"},
                "messages": []
            }

        mock_ctx = MagicMock()
        mock_ctx.last_executor_summary = None
        mock_ctx.last_verifier_assessment = None
        mock_ctx.last_specialist_feedback = None

        with patch('ralph2.runner.run_planner', side_effect=succeed_immediately):
            result, error = await runner._run_planner_with_retry(mock_ctx, [], max_retries=3)

        # Should only be called once
        assert call_count[0] == 1
        assert result is not None
        assert error is None

        runner.close()


class TestPreIterationHealthCheck:
    """Test pre-iteration health checks."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project context."""
        spec_file = tmp_path / "Ralph2file"
        spec_file.write_text("# Test Spec\n\nTest specification.")
        ctx = ProjectContext(project_root=tmp_path)
        return ctx, str(spec_file)

    @pytest.mark.asyncio
    async def test_planner_phase_cleans_stale_worktrees(self, temp_project):
        """Test that planner phase runs cleanup before starting."""
        ctx, spec_file = temp_project
        runner = Ralph2Runner(spec_file, ctx)

        cleanup_called = [False]
        original_cleanup = runner._cleanup_abandoned_branches

        def tracking_cleanup():
            cleanup_called[0] = True
            # Don't actually run cleanup in test

        runner._cleanup_abandoned_branches = tracking_cleanup

        mock_ctx = MagicMock()
        mock_ctx.iteration_id = 1
        mock_ctx.run_id = "test-run"
        mock_ctx.last_executor_summary = None
        mock_ctx.last_verifier_assessment = None
        mock_ctx.last_specialist_feedback = None

        async def mock_planner(**kwargs):
            return {
                "intent": "Test",
                "decision": {"decision": "CONTINUE", "reason": "Work"},
                "messages": []
            }

        with patch('ralph2.runner.run_planner', side_effect=mock_planner):
            with patch.object(runner.db, 'create_agent_output'):
                with patch.object(runner, '_save_agent_messages', return_value='/tmp/test'):
                    await runner._run_planner_phase(mock_ctx, [])

        # Cleanup should have been called at the start of the phase
        assert cleanup_called[0], "Pre-iteration cleanup should be called"

        runner.close()
