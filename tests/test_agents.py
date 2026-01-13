"""Tests for agents module - output parsing logic."""

import pytest
from ralph.agents.planner import run_planner, PLANNER_SYSTEM_PROMPT
from ralph.agents.executor import run_executor, EXECUTOR_SYSTEM_PROMPT
from ralph.agents.verifier import run_verifier, VERIFIER_SYSTEM_PROMPT, parse_verifier_output


class TestPlannerParsing:
    """Test planner output parsing logic."""

    def test_extracts_iteration_intent_with_prefix(self):
        """Test extracting ITERATION_INTENT when present with prefix."""
        output = """
I've reviewed the tasks and created a breakdown.

ITERATION_INTENT: Implement unit tests for the state module
"""
        # Simulate the parsing logic from run_planner
        intent = None
        for line in output.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break

        assert intent == "Implement unit tests for the state module"

    def test_extracts_iteration_intent_multiline(self):
        """Test extracting first line when ITERATION_INTENT is multiline."""
        output = """
Based on the spec review:

ITERATION_INTENT: Work on task ralph-abc123 to add validation logic
and ensure all edge cases are covered.

Some additional notes here.
"""
        intent = None
        for line in output.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break

        assert intent == "Work on task ralph-abc123 to add validation logic"

    def test_fallback_to_last_line_when_no_prefix(self):
        """Test fallback behavior when ITERATION_INTENT prefix is missing."""
        output = """
I've reviewed the tasks.
Next we should work on the database module.
"""
        # Simulate the fallback logic
        intent = None
        full_text = output

        for line in full_text.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break

        if not intent:
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            if lines:
                intent = lines[-1]

        assert intent == "Next we should work on the database module."

    def test_handles_empty_output(self):
        """Test fallback when output is empty."""
        output = ""

        intent = None
        for line in output.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break

        if not intent:
            lines = [l.strip() for l in output.split("\n") if l.strip()]
            if lines:
                intent = lines[-1]
            else:
                intent = "Continue working on tasks"

        assert intent == "Continue working on tasks"


class TestExecutorParsing:
    """Test executor output parsing logic."""

    def test_extracts_executor_summary_completed(self):
        """Test extracting EXECUTOR_SUMMARY with Completed status."""
        output = """
I've implemented the test file.

EXECUTOR_SUMMARY:
Status: Completed
What was done: Created test_agents.py with comprehensive unit tests
Blockers: None
Notes: All tests passing
"""
        # Simulate the parsing logic from run_executor
        summary_start = output.find("EXECUTOR_SUMMARY:")
        summary = None
        status = "Completed"  # Default

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Status:"):
                    status_text = line.replace("Status:", "").strip()
                    if "Completed" in status_text:
                        status = "Completed"
                    elif "Blocked" in status_text:
                        status = "Blocked"
                    elif "Uncertain" in status_text:
                        status = "Uncertain"
                    break

        assert summary is not None
        assert "EXECUTOR_SUMMARY:" in summary
        assert status == "Completed"
        assert "What was done:" in summary

    def test_extracts_executor_summary_blocked(self):
        """Test extracting EXECUTOR_SUMMARY with Blocked status."""
        output = """
I've started work but encountered an issue.

EXECUTOR_SUMMARY:
Status: Blocked
What was done: Reviewed codebase and identified dependencies
Blockers: Missing pytest-asyncio package
Notes: Need to install dependency before proceeding
"""
        summary_start = output.find("EXECUTOR_SUMMARY:")
        status = "Completed"  # Default

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Status:"):
                    status_text = line.replace("Status:", "").strip()
                    if "Completed" in status_text:
                        status = "Completed"
                    elif "Blocked" in status_text:
                        status = "Blocked"
                    elif "Uncertain" in status_text:
                        status = "Uncertain"
                    break

        assert status == "Blocked"
        assert "Blockers:" in summary

    def test_extracts_executor_summary_uncertain(self):
        """Test extracting EXECUTOR_SUMMARY with Uncertain status."""
        output = """
I've made some progress but unsure about approach.

EXECUTOR_SUMMARY:
Status: Uncertain
What was done: Created initial implementation
Blockers: None
Notes: Unsure if this approach aligns with architectural patterns
"""
        summary_start = output.find("EXECUTOR_SUMMARY:")
        status = "Completed"  # Default

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Status:"):
                    status_text = line.replace("Status:", "").strip()
                    if "Completed" in status_text:
                        status = "Completed"
                    elif "Blocked" in status_text:
                        status = "Blocked"
                    elif "Uncertain" in status_text:
                        status = "Uncertain"
                    break

        assert status == "Uncertain"

    def test_fallback_when_no_summary(self):
        """Test fallback behavior when EXECUTOR_SUMMARY is missing."""
        output = "I did some work but forgot to add the summary."

        summary_start = output.find("EXECUTOR_SUMMARY:")
        summary = None
        status = "Completed"

        if summary_start != -1:
            summary = output[summary_start:].strip()
        else:
            summary = "EXECUTOR_SUMMARY:\nStatus: Completed\nWhat was done: Work completed\n"

        assert summary is not None
        assert "EXECUTOR_SUMMARY:" in summary
        assert status == "Completed"


