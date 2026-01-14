"""Main iteration loop orchestration for Ralph."""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid
import json

from .state.db import RalphDB
from .state.models import Run, Iteration, AgentOutput, HumanInput
from .agents.planner import run_planner
from .agents.executor import run_executor
from .agents.verifier import run_verifier
from .project import ProjectContext, read_memory


class RalphRunner:
    """Orchestrates the Ralph multi-agent iteration loop."""

    def __init__(self, spec_path: str, project_context: ProjectContext):
        """
        Initialize Ralph runner.

        Args:
            spec_path: Path to the Ralphfile (spec)
            project_context: ProjectContext with paths for state storage
        """
        self.spec_path = spec_path
        self.project_context = project_context
        self.db = RalphDB(str(project_context.db_path))

        # Load spec content
        with open(spec_path, 'r') as f:
            self.spec_content = f.read()

        # Output directory is managed by ProjectContext
        self.output_dir = project_context.outputs_dir

    def _save_agent_messages(self, iteration_id: int, agent_type: str, messages: list) -> str:
        """
        Save agent messages to a JSONL file.

        Args:
            iteration_id: Iteration ID
            agent_type: Type of agent (planner, executor, verifier)
            messages: List of message dictionaries from the agent

        Returns:
            Path to the saved output file
        """
        output_path = self.output_dir / f"iteration_{iteration_id}_{agent_type}.jsonl"

        # Save as JSONL (each message is one line)
        with open(output_path, 'w') as f:
            for msg in messages:
                json.dump(msg, f)
                f.write('\n')

        return str(output_path)

    async def run(self, max_iterations: int = 50) -> str:
        """
        Run Ralph until completion or max iterations.

        Args:
            max_iterations: Maximum number of iterations to run

        Returns:
            Final status: "completed", "stuck", or "max_iterations"
        """
        # Create a new run
        run_id = f"ralph-{uuid.uuid4().hex[:8]}"
        run = Run(
            id=run_id,
            spec_path=self.spec_path,
            spec_content=self.spec_content,
            status="running",
            config={"max_iterations": max_iterations},
            started_at=datetime.now()
        )
        self.db.create_run(run)

        print(f"🚀 Starting Ralph run: {run_id}")
        print(f"📋 Spec: {self.spec_path}")
        print()

        # Read project memory
        memory = read_memory(self.project_context.project_id)

        iteration_number = 0
        last_executor_summary = None
        last_verifier_assessment = None

        while iteration_number < max_iterations:
            iteration_number += 1
            print(f"\n{'='*60}")
            print(f"Iteration {iteration_number}")
            print(f"{'='*60}\n")

            # Check for human input
            human_inputs = self.db.get_unconsumed_inputs(run_id)
            human_input_messages = []

            for human_input in human_inputs:
                if human_input.input_type == "comment":
                    human_input_messages.append(human_input.content)
                    self.db.mark_input_consumed(human_input.id, datetime.now())
                elif human_input.input_type == "pause":
                    print("⏸️  Pausing run (human requested)")
                    self.db.update_run_status(run_id, "paused", datetime.now())
                    return "paused"
                elif human_input.input_type == "abort":
                    print("🛑 Aborting run (human requested)")
                    self.db.update_run_status(run_id, "aborted", datetime.now())
                    return "aborted"

            # Create iteration record
            iteration = Iteration(
                id=None,
                run_id=run_id,
                number=iteration_number,
                intent="",  # Will be updated by planner
                outcome="",  # Will be updated by verifier
                started_at=datetime.now()
            )
            iteration = self.db.create_iteration(iteration)
            iteration_id = iteration.id

            # ===== PLANNER =====
            print("🧠 Running Planner...")
            try:
                planner_result = await run_planner(
                    spec_content=self.spec_content,
                    last_executor_summary=last_executor_summary,
                    last_verifier_assessment=last_verifier_assessment,
                    human_inputs=human_input_messages if human_input_messages else None,
                    memory=memory,
                    project_id=self.project_context.project_id
                )
            except Exception as e:
                print(f"   ❌ Planner error: {e}")
                self.db.update_iteration(iteration_id, "STUCK", datetime.now())
                self.db.update_run_status(run_id, "stuck", datetime.now())
                self._write_summary(run_id)
                return "stuck"

            intent = planner_result["intent"]
            print(f"   Intent: {intent}\n")

            # Update iteration with intent
            self.db.conn.execute(
                "UPDATE iterations SET intent = ? WHERE id = ?",
                (intent, iteration_id)
            )
            self.db.conn.commit()

            # Save planner output
            planner_output_path = self._save_agent_messages(
                iteration_id, "planner", planner_result["messages"]
            )
            self.db.create_agent_output(AgentOutput(
                id=None,
                iteration_id=iteration_id,
                agent_type="planner",
                raw_output_path=planner_output_path,
                summary=intent
            ))

            # Re-read memory in case planner updated it
            memory = read_memory(self.project_context.project_id)

            # ===== EXECUTOR =====
            print("⚙️  Running Executor...")
            try:
                executor_result = await run_executor(
                    iteration_intent=intent,
                    spec_content=self.spec_content,
                    memory=memory
                )
            except Exception as e:
                print(f"   ❌ Executor error: {e}")
                # Save what we have and continue - let verifier assess the situation
                executor_result = {
                    "status": "Blocked",
                    "summary": f"EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Agent crashed with error\nBlockers: {e}\nNotes: Executor agent encountered an error and could not complete",
                    "full_output": str(e),
                    "messages": []
                }

            status = executor_result["status"]
            summary = executor_result["summary"]
            print(f"   Status: {status}")
            print(f"   Summary: {summary[:200]}...\n" if len(summary) > 200 else f"   Summary: {summary}\n")

            # Save executor output
            executor_output_path = self._save_agent_messages(
                iteration_id, "executor", executor_result["messages"]
            )
            self.db.create_agent_output(AgentOutput(
                id=None,
                iteration_id=iteration_id,
                agent_type="executor",
                raw_output_path=executor_output_path,
                summary=summary
            ))

            last_executor_summary = summary

            # ===== VERIFIER =====
            print("🔍 Running Verifier...")
            try:
                verifier_result = await run_verifier(
                    spec_content=self.spec_content,
                    memory=memory
                )
            except Exception as e:
                print(f"   ❌ Verifier error: {e}")
                # Default to CONTINUE so the loop can retry
                verifier_result = {
                    "outcome": "CONTINUE",
                    "assessment": f"VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nReasoning: Verifier agent crashed with error: {e}\nGaps: Unable to verify - agent error",
                    "full_output": str(e),
                    "messages": []
                }

            outcome = verifier_result["outcome"]
            assessment = verifier_result["assessment"]
            print(f"   Outcome: {outcome}")
            print(f"   Assessment: {assessment[:200]}...\n" if len(assessment) > 200 else f"   Assessment: {assessment}\n")

            # Save verifier output
            verifier_output_path = self._save_agent_messages(
                iteration_id, "verifier", verifier_result["messages"]
            )
            self.db.create_agent_output(AgentOutput(
                id=None,
                iteration_id=iteration_id,
                agent_type="verifier",
                raw_output_path=verifier_output_path,
                summary=assessment
            ))

            last_verifier_assessment = assessment

            # Update iteration with outcome
            self.db.update_iteration(iteration_id, outcome, datetime.now())

            # ===== CHECK OUTCOME =====
            if outcome == "DONE":
                print("\n✅ Spec satisfied! Ralph is done.")
                self.db.update_run_status(run_id, "completed", datetime.now())
                self._write_summary(run_id)
                return "completed"

            elif outcome == "STUCK":
                print("\n⚠️  Ralph is stuck and cannot make progress.")
                self.db.update_run_status(run_id, "stuck", datetime.now())
                self._write_summary(run_id)
                return "stuck"

            # outcome == "CONTINUE" - loop continues

        # Max iterations reached
        print(f"\n⏱️  Max iterations ({max_iterations}) reached.")
        self.db.update_run_status(run_id, "max_iterations", datetime.now())
        self._write_summary(run_id)
        return "max_iterations"

    def _write_summary(self, run_id: str):
        """Write a summary of the run to a file."""
        run = self.db.get_run(run_id)
        if not run:
            return

        iterations = self.db.list_iterations(run_id)

        summary_path = self.project_context.summaries_dir / f"summary_{run_id}.md"

        with open(summary_path, 'w') as f:
            f.write(f"# Ralph Run Summary\n\n")
            f.write(f"**Run ID:** {run.id}\n")
            f.write(f"**Status:** {run.status}\n")
            f.write(f"**Started:** {run.started_at.isoformat()}\n")
            if run.ended_at:
                f.write(f"**Ended:** {run.ended_at.isoformat()}\n")
                duration = run.ended_at - run.started_at
                f.write(f"**Duration:** {duration}\n")
            f.write(f"\n**Spec:** {run.spec_path}\n\n")

            f.write(f"## Iterations ({len(iterations)})\n\n")

            for iteration in iterations:
                f.write(f"### Iteration {iteration.number}\n\n")
                f.write(f"**Intent:** {iteration.intent}\n\n")
                f.write(f"**Outcome:** {iteration.outcome}\n\n")

                # Get agent outputs
                agent_outputs = self.db.get_agent_outputs(iteration.id)
                for output in agent_outputs:
                    f.write(f"**{output.agent_type.capitalize()} Summary:**\n")
                    f.write(f"```\n{output.summary}\n```\n\n")

                f.write("---\n\n")

        print(f"\n📄 Summary written to: {summary_path}")

    def close(self):
        """Close database connection."""
        self.db.close()


async def run_ralph(spec_path: str = "Ralphfile", max_iterations: int = 50) -> str:
    """
    Run Ralph with the given spec.

    This is a convenience function that creates a ProjectContext automatically.
    For more control, use RalphRunner directly with a ProjectContext.

    Args:
        spec_path: Path to the Ralphfile
        max_iterations: Maximum number of iterations

    Returns:
        Final status
    """
    ctx = ProjectContext()
    runner = RalphRunner(spec_path, ctx)
    try:
        return await runner.run(max_iterations)
    finally:
        runner.close()


def main():
    """Main entry point for testing."""
    import sys

    spec_path = sys.argv[1] if len(sys.argv) > 1 else "Ralphfile"

    status = asyncio.run(run_ralph(spec_path))
    print(f"\nFinal status: {status}")


if __name__ == "__main__":
    main()
