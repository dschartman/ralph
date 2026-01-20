"""Tests for DECIDE data structures and routing logic."""

import pytest
from pydantic import ValidationError

from soda.decide import (
    Decision,
    DecisionOutcome,
    OrientOutput,
    SpecSatisfied,
    decide,
)


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


class TestSpecSatisfied:
    """Tests for SpecSatisfied enum."""

    def test_true_value(self):
        """TRUE value exists."""
        assert SpecSatisfied.TRUE.value == "true"

    def test_false_value(self):
        """FALSE value exists."""
        assert SpecSatisfied.FALSE.value == "false"

    def test_unverifiable_value(self):
        """UNVERIFIABLE value exists."""
        assert SpecSatisfied.UNVERIFIABLE.value == "unverifiable"


class TestOrientOutput:
    """Tests for OrientOutput model (minimal for DECIDE)."""

    def test_orient_output_spec_satisfied_true(self):
        """OrientOutput with spec_satisfied=true."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            summary="All criteria met",
        )
        assert output.spec_satisfied == SpecSatisfied.TRUE
        assert output.actionable_work_exists is False

    def test_orient_output_spec_satisfied_false(self):
        """OrientOutput with spec_satisfied=false."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            gaps=["Missing tests"],
        )
        assert output.spec_satisfied == SpecSatisfied.FALSE
        assert output.actionable_work_exists is True
        assert "Missing tests" in output.gaps

    def test_orient_output_spec_unverifiable(self):
        """OrientOutput with spec_satisfied=unverifiable."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.UNVERIFIABLE,
            actionable_work_exists=False,
            gaps=["Requires external API"],
        )
        assert output.spec_satisfied == SpecSatisfied.UNVERIFIABLE
        assert output.actionable_work_exists is False

    def test_orient_output_from_string(self):
        """OrientOutput can be created with string spec_satisfied."""
        output = OrientOutput(
            spec_satisfied="true",
            actionable_work_exists=False,
            summary="Done",
        )
        assert output.spec_satisfied == SpecSatisfied.TRUE

    def test_orient_output_json_serializable(self):
        """OrientOutput can be serialized to JSON."""
        output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            gaps=["Gap 1"],
        )
        data = output.model_dump(mode="json")
        assert data["spec_satisfied"] == "false"
        assert data["actionable_work_exists"] is True


class TestDecideFunction:
    """Tests for decide() routing logic.

    Routing rules:
    - spec_satisfied=true → DONE
    - spec_satisfied=false AND actionable_work_exists=true → CONTINUE
    - spec_satisfied=false AND actionable_work_exists=false → STUCK
    - spec_satisfied=unverifiable AND actionable_work_exists=false → STUCK
    - spec_satisfied=unverifiable AND actionable_work_exists=true → CONTINUE
    """

    def test_decide_spec_satisfied_true_returns_done(self):
        """WHEN spec_satisfied=true, THEN DECIDE returns DONE."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            summary="All acceptance criteria verified",
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.DONE
        assert decision.summary == "All acceptance criteria verified"

    def test_decide_spec_satisfied_true_ignores_actionable_work(self):
        """DONE takes precedence even if actionable_work_exists=true."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=True,
            summary="Complete despite remaining work",
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.DONE

    def test_decide_spec_false_actionable_true_returns_continue(self):
        """WHEN spec_satisfied=false AND actionable_work_exists=true, THEN CONTINUE."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            gaps=["Missing implementation"],
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.CONTINUE

    def test_decide_spec_false_actionable_false_returns_stuck(self):
        """WHEN spec_satisfied=false AND actionable_work_exists=false, THEN STUCK."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            gaps=["All tasks blocked"],
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.STUCK
        assert decision.reason is not None
        assert "blocked" in decision.reason.lower() or "All tasks blocked" in decision.reason

    def test_decide_spec_unverifiable_actionable_false_returns_stuck(self):
        """WHEN spec_satisfied=unverifiable AND actionable_work_exists=false, THEN STUCK."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.UNVERIFIABLE,
            actionable_work_exists=False,
            gaps=["Requires external API key"],
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.STUCK
        assert decision.reason is not None

    def test_decide_spec_unverifiable_actionable_true_returns_continue(self):
        """WHEN spec_satisfied=unverifiable AND actionable_work_exists=true, THEN CONTINUE."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.UNVERIFIABLE,
            actionable_work_exists=True,
            gaps=["Requires external verification"],
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.CONTINUE

    def test_decide_stuck_includes_reason_from_gaps(self):
        """WHEN STUCK, reason comes from ORIENT gaps."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=False,
            gaps=["Gap A: Missing dependency", "Gap B: Blocked by external"],
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.STUCK
        # Reason should include gap information
        assert "Gap A" in decision.reason or "Missing dependency" in decision.reason

    def test_decide_done_includes_summary(self):
        """WHEN DONE, summary comes from ORIENT output."""
        summary_text = "All 5 acceptance criteria verified with passing tests"
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.TRUE,
            actionable_work_exists=False,
            summary=summary_text,
        )
        decision = decide(orient_output)
        assert decision.outcome == DecisionOutcome.DONE
        assert decision.summary == summary_text

    def test_decide_is_deterministic(self):
        """Same input always produces same output (deterministic)."""
        orient_output = OrientOutput(
            spec_satisfied=SpecSatisfied.FALSE,
            actionable_work_exists=True,
            gaps=["Test gap"],
        )
        decision1 = decide(orient_output)
        decision2 = decide(orient_output)
        decision3 = decide(orient_output)
        assert decision1.outcome == decision2.outcome == decision3.outcome
        assert decision1.reason == decision2.reason == decision3.reason
        assert decision1.summary == decision2.summary == decision3.summary
