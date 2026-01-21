"""CLI interface for SODA using Typer.

SODA (Sense-Orient-Decide-Act) is an agentic loop runner that executes
spec-driven development using Claude agents.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from soda.project import ProjectContext, find_project_root, get_project_db_path
from soda.runner import (
    BootstrapError,
    MilestoneError,
    RunContext,
    bootstrap,
    run_loop,
    setup_milestone,
)
from soda.state.db import SodaDB
from soda.state.git import GitClient
from soda.state.models import Run, RunStatus
from soda.state.trace import TraceClient

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = typer.Typer(help="SODA - Sense-Orient-Decide-Act Loop Runner")
console = Console()


def _format_status(status: RunStatus) -> str:
    """Format status with color."""
    status_colors = {
        RunStatus.RUNNING: "[blue]running[/blue]",
        RunStatus.DONE: "[green]done[/green]",
        RunStatus.STUCK: "[yellow]stuck[/yellow]",
        RunStatus.PAUSED: "[cyan]paused[/cyan]",
        RunStatus.ABORTED: "[red]aborted[/red]",
    }
    return status_colors.get(status, status.value)


def _get_project_context() -> Optional[ProjectContext]:
    """Get project context, returning None if not found."""
    try:
        return ProjectContext(require_spec=True)
    except ValueError:
        return None


@app.command()
def run(
    spec: Optional[str] = typer.Option(
        None,
        "--spec",
        "-s",
        help="Path to spec file (defaults to Sodafile in current directory)",
    ),
    max_iterations: int = typer.Option(
        20,
        "--max-iterations",
        "-m",
        help="Maximum number of iterations before halting",
    ),
):
    """
    Start a new SODA run.

    Executes the SODA loop (Sense-Orient-Decide-Act) until the spec is
    satisfied, the system gets stuck, or max iterations is reached.

    Examples:
        soda run                      # Use Sodafile in current directory
        soda run --spec myspec.md     # Use specific spec file
        soda run --max-iterations 10  # Limit iterations
    """
    # Determine spec path
    spec_path = spec or "Sodafile"
    working_dir = str(Path.cwd())

    console.print(f"[dim]Spec: {spec_path}[/dim]")
    console.print(f"[dim]Max iterations: {max_iterations}[/dim]")

    try:
        # Bootstrap phase
        console.print("\n[bold]Bootstrapping...[/bold]")
        bootstrap_result = asyncio.run(bootstrap(working_dir, spec_path))

        console.print(f"[green]✓[/green] Project ID: {bootstrap_result.project_id}")
        if bootstrap_result.is_new_project:
            console.print("[green]✓[/green] New project initialized")
        if bootstrap_result.is_kickstart:
            console.print("[yellow]![/yellow] Kickstart mode: project needs scaffolding")

        # Initialize clients
        git_client = GitClient(cwd=working_dir)
        trace_client = TraceClient()
        db = SodaDB(str(get_project_db_path(bootstrap_result.project_id)))

        # Create new run record
        run_id = str(uuid.uuid4())[:8]
        new_run = Run(
            id=run_id,
            spec_path=spec_path,
            spec_content=bootstrap_result.spec_content,
            status=RunStatus.RUNNING,
            config={"max_iterations": max_iterations},
            started_at=datetime.now(),
        )
        db.create_run(new_run)
        console.print(f"[green]✓[/green] Run ID: {run_id}")

        # Milestone phase
        console.print("\n[bold]Setting up milestone...[/bold]")
        milestone_ctx = asyncio.run(
            setup_milestone(
                project_id=bootstrap_result.project_id,
                spec_content=bootstrap_result.spec_content,
                git_client=git_client,
                trace_client=trace_client,
                db=db,
            )
        )
        console.print(f"[green]✓[/green] Branch: {milestone_ctx.milestone_branch}")
        if milestone_ctx.root_work_item_id:
            console.print(f"[green]✓[/green] Work item: {milestone_ctx.root_work_item_id}")

        # Update run with milestone info
        db.conn.execute(
            "UPDATE runs SET milestone_branch = ?, root_work_item_id = ? WHERE id = ?",
            (milestone_ctx.milestone_branch, milestone_ctx.root_work_item_id, run_id),
        )
        db.conn.commit()

        # Build run context
        run_ctx = RunContext(
            project_id=bootstrap_result.project_id,
            spec_content=bootstrap_result.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id or None,
            max_iterations=max_iterations,
            working_directory=working_dir,
            run_id=run_id,
        )

        # Run the loop
        console.print("\n[bold]Starting SODA loop...[/bold]\n")
        result = asyncio.run(run_loop(run_ctx, git_client, trace_client, db))

        # Update run status
        final_status = {
            "done": RunStatus.DONE,
            "stuck": RunStatus.STUCK,
            "max_iterations": RunStatus.PAUSED,
        }.get(result.status, RunStatus.STUCK)

        db.update_run_status(run_id, final_status, datetime.now())

        # Display result
        console.print(f"\n{'='*60}")
        if result.status == "done":
            console.print("[green]✅ SODA completed successfully![/green]")
        elif result.status == "stuck":
            console.print("[yellow]⚠️  SODA is stuck and cannot make progress.[/yellow]")
        elif result.status == "max_iterations":
            console.print(f"[yellow]⏱️  Max iterations ({max_iterations}) reached.[/yellow]")

        console.print(f"\nIterations: {result.iterations_completed}")
        console.print(f"Summary: {result.summary}")

        db.close()

    except BootstrapError as e:
        console.print(f"[red]Bootstrap error:[/red] {e}")
        raise typer.Exit(1)
    except MilestoneError as e:
        console.print(f"[red]Milestone error:[/red] {e}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.exception("Unexpected error")
        raise typer.Exit(1)


@app.command()
def status():
    """
    Show current run status.

    Displays information about the most recent SODA run.
    """
    ctx = _get_project_context()
    if not ctx:
        console.print("[yellow]No SODA project found[/yellow] (no Sodafile)")
        return

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[yellow]No SODA runs found[/yellow] (no database)")
        return

    db = SodaDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[yellow]No SODA runs found[/yellow]")
            return

        # Create status table
        table = Table(title="Current SODA Run")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Run ID", run.id)
        table.add_row("Status", _format_status(run.status))
        table.add_row("Spec", run.spec_path)
        if run.milestone_branch:
            table.add_row("Branch", run.milestone_branch)
        if run.root_work_item_id:
            table.add_row("Work Item", run.root_work_item_id)
        table.add_row("Started", run.started_at.strftime("%Y-%m-%d %H:%M:%S"))

        if run.ended_at:
            table.add_row("Ended", run.ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            duration = run.ended_at - run.started_at
            table.add_row("Duration", str(duration))

        console.print(table)

        # Show iterations
        iterations = db.get_iterations(run.id)
        if iterations:
            console.print(f"\n[bold]Iterations:[/bold] {len(iterations)}")

            for iteration in iterations[-5:]:  # Show last 5
                intent_display = (
                    f"{iteration.intent[:80]}..."
                    if len(iteration.intent) > 80
                    else iteration.intent
                )
                console.print(f"  {iteration.number}. {intent_display}")
                console.print(f"     → {iteration.outcome.value}")

    finally:
        db.close()


@app.command()
def history(
    runs: int = typer.Option(10, "--runs", "-n", help="Number of runs to show"),
):
    """
    Show past SODA runs.

    Lists historical runs with their status and basic information.
    """
    ctx = _get_project_context()
    if not ctx:
        console.print("[yellow]No SODA project found[/yellow] (no Sodafile)")
        return

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[yellow]No SODA runs found[/yellow] (no database)")
        return

    db = SodaDB(str(db_path))
    try:
        all_runs = db.list_runs()
        if not all_runs:
            console.print("[yellow]No SODA runs found[/yellow]")
            return

        # Create history table
        table = Table(title=f"SODA Run History (last {runs})")
        table.add_column("Run ID", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Started", style="white")
        table.add_column("Iterations", style="white", justify="right")
        table.add_column("Branch", style="dim")

        for r in all_runs[:runs]:
            iterations = db.get_iterations(r.id)
            table.add_row(
                r.id,
                _format_status(r.status),
                r.started_at.strftime("%Y-%m-%d %H:%M"),
                str(len(iterations)),
                r.milestone_branch or "-",
            )

        console.print(table)

    finally:
        db.close()


@app.command()
def resume(
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        "-r",
        help="Specific run ID to resume (defaults to most recent)",
    ),
    max_iterations: int = typer.Option(
        20,
        "--max-iterations",
        "-m",
        help="Maximum additional iterations to run",
    ),
):
    """
    Resume a paused or interrupted SODA run.

    Continues from where the run was paused or interrupted.
    """
    ctx = _get_project_context()
    if not ctx:
        console.print("[red]Error:[/red] No SODA project found (no Sodafile)")
        raise typer.Exit(1)

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[red]Error:[/red] No SODA database found")
        raise typer.Exit(1)

    db = SodaDB(str(db_path))
    try:
        # Find run to resume
        if run_id:
            run = db.get_run(run_id)
            if not run:
                console.print(f"[red]Error:[/red] Run {run_id} not found")
                raise typer.Exit(1)
        else:
            run = db.get_latest_run()
            if not run:
                console.print("[red]Error:[/red] No SODA runs found")
                raise typer.Exit(1)

        # Check if run can be resumed
        if run.status == RunStatus.DONE:
            console.print(f"[yellow]Run {run.id} already completed[/yellow]")
            console.print("Use 'soda run' to start a new run.")
            raise typer.Exit(1)

        if run.status == RunStatus.RUNNING:
            console.print(f"[yellow]Run {run.id} is already running[/yellow]")
            raise typer.Exit(1)

        console.print(f"[green]✓[/green] Resuming run {run.id}...")
        console.print(f"[dim]Branch: {run.milestone_branch}[/dim]")

        # Update status to running
        db.update_run_status(run.id, RunStatus.RUNNING)

        # Initialize clients
        working_dir = str(find_project_root() or Path.cwd())
        git_client = GitClient(cwd=working_dir)
        trace_client = TraceClient()

        # Setup milestone (will reuse existing)
        milestone_ctx = asyncio.run(
            setup_milestone(
                project_id=ctx.project_id,
                spec_content=run.spec_content,
                git_client=git_client,
                trace_client=trace_client,
                db=db,
                run_id=run.id,
            )
        )

        if milestone_ctx.is_resumed:
            console.print("[green]✓[/green] Reusing existing milestone")

        # Build run context
        run_ctx = RunContext(
            project_id=ctx.project_id,
            spec_content=run.spec_content,
            milestone_branch=milestone_ctx.milestone_branch,
            root_work_item_id=milestone_ctx.root_work_item_id or None,
            max_iterations=max_iterations,
            working_directory=working_dir,
            run_id=run.id,
        )

        # Continue the loop
        console.print("\n[bold]Continuing SODA loop...[/bold]\n")
        result = asyncio.run(run_loop(run_ctx, git_client, trace_client, db))

        # Update run status
        final_status = {
            "done": RunStatus.DONE,
            "stuck": RunStatus.STUCK,
            "max_iterations": RunStatus.PAUSED,
        }.get(result.status, RunStatus.STUCK)

        db.update_run_status(run.id, final_status, datetime.now())

        # Display result
        console.print(f"\n{'='*60}")
        if result.status == "done":
            console.print("[green]✅ SODA completed successfully![/green]")
        elif result.status == "stuck":
            console.print("[yellow]⚠️  SODA is stuck and cannot make progress.[/yellow]")
        elif result.status == "max_iterations":
            console.print(f"[yellow]⏱️  Max iterations ({max_iterations}) reached.[/yellow]")

        console.print(f"\nIterations: {result.iterations_completed}")
        console.print(f"Summary: {result.summary}")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.exception("Unexpected error")
        raise typer.Exit(1)
    finally:
        db.close()


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
