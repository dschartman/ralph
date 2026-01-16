"""Main iteration loop orchestration for Ralph2."""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid
import json

from .state.db import Ralph2DB
from .state.models import Run, Iteration, AgentOutput, HumanInput
from .agents.planner import run_planner
from .agents.executor import run_executor
from .agents.verifier import run_verifier
from .agents.specialist import CodeReviewerSpecialist, run_specialist
from .project import ProjectContext, read_memory


class Ralph2Runner:
    """Orchestrates the Ralph2 multi-agent iteration loop."""

    def __init__(self, spec_path: str, project_context: ProjectContext, root_work_item_id: Optional[str] = None):
        """
        Initialize Ralph2 runner.

        Args:
            spec_path: Path to the Ralph2file (spec)
            project_context: ProjectContext with paths for state storage
            root_work_item_id: Optional root work item ID (spec milestone in Trace)
        """
        self.spec_path = spec_path
        self.project_context = project_context
        self.db = Ralph2DB(str(project_context.db_path))
        self.root_work_item_id = root_work_item_id

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

    def _cleanup_abandoned_branches(self):
        """Clean up abandoned ralph2/* feature branches from interrupted work."""
        try:
            import subprocess
            # Use project root as working directory
            cwd = self.project_context.project_root

            # Get list of ralph2/* branches
            result = subprocess.run(
                ["git", "branch", "--list", "ralph2/*"],
                capture_output=True,
                text=True,
                check=False,
                cwd=cwd
            )

            if result.returncode == 0 and result.stdout.strip():
                branches = [b.strip().replace('* ', '') for b in result.stdout.strip().split('\n')]
                for branch in branches:
                    if branch:
                        print(f"   🧹 Cleaning up abandoned branch: {branch}")
                        # Switch to main/master first if we're on a ralph2 branch
                        subprocess.run(
                            ["git", "checkout", "main"],
                            capture_output=True,
                            check=False,
                            cwd=cwd
                        )
                        subprocess.run(
                            ["git", "checkout", "master"],
                            capture_output=True,
                            check=False,
                            cwd=cwd
                        )
                        # Delete the branch
                        subprocess.run(
                            ["git", "branch", "-D", branch],
                            capture_output=True,
                            check=False,
                            cwd=cwd
                        )
        except Exception as e:
            print(f"   ⚠️  Warning: Could not clean up branches: {e}")

    async def run(self, max_iterations: int = 50) -> str:
        """
        Run Ralph2 until completion or max iterations.

        Args:
            max_iterations: Maximum number of iterations to run

        Returns:
            Final status: "completed", "stuck", or "max_iterations"
        """
        # Check if there's an interrupted run to resume
        existing_run = self.db.get_latest_run()

        if existing_run and existing_run.status == "running":
            # Resume interrupted run
            run_id = existing_run.id
            run = existing_run

            # Update max_iterations in config if different
            run.config["max_iterations"] = max_iterations

            print(f"♻️  Resuming interrupted Ralph2 run: {run_id}")
            print(f"📋 Spec: {self.spec_path}")

            # Clean up any abandoned feature branches
            print(f"🧹 Cleaning up abandoned work from interruption...")
            self._cleanup_abandoned_branches()
            print()

            # Get the last completed iteration number
            last_iteration = self.db.get_latest_iteration(run_id)
            iteration_number = last_iteration.number if last_iteration else 0

            print(f"   Resuming from iteration {iteration_number + 1}")
            print()

            # Get last agent outputs for context
            if last_iteration:
                agent_outputs = self.db.get_agent_outputs(last_iteration.id)
                last_executor_summary = None
                last_verifier_assessment = None
                last_specialist_feedback = None

                for output in agent_outputs:
                    if output.agent_type.startswith("executor"):
                        if last_executor_summary is None:
                            last_executor_summary = output.summary
                        else:
                            last_executor_summary += f"\n\n{output.summary}"
                    elif output.agent_type == "verifier":
                        last_verifier_assessment = output.summary
                    elif "specialist" in output.agent_type.lower() or "reviewer" in output.agent_type.lower():
                        if last_specialist_feedback is None:
                            last_specialist_feedback = output.summary
                        else:
                            last_specialist_feedback += f"\n\n{output.summary}"
            else:
                last_executor_summary = None
                last_verifier_assessment = None
                last_specialist_feedback = None
        else:
            # Create a new run
            run_id = f"ralph2-{uuid.uuid4().hex[:8]}"
            run = Run(
                id=run_id,
                spec_path=self.spec_path,
                spec_content=self.spec_content,
                status="running",
                config={"max_iterations": max_iterations},
                started_at=datetime.now()
            )
            self.db.create_run(run)

            print(f"🚀 Starting Ralph2 run: {run_id}")
            print(f"📋 Spec: {self.spec_path}")
            print()

            iteration_number = 0
            last_executor_summary = None
            last_verifier_assessment = None
            last_specialist_feedback = None

        # Read project memory
        memory = read_memory(self.project_context.project_id)

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
                    last_specialist_feedback=last_specialist_feedback,
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
            decision = planner_result["decision"]
            print(f"   Decision: {decision['decision']} - {decision['reason']}")
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

            # ===== CHECK IF PLANNER DECIDED TO STOP =====
            # If Planner decided DONE or STUCK, skip Executors and Feedback Generators
            if decision['decision'] in ('DONE', 'STUCK'):
                print(f"   Planner decided {decision['decision']}, skipping executor and feedback phases")

                # Update iteration outcome
                self.db.update_iteration(iteration_id, decision['decision'], datetime.now())

                # Handle termination
                if decision['decision'] == "DONE":
                    print("\n✅ Planner decided: DONE - Spec satisfied!")
                    print(f"   Reason: {decision['reason']}")
                    self.db.update_run_status(run_id, "completed", datetime.now())
                    self._write_summary(run_id)
                    return "completed"
                else:  # STUCK
                    print("\n⚠️  Planner decided: STUCK - Cannot make progress")
                    print(f"   Reason: {decision['reason']}")
                    if decision.get('blocker'):
                        print(f"   Blocker: {decision['blocker']}")
                    self.db.update_run_status(run_id, "stuck", datetime.now())
                    self._write_summary(run_id)
                    return "stuck"

            # ===== EXECUTOR(S) =====
            # Check if planner provided an ITERATION_PLAN for parallel execution
            iteration_plan = planner_result.get("iteration_plan")

            if iteration_plan and iteration_plan.get("work_items"):
                # Parallel execution mode
                work_items = iteration_plan["work_items"]
                print(f"⚙️  Running {len(work_items)} Executors in parallel...")

                # Create tasks for each executor
                executor_tasks = []
                for work_item in work_items:
                    task = run_executor(
                        iteration_intent=intent,
                        spec_content=self.spec_content,
                        memory=memory,
                        work_item_id=work_item["work_item_id"]
                    )
                    executor_tasks.append(task)

                # Run all executors in parallel
                executor_results = await asyncio.gather(*executor_tasks, return_exceptions=True)

                # Process results
                all_summaries = []
                for i, result in enumerate(executor_results):
                    work_item_id = work_items[i]["work_item_id"]

                    if isinstance(result, Exception):
                        print(f"   ❌ Executor {i+1} ({work_item_id}) error: {result}")
                        result = {
                            "status": "Blocked",
                            "summary": f"EXECUTOR_SUMMARY:\nStatus: Blocked\nWhat was done: Agent crashed with error\nBlockers: {result}\nNotes: Executor agent encountered an error and could not complete",
                            "full_output": str(result),
                            "messages": []
                        }

                    status = result["status"]
                    summary = result["summary"]
                    print(f"   Executor {i+1} ({work_item_id}) - Status: {status}")

                    # Save executor output
                    executor_output_path = self._save_agent_messages(
                        iteration_id, f"executor_{i+1}_{work_item_id}", result["messages"]
                    )
                    self.db.create_agent_output(AgentOutput(
                        id=None,
                        iteration_id=iteration_id,
                        agent_type=f"executor_{i+1}",
                        raw_output_path=executor_output_path,
                        summary=summary
                    ))

                    all_summaries.append(f"Executor {i+1} ({work_item_id}):\n{summary}")

                # Combine all summaries for feedback
                last_executor_summary = "\n\n".join(all_summaries)
                print()

            else:
                # Single executor mode (fallback)
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

            # ===== FEEDBACK GENERATORS (Verifier + Specialists) =====
            print("🔍 Running Feedback Generators (Verifier + Specialists)...")

            # Create list of specialists to run
            specialists = [
                CodeReviewerSpecialist(),
            ]

            # Run Verifier and all Specialists in parallel
            feedback_tasks = []

            # Add Verifier task
            feedback_tasks.append(run_verifier(
                spec_content=self.spec_content,
                memory=memory,
                root_work_item_id=self.root_work_item_id
            ))

            # Add Specialist tasks
            for specialist in specialists:
                feedback_tasks.append(run_specialist(
                    specialist=specialist,
                    spec_content=self.spec_content,
                    memory=memory
                ))

            # Gather all feedback in parallel
            feedback_results = await asyncio.gather(*feedback_tasks, return_exceptions=True)

            # Process Verifier result (first result)
            verifier_result = feedback_results[0]
            if isinstance(verifier_result, Exception):
                print(f"   ❌ Verifier error: {verifier_result}")
                verifier_result = {
                    "outcome": "CONTINUE",
                    "assessment": f"VERIFIER_ASSESSMENT:\nOutcome: CONTINUE\nReasoning: Verifier agent crashed with error: {verifier_result}\nGaps: Unable to verify - agent error",
                    "full_output": str(verifier_result),
                    "messages": []
                }

            outcome = verifier_result["outcome"]
            assessment = verifier_result["assessment"]
            print(f"   Verifier Outcome: {outcome}")
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

            # Process Specialist results
            specialist_feedback_summary = []
            for i, result in enumerate(feedback_results[1:], start=1):
                specialist = specialists[i-1]

                if isinstance(result, Exception):
                    print(f"   ❌ {specialist.name} error: {result}")
                    result = {
                        "specialist_name": specialist.name,
                        "error": str(result),
                        "feedback": [],
                        "full_output": "",
                        "messages": []
                    }

                specialist_name = result["specialist_name"]
                feedback_items = result.get("feedback", [])
                print(f"   {specialist_name}: {len(feedback_items)} feedback items")

                # Save specialist output
                specialist_output_path = self._save_agent_messages(
                    iteration_id, specialist_name, result.get("messages", [])
                )

                # Create summary of feedback
                feedback_summary = f"{specialist_name} feedback:\n"
                if feedback_items:
                    feedback_summary += "\n".join(f"  - {item}" for item in feedback_items)
                else:
                    feedback_summary += "  No issues found"

                self.db.create_agent_output(AgentOutput(
                    id=None,
                    iteration_id=iteration_id,
                    agent_type=specialist_name,
                    raw_output_path=specialist_output_path,
                    summary=feedback_summary
                ))

                specialist_feedback_summary.append(feedback_summary)

            # Combine all specialist feedback for next Planner iteration
            last_specialist_feedback = "\n\n".join(specialist_feedback_summary) if specialist_feedback_summary else "No specialist feedback"
            print()

            # Update iteration with Verifier outcome (for historical record)
            self.db.update_iteration(iteration_id, outcome, datetime.now())

            # ===== CHECK PLANNER'S DECISION =====
            planner_decision = decision['decision']

            if planner_decision == "DONE":
                print("\n✅ Planner decided: DONE - Spec satisfied!")
                print(f"   Reason: {decision['reason']}")
                self.db.update_run_status(run_id, "completed", datetime.now())
                self._write_summary(run_id)
                return "completed"

            elif planner_decision == "STUCK":
                print("\n⚠️  Planner decided: STUCK - Cannot make progress")
                print(f"   Reason: {decision['reason']}")
                if decision.get('blocker'):
                    print(f"   Blocker: {decision['blocker']}")
                self.db.update_run_status(run_id, "stuck", datetime.now())
                self._write_summary(run_id)
                return "stuck"

            # planner_decision == "CONTINUE" - loop continues
            print(f"   Continuing to next iteration...")

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
            f.write(f"# Ralph2 Run Summary\n\n")
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


async def run_ralph2(spec_path: str = "Ralph2file", max_iterations: int = 50) -> str:
    """
    Run Ralph2 with the given spec.

    This is a convenience function that creates a ProjectContext automatically.
    For more control, use Ralph2Runner directly with a ProjectContext.

    Args:
        spec_path: Path to the Ralph2file
        max_iterations: Maximum number of iterations

    Returns:
        Final status
    """
    ctx = ProjectContext()
    runner = Ralph2Runner(spec_path, ctx)
    try:
        return await runner.run(max_iterations)
    finally:
        runner.close()


def main():
    """Main entry point for testing."""
    import sys

    spec_path = sys.argv[1] if len(sys.argv) > 1 else "Ralph2file"

    status = asyncio.run(run_ralph2(spec_path))
    print(f"\nFinal status: {status}")


if __name__ == "__main__":
    main()