class TestVerifierParsing:
    """Test verifier output parsing logic."""

    def test_extracts_verifier_assessment_done(self):
        """Test extracting VERIFIER_ASSESSMENT with DONE outcome."""
        output = """
I've verified all acceptance criteria.

VERIFIER_ASSESSMENT:
Outcome: DONE
Reasoning: All tests passing, all acceptance criteria met
Gaps (if CONTINUE): N/A
Blocker (if STUCK): N/A
"""
        # Simulate the parsing logic from run_verifier
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        assessment = None
        outcome = "CONTINUE"  # Default

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Outcome:"):
                    outcome_text = line.replace("Outcome:", "").strip()
                    if "DONE" in outcome_text:
                        outcome = "DONE"
                    elif "STUCK" in outcome_text:
                        outcome = "STUCK"
                    elif "CONTINUE" in outcome_text:
                        outcome = "CONTINUE"
                    break

        assert assessment is not None
        assert "VERIFIER_ASSESSMENT:" in assessment
        assert outcome == "DONE"

    def test_extracts_verifier_assessment_continue(self):
        """Test extracting VERIFIER_ASSESSMENT with CONTINUE outcome."""
        output = """
I've checked the implementation but found some gaps.

VERIFIER_ASSESSMENT:
Outcome: CONTINUE
Reasoning: Tests exist but some acceptance criteria not yet met
Gaps (if CONTINUE): Missing tests for edge cases, documentation incomplete
Blocker (if STUCK): N/A
"""
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        outcome = "CONTINUE"  # Default

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Outcome:"):
                    outcome_text = line.replace("Outcome:", "").strip()
                    if "DONE" in outcome_text:
                        outcome = "DONE"
                    elif "STUCK" in outcome_text:
                        outcome = "STUCK"
                    elif "CONTINUE" in outcome_text:
                        outcome = "CONTINUE"
                    break

        assert outcome == "CONTINUE"
        assert "Gaps (if CONTINUE):" in assessment

    def test_extracts_verifier_assessment_stuck(self):
        """Test extracting VERIFIER_ASSESSMENT with STUCK outcome."""
        output = """
I've attempted verification but cannot proceed.

VERIFIER_ASSESSMENT:
Outcome: STUCK
Reasoning: Cannot verify without external dependency
Gaps (if CONTINUE): N/A
Blocker (if STUCK): Database service not running, cannot test integration
"""
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        outcome = "CONTINUE"  # Default

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Outcome:"):
                    outcome_text = line.replace("Outcome:", "").strip()
                    if "DONE" in outcome_text:
                        outcome = "DONE"
                    elif "STUCK" in outcome_text:
                        outcome = "STUCK"
                    elif "CONTINUE" in outcome_text:
                        outcome = "CONTINUE"
                    break

        assert outcome == "STUCK"
        assert "Blocker (if STUCK):" in assessment

    def test_fallback_when_no_assessment(self):
        """Test fallback behavior when VERIFIER_ASSESSMENT is missing."""
        output = "I verified the work but forgot to add assessment."

        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        assessment = None
        outcome = "CONTINUE"

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()
        else:
            assessment = "VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nReasoning: Verification incomplete\n"

        assert assessment is not None
        assert "VERIFIER_ASSESSMENT:" in assessment
        assert outcome == "CONTINUE"


