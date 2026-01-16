"""Tests for planner ITERATION_PLAN output format."""

import pytest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

from ralph2.agents.planner import run_planner, parse_iteration_plan


class TestIterationPlanFormat:
    """Test that planner outputs properly formatted ITERATION_PLAN."""

    @pytest.mark.asyncio
    async def test_planner_outputs_iteration_plan_structure(self):
        """Test that planner output includes ITERATION_PLAN with work items and executor count."""
        spec = """
        # Test Spec
        Build a feature with multiple components.
        """

        # Mock the Claude agent query to return a plan with ITERATION_PLAN
        mock_output = """
Based on the task backlog, I'll work on these items:

ITERATION_PLAN:
Executor Count: 2
Work Items:
- ralph-abc123: Implement database schema (Executor 1)
- ralph-def456: Create API endpoints (Executor 2)

ITERATION_INTENT: Implement database schema and API endpoints in parallel
"""

        with patch('ralph2.agents.planner.query') as mock_query:
            # Mock the async generator
            async def mock_query_gen(*args, **kwargs):
                # Return a mock message with text content
                from claude_agent_sdk.types import AssistantMessage, TextBlock

                msg = MagicMock(spec=AssistantMessage)
                msg.content = [MagicMock(spec=TextBlock, text=mock_output)]
                yield msg

            mock_query.return_value = mock_query_gen()

            result = await run_planner(
                spec_content=spec,
                memory="",
                project_id="test-project"
            )

        # Verify the result contains iteration_plan key
        assert "iteration_plan" in result
        assert result["iteration_plan"] is not None

        # Verify iteration plan structure
        plan = result["iteration_plan"]
        assert "executor_count" in plan
        assert "work_items" in plan

        # Verify executor count
        assert plan["executor_count"] == 2

        # Verify work items structure
        assert len(plan["work_items"]) == 2

        work_item_1 = plan["work_items"][0]
        assert "work_item_id" in work_item_1
        assert "description" in work_item_1
        assert "executor_number" in work_item_1

        assert work_item_1["work_item_id"] == "ralph-abc123"
        assert "database schema" in work_item_1["description"].lower()
        assert work_item_1["executor_number"] == 1

        work_item_2 = plan["work_items"][1]
        assert work_item_2["work_item_id"] == "ralph-def456"
        assert "api endpoints" in work_item_2["description"].lower()
        assert work_item_2["executor_number"] == 2

    def test_parse_iteration_plan_from_text(self):
        """Test parsing ITERATION_PLAN from planner output text."""
        output_text = """
I've reviewed the tasks and will work on these:

ITERATION_PLAN:
Executor Count: 3
Work Items:
- ralph-abc123: Implement database schema (Executor 1)
- ralph-def456: Create API endpoints (Executor 2)
- ralph-ghi789: Write unit tests (Executor 3)

ITERATION_INTENT: Complete core implementation with tests
"""

        plan = parse_iteration_plan(output_text)

        assert plan is not None
        assert plan["executor_count"] == 3
        assert len(plan["work_items"]) == 3

        assert plan["work_items"][0] == {
            "work_item_id": "ralph-abc123",
            "description": "Implement database schema",
            "executor_number": 1
        }

        assert plan["work_items"][1] == {
            "work_item_id": "ralph-def456",
            "description": "Create API endpoints",
            "executor_number": 2
        }

        assert plan["work_items"][2] == {
            "work_item_id": "ralph-ghi789",
            "description": "Write unit tests",
            "executor_number": 3
        }

    def test_parse_iteration_plan_single_executor(self):
        """Test parsing ITERATION_PLAN with single executor."""
        output_text = """
ITERATION_PLAN:
Executor Count: 1
Work Items:
- ralph-xyz999: Fix critical bug (Executor 1)

ITERATION_INTENT: Address critical bug
"""

        plan = parse_iteration_plan(output_text)

        assert plan is not None
        assert plan["executor_count"] == 1
        assert len(plan["work_items"]) == 1
        assert plan["work_items"][0]["executor_number"] == 1

    def test_parse_iteration_plan_returns_none_when_missing(self):
        """Test that parse returns None when ITERATION_PLAN is not in output."""
        output_text = """
Just some regular output without an iteration plan.

ITERATION_INTENT: Do some work
"""

        plan = parse_iteration_plan(output_text)

        assert plan is None

    def test_parse_iteration_plan_handles_malformed_input(self):
        """Test graceful handling of malformed ITERATION_PLAN."""
        output_text = """
ITERATION_PLAN:
Executor Count: not-a-number
Work Items:
- invalid format here

ITERATION_INTENT: Try to work
"""

        plan = parse_iteration_plan(output_text)

        # Should return None on parse errors
        assert plan is None


class TestPlannerSystemPromptIncludesIterationPlan:
    """Test that planner system prompt instructs output of ITERATION_PLAN."""

    def test_system_prompt_mentions_iteration_plan(self):
        """Test that PLANNER_SYSTEM_PROMPT includes instructions for ITERATION_PLAN."""
        from ralph2.agents.planner import PLANNER_SYSTEM_PROMPT

        # Verify prompt mentions ITERATION_PLAN
        assert "ITERATION_PLAN" in PLANNER_SYSTEM_PROMPT

        # Verify prompt mentions executor count
        assert "executor" in PLANNER_SYSTEM_PROMPT.lower()

        # Verify prompt explains format
        assert "work item" in PLANNER_SYSTEM_PROMPT.lower()
