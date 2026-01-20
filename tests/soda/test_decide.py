"""Tests for DECIDE data structures (Decision)."""

import pytest
from pydantic import ValidationError

from soda.decide import Decision, DecisionOutcome


class TestDecisionOutcome:
    """Tests for DecisionOutcome enum."""

    def test_done_outcome_exists(self):
        """DONE outcome is available."""
        assert DecisionOutcome.DONE == "DONE"

    def test_stuck_outcome_exists(self):
        """STUCK outcome is available."""
        assert DecisionOutcome.STUCK == "STUCK"

    def test_continue_outcome_exists(self):
        """CONTINUE outcome is available."""
        assert DecisionOutcome.CONTINUE == "CONTINUE"


class TestDecision:
    """Tests for Decision model."""

    def test_decision_done_with_summary(self):
        """Decision DONE requires summary."""
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="All acceptance criteria met",
        )
        assert decision.outcome == DecisionOutcome.DONE
        assert decision.summary == "All acceptance criteria met"
        assert decision.reason is None

    def test_decision_done_without_summary_raises(self):
        """Decision DONE without summary raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Decision(
                outcome=DecisionOutcome.DONE,
            )
        # Check that the error mentions summary being required
        assert "summary" in str(exc_info.value).lower()

    def test_decision_stuck_with_reason(self):
        """Decision STUCK requires reason."""
        decision = Decision(
            outcome=DecisionOutcome.STUCK,
            reason="No actionable work exists",
        )
        assert decision.outcome == DecisionOutcome.STUCK
        assert decision.reason == "No actionable work exists"
        assert decision.summary is None

    def test_decision_stuck_without_reason_raises(self):
        """Decision STUCK without reason raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Decision(
                outcome=DecisionOutcome.STUCK,
            )
        # Check that the error mentions reason being required
        assert "reason" in str(exc_info.value).lower()

    def test_decision_continue_no_constraints(self):
        """Decision CONTINUE has no extra requirements."""
        decision = Decision(
            outcome=DecisionOutcome.CONTINUE,
        )
        assert decision.outcome == DecisionOutcome.CONTINUE
        assert decision.reason is None
        assert decision.summary is None

    def test_decision_continue_with_optional_fields(self):
        """Decision CONTINUE can have optional fields."""
        decision = Decision(
            outcome=DecisionOutcome.CONTINUE,
            reason="Work in progress",
            summary="Making good progress",
        )
        assert decision.outcome == DecisionOutcome.CONTINUE
        assert decision.reason == "Work in progress"
        assert decision.summary == "Making good progress"

    def test_decision_json_serializable(self):
        """Decision can be serialized to JSON."""
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="All done",
        )
        data = decision.model_dump(mode="json")
        assert data["outcome"] == "DONE"
        assert data["summary"] == "All done"
        assert data["reason"] is None

    def test_decision_from_string_outcome(self):
        """Decision can be created with string outcome."""
        decision = Decision(
            outcome="STUCK",
            reason="No work available",
        )
        assert decision.outcome == DecisionOutcome.STUCK
        assert decision.reason == "No work available"

    def test_decision_invalid_outcome_raises(self):
        """Decision with invalid outcome raises validation error."""
        with pytest.raises(ValidationError):
            Decision(
                outcome="INVALID",
            )

    def test_decision_done_with_reason_allowed(self):
        """Decision DONE can optionally have reason."""
        decision = Decision(
            outcome=DecisionOutcome.DONE,
            summary="Complete",
            reason="All tests pass",
        )
        assert decision.outcome == DecisionOutcome.DONE
        assert decision.summary == "Complete"
        assert decision.reason == "All tests pass"

    def test_decision_stuck_with_summary_allowed(self):
        """Decision STUCK can optionally have summary."""
        decision = Decision(
            outcome=DecisionOutcome.STUCK,
            reason="Blocked",
            summary="Progress so far",
        )
        assert decision.outcome == DecisionOutcome.STUCK
        assert decision.reason == "Blocked"
        assert decision.summary == "Progress so far"