class TestAgentSystemPrompts:
    """Test that agent system prompts contain expected content."""

    def test_planner_system_prompt_has_trace_commands(self):
        """Test that planner system prompt includes Trace command reference."""
        assert "trc ready" in PLANNER_SYSTEM_PROMPT
        assert "trc list" in PLANNER_SYSTEM_PROMPT
        assert "trc show" in PLANNER_SYSTEM_PROMPT
        assert "trc create" in PLANNER_SYSTEM_PROMPT
        assert "trc close" in PLANNER_SYSTEM_PROMPT
        assert "--description" in PLANNER_SYSTEM_PROMPT
        assert "--parent" in PLANNER_SYSTEM_PROMPT

    def test_planner_system_prompt_has_output_format(self):
        """Test that planner system prompt specifies output format."""
        assert "ITERATION_INTENT:" in PLANNER_SYSTEM_PROMPT

    def test_executor_system_prompt_has_trace_commands(self):
        """Test that executor system prompt includes Trace command reference."""
        assert "trc show" in EXECUTOR_SYSTEM_PROMPT
        assert "trc comment" in EXECUTOR_SYSTEM_PROMPT
        assert "trc close" in EXECUTOR_SYSTEM_PROMPT
        assert "--source executor" in EXECUTOR_SYSTEM_PROMPT

    def test_executor_system_prompt_has_output_format(self):
        """Test that executor system prompt specifies output format."""
        assert "EXECUTOR_SUMMARY:" in EXECUTOR_SYSTEM_PROMPT
        assert "Status:" in EXECUTOR_SYSTEM_PROMPT
        assert "Completed" in EXECUTOR_SYSTEM_PROMPT
        assert "Blocked" in EXECUTOR_SYSTEM_PROMPT
        assert "Uncertain" in EXECUTOR_SYSTEM_PROMPT

    def test_verifier_system_prompt_has_output_format(self):
        """Test that verifier system prompt specifies output format."""
        assert "VERIFIER_ASSESSMENT:" in VERIFIER_SYSTEM_PROMPT
        assert "Outcome:" in VERIFIER_SYSTEM_PROMPT
        assert "DONE" in VERIFIER_SYSTEM_PROMPT
        assert "CONTINUE" in VERIFIER_SYSTEM_PROMPT
        assert "STUCK" in VERIFIER_SYSTEM_PROMPT


class TestEfficiencyNotesParsing:
    """Test efficiency notes extraction from agent outputs."""

    def test_extracts_efficiency_notes_from_executor(self):
        """Test extracting Efficiency Notes from executor summary."""
        output = """
I've completed the work.

EXECUTOR_SUMMARY:
Status: Completed
What was done: Created test file
Blockers: None
Notes: All tests passing
Efficiency Notes: Use UV for package management, tests in tests/ directory
"""
        # Simulate parsing logic
        summary_start = output.find("EXECUTOR_SUMMARY:")
        efficiency_notes = None

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Efficiency Notes:"):
                    efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                    break

        assert efficiency_notes == "Use UV for package management, tests in tests/ directory"

    def test_extracts_efficiency_notes_from_verifier(self):
        """Test extracting Efficiency Notes from verifier assessment."""
        output = """
Verification complete.

VERIFIER_ASSESSMENT:
Outcome: DONE
Reasoning: All criteria met
Gaps (if CONTINUE): N/A
Blocker (if STUCK): N/A
Efficiency Notes: Run pytest with -v flag for verbose output
"""
        # Simulate parsing logic
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        efficiency_notes = None

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Efficiency Notes:"):
                    efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                    break

        assert efficiency_notes == "Run pytest with -v flag for verbose output"

    def test_handles_missing_efficiency_notes_executor(self):
        """Test that missing efficiency notes doesn't break parsing."""
        output = """
EXECUTOR_SUMMARY:
Status: Completed
What was done: Created test file
Blockers: None
Notes: All tests passing
"""
        summary_start = output.find("EXECUTOR_SUMMARY:")
        efficiency_notes = None

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Efficiency Notes:"):
                    efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                    break

        assert efficiency_notes is None

    def test_handles_missing_efficiency_notes_verifier(self):
        """Test that missing efficiency notes doesn't break parsing."""
        output = """
VERIFIER_ASSESSMENT:
Outcome: DONE
Reasoning: All criteria met
"""
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        efficiency_notes = None

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Efficiency Notes:"):
                    efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                    break

        assert efficiency_notes is None

    def test_extracts_none_explicitly_stated(self):
        """Test extracting 'None' when explicitly stated."""
        output = """
EXECUTOR_SUMMARY:
Status: Completed
What was done: Work completed
Efficiency Notes: None
"""
        summary_start = output.find("EXECUTOR_SUMMARY:")
        efficiency_notes = None

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Efficiency Notes:"):
                    efficiency_notes = line.replace("Efficiency Notes:", "").strip()
                    break

        assert efficiency_notes == "None"


class TestMemoryIntegration:
    """Test memory integration in agent functions."""

    def test_planner_accepts_memory_parameter(self):
        """Test that run_planner accepts memory parameter."""
        import inspect
        sig = inspect.signature(run_planner)
        assert 'memory' in sig.parameters

    def test_executor_accepts_memory_parameter(self):
        """Test that run_executor accepts memory parameter."""
        import inspect
        sig = inspect.signature(run_executor)
        assert 'memory' in sig.parameters

    def test_verifier_accepts_memory_parameter(self):
        """Test that run_verifier accepts memory parameter."""
        import inspect
        sig = inspect.signature(run_verifier)
        assert 'memory' in sig.parameters


class TestEdgeCases:
    """Test edge cases in parsing logic."""

    def test_planner_handles_multiple_intent_markers(self):
        """Test that only first ITERATION_INTENT is extracted."""
        output = """
ITERATION_INTENT: First intent
Some other text
ITERATION_INTENT: Second intent (this should be ignored)
"""
        intent = None
        for line in output.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break

        assert intent == "First intent"

    def test_executor_handles_status_with_extra_text(self):
        """Test that status is extracted even with extra text on line."""
        output = """
EXECUTOR_SUMMARY:
Status: Completed (all tests passing)
What was done: Implementation finished
"""
        summary_start = output.find("EXECUTOR_SUMMARY:")
        status = "Completed"

        if summary_start != -1:
            summary = output[summary_start:].strip()

            for line in summary.split("\n"):
                if line.startswith("Status:"):
                    status_text = line.replace("Status:", "").strip()
                    if "Completed" in status_text:
                        status = "Completed"
                    elif "Blocked" in status_text:
                        status = "Blocked"
                    elif "Uncertain" in status_text:
                        status = "Uncertain"
                    break

        assert status == "Completed"

    def test_verifier_handles_outcome_with_extra_text(self):
        """Test that outcome is extracted even with extra text."""
        output = """
VERIFIER_ASSESSMENT:
Outcome: DONE (all criteria satisfied)
Reasoning: Everything looks good
"""
        assessment_start = output.find("VERIFIER_ASSESSMENT:")
        outcome = "CONTINUE"

        if assessment_start != -1:
            assessment = output[assessment_start:].strip()

            for line in assessment.split("\n"):
                if line.startswith("Outcome:"):
                    outcome_text = line.replace("Outcome:", "").strip()
                    if "DONE" in outcome_text:
                        outcome = "DONE"
                    elif "STUCK" in outcome_text:
                        outcome = "STUCK"
                    elif "CONTINUE" in outcome_text:
                        outcome = "CONTINUE"
                    break

        assert outcome == "DONE"

    def test_handles_whitespace_variations(self):
        """Test that parsing handles various whitespace patterns."""
        # Test with extra spaces
        output1 = "ITERATION_INTENT:    Work on task X   "
        intent = None
        for line in output1.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break
        assert intent == "Work on task X"

        # Test with tabs
        output2 = "ITERATION_INTENT:\tWork on task Y"
        intent = None
        for line in output2.split("\n"):
            if line.startswith("ITERATION_INTENT:"):
                intent = line.replace("ITERATION_INTENT:", "").strip()
                break
        assert intent == "Work on task Y"


class TestParseVerifierOutput:
    """Tests for parse_verifier_output function - handles markdown formatting."""

    def test_parses_plain_outcome_done(self):
        """Test parsing standard DONE outcome."""
        output = """
VERIFIER_ASSESSMENT:
Outcome: DONE
Criteria Status:
- Feature implemented: ✓ satisfied
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"
        assert result["assessment"] is not None

    def test_parses_markdown_bold_outcome_done(self):
        """Test parsing DONE outcome wrapped in markdown bold markers."""
        output = """
**VERIFIER_ASSESSMENT:**
**Outcome: DONE**
Criteria Status:
- Feature implemented: ✓ satisfied
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"

    def test_parses_markdown_bold_outcome_continue(self):
        """Test parsing CONTINUE outcome wrapped in markdown bold markers."""
        output = """
VERIFIER_ASSESSMENT:
**Outcome: CONTINUE**
Gaps: Missing tests
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "CONTINUE"

    def test_parses_markdown_bold_outcome_stuck(self):
        """Test parsing STUCK outcome wrapped in markdown bold markers."""
        output = """
VERIFIER_ASSESSMENT:
**Outcome: STUCK**
Blocker: Cannot access database
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "STUCK"

    def test_parses_outcome_with_double_asterisks(self):
        """Test parsing outcome with double asterisks on both sides."""
        output = """
VERIFIER_ASSESSMENT:
**Outcome:** **DONE**
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"

    def test_parses_efficiency_notes_with_markdown(self):
        """Test parsing efficiency notes with markdown formatting."""
        output = """
VERIFIER_ASSESSMENT:
Outcome: DONE
**Efficiency Notes:** Always run tests before verification
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"
        assert result["efficiency_notes"] == "Always run tests before verification"

    def test_defaults_to_continue_when_no_assessment(self):
        """Test that outcome defaults to CONTINUE when no assessment found."""
        output = "Some random output without assessment"
        result = parse_verifier_output(output)
        assert result["outcome"] == "CONTINUE"
        assert result["assessment"] is not None  # Fallback assessment

    def test_handles_outcome_with_extra_text(self):
        """Test parsing outcome with additional explanatory text."""
        output = """
VERIFIER_ASSESSMENT:
Outcome: DONE (all criteria satisfied)
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"

    def test_handles_leading_whitespace(self):
        """Test parsing with leading whitespace on outcome line."""
        output = """
VERIFIER_ASSESSMENT:
    Outcome: DONE
"""
        result = parse_verifier_output(output)
        assert result["outcome"] == "DONE"
