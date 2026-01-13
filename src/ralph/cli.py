"""CLI interface for Ralph using Typer."""

import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import subprocess
import typer
from rich.console import Console
from rich.table import Table

from .runner import run_ralph, RalphRunner
from .state.db import RalphDB
from .state.models import HumanInput
from .project import ProjectContext, ensure_ralph_id_in_gitignore, find_project_root

app = typer.Typer(help="Ralph - Multi-Agent Architecture for Spec-Driven Development")
console = Console()


def _validate_prerequisites() -> bool:
    """
    Validate that all prerequisites are met before running Ralph.

    Checks:
    1. Running inside a git repository
    2. trc command is available
    3. Initializes Trace if needed
    4. Adds .ralph/ to .gitignore

    Returns:
        True if all prerequisites are met, False otherwise
    """
    # Check for git repository
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            console.print("[red]Error:[/red] Not in a git repository")
            console.print("Ralph requires a git repository to track changes.")
            console.print("\nInitialize one with: [cyan]git init[/cyan]")
            return False
    except FileNotFoundError:
        console.print("[red]Error:[/red] git command not found")
        console.print("Ralph requires git to be installed.")
        return False

    # Check for trc command
    try:
        result = subprocess.run(
            ["trc", "--help"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            console.print("[red]Error:[/red] trc command not available")
            console.print("Ralph requires the Trace CLI (trc) to be installed.")
            console.print("\nInstall it from: [cyan]https://github.com/trevorklee/trace[/cyan]")
            return False
    except FileNotFoundError:
        console.print("[red]Error:[/red] trc command not found")
        console.print("Ralph requires the Trace CLI (trc) to be installed.")
        console.print("\nInstall it from: [cyan]https://github.com/trevorklee/trace[/cyan]")
        return False

    # Initialize Trace if needed
    trace_dir = Path(".trace")
    if not trace_dir.exists():
        console.print("[yellow]Trace not initialized. Initializing...[/yellow]")
        result = subprocess.run(
            ["trc", "init"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            console.print(f"[red]Error:[/red] Failed to initialize Trace: {result.stderr}")
            return False
        console.print("[green]✓[/green] Trace initialized")

    # Add .ralph-id to .gitignore
    project_root = find_project_root()
    if project_root:
        if ensure_ralph_id_in_gitignore(project_root):
            console.print("[green]✓[/green] Added .ralph-id to .gitignore")

    return True


@app.command()
def run(
    spec_path: str = typer.Argument("Ralphfile", help="Path to the Ralphfile (spec)"),
    max_iterations: int = typer.Option(50, help="Maximum number of iterations to run")
):
    """
    Run Ralph with the given spec.

    Requires a Ralphfile in the current directory or provide a path.
    """
    # Validate prerequisites
    if not _validate_prerequisites():
        raise typer.Exit(1)

    # Check if spec file exists
    if not Path(spec_path).exists():
        console.print(f"[red]Error:[/red] Spec file not found: {spec_path}")
        console.print("\nRalph requires a Ralphfile to run.")
        raise typer.Exit(1)

    # Get project context
    try:
        ctx = ProjectContext()
        console.print(f"[dim]Project ID: {ctx.project_id}[/dim]")
        console.print(f"[dim]State dir: {ctx.state_dir}[/dim]")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Run Ralph
    try:
        runner = RalphRunner(spec_path, ctx)
        status = asyncio.run(runner.run(max_iterations))

        if status == "completed":
            console.print("\n[green]✅ Ralph completed successfully![/green]")
        elif status == "stuck":
            console.print("\n[yellow]⚠️  Ralph is stuck and cannot make progress.[/yellow]")
        elif status == "paused":
            console.print("\n[blue]⏸️  Ralph paused by user.[/blue]")
        elif status == "aborted":
            console.print("\n[red]🛑 Ralph aborted by user.[/red]")
        elif status == "max_iterations":
            console.print(f"\n[yellow]⏱️  Max iterations ({max_iterations}) reached.[/yellow]")

        runner.close()

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status():
    """
    Show current run status.

    Displays information about the most recent Ralph run.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[yellow]No Ralph project found[/yellow] (no Ralphfile)")
        return

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[yellow]No Ralph runs found[/yellow] (no database)")
        return

    db = RalphDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[yellow]No Ralph runs found[/yellow]")
            return

        # Create status table
        table = Table(title="Current Ralph Run")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Run ID", run.id)
        table.add_row("Status", _format_status(run.status))
        table.add_row("Spec", run.spec_path)
        table.add_row("Started", run.started_at.strftime("%Y-%m-%d %H:%M:%S"))

        if run.ended_at:
            table.add_row("Ended", run.ended_at.strftime("%Y-%m-%d %H:%M:%S"))
            duration = run.ended_at - run.started_at
            table.add_row("Duration", str(duration))

        console.print(table)

        # Show iterations
        iterations = db.list_iterations(run.id)
        if iterations:
            console.print(f"\n[bold]Iterations:[/bold] {len(iterations)}")

            for iteration in iterations[-5:]:  # Show last 5
                console.print(f"  {iteration.number}. {iteration.intent[:80]}..." if len(iteration.intent) > 80 else f"  {iteration.number}. {iteration.intent}")
                console.print(f"     → {iteration.outcome}")

    finally:
        db.close()


@app.command()
def history(
    limit: int = typer.Option(10, help="Number of runs to show")
):
    """
    Show past Ralph runs.

    Lists historical runs with their status and basic information.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[yellow]No Ralph project found[/yellow] (no Ralphfile)")
        return

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[yellow]No Ralph runs found[/yellow] (no database)")
        return

    db = RalphDB(str(db_path))
    try:
        runs = db.list_runs()
        if not runs:
            console.print("[yellow]No Ralph runs found[/yellow]")
            return

        # Create history table
        table = Table(title=f"Ralph Run History (last {limit})")
        table.add_column("Run ID", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Started", style="white")
        table.add_column("Iterations", style="white", justify="right")
        table.add_column("Spec", style="white")

        for run in runs[:limit]:
            iterations = db.list_iterations(run.id)
            table.add_row(
                run.id,
                _format_status(run.status),
                run.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                str(len(iterations)),
                run.spec_path
            )

        console.print(table)

    finally:
        db.close()


@app.command()
def input(
    message: str = typer.Argument(..., help="Comment or message for next iteration")
):
    """
    Add human input for the next iteration.

    The message will be read by the Planner at the start of the next iteration.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[red]Error:[/red] No Ralph project found (no Ralphfile)")
        raise typer.Exit(1)

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[red]Error:[/red] No active Ralph run found (no database)")
        raise typer.Exit(1)

    db = RalphDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[red]Error:[/red] No Ralph run found")
            raise typer.Exit(1)

        if run.status not in ["running", "paused"]:
            console.print(f"[red]Error:[/red] Run {run.id} is {run.status}, cannot add input")
            raise typer.Exit(1)

        human_input = HumanInput(
            id=None,
            run_id=run.id,
            input_type="comment",
            content=message,
            created_at=datetime.now(),
            consumed_at=None
        )
        db.create_human_input(human_input)

        console.print(f"[green]✓[/green] Input added for run {run.id}")
        console.print(f"  Message: {message}")

    finally:
        db.close()


@app.command()
def pause():
    """
    Pause the current Ralph run after the current iteration.

    Ralph will check for this signal between iterations and pause gracefully.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[red]Error:[/red] No Ralph project found (no Ralphfile)")
        raise typer.Exit(1)

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[red]Error:[/red] No active Ralph run found (no database)")
        raise typer.Exit(1)

    db = RalphDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[red]Error:[/red] No Ralph run found")
            raise typer.Exit(1)

        if run.status != "running":
            console.print(f"[yellow]Warning:[/yellow] Run {run.id} is {run.status}, not running")
            raise typer.Exit(1)

        human_input = HumanInput(
            id=None,
            run_id=run.id,
            input_type="pause",
            content="pause",
            created_at=datetime.now(),
            consumed_at=None
        )
        db.create_human_input(human_input)

        console.print(f"[green]✓[/green] Pause signal sent for run {run.id}")
        console.print("  Ralph will pause after the current iteration completes.")

    finally:
        db.close()


@app.command()
def resume(
    max_iterations: int = typer.Option(50, help="Maximum additional iterations to run")
):
    """
    Resume a paused Ralph run.

    Continues from where the run was paused.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[red]Error:[/red] No Ralph project found (no Ralphfile)")
        raise typer.Exit(1)

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[red]Error:[/red] No Ralph database found")
        raise typer.Exit(1)

    db = RalphDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[red]Error:[/red] No Ralph run found")
            raise typer.Exit(1)

        if run.status != "paused":
            console.print(f"[yellow]Warning:[/yellow] Run {run.id} is {run.status}, not paused")
            console.print("  Use 'ralph run' to start a new run.")
            raise typer.Exit(1)

        # Update status to running
        db.update_run_status(run.id, "running")

        console.print(f"[green]✓[/green] Resuming run {run.id}...")

    finally:
        db.close()

    # Now run Ralph
    try:
        runner = RalphRunner(run.spec_path, ctx)
        status = asyncio.run(runner.run(max_iterations))

        if status == "completed":
            console.print("\n[green]✅ Ralph completed successfully![/green]")
        elif status == "stuck":
            console.print("\n[yellow]⚠️  Ralph is stuck and cannot make progress.[/yellow]")
        elif status == "paused":
            console.print("\n[blue]⏸️  Ralph paused by user.[/blue]")
        elif status == "aborted":
            console.print("\n[red]🛑 Ralph aborted by user.[/red]")
        elif status == "max_iterations":
            console.print(f"\n[yellow]⏱️  Max iterations ({max_iterations}) reached.[/yellow]")

        runner.close()

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrupted by user[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def abort():
    """
    Abort the current Ralph run.

    Ralph will check for this signal between iterations and abort gracefully.
    """
    try:
        ctx = ProjectContext()
    except ValueError:
        console.print("[red]Error:[/red] No Ralph project found (no Ralphfile)")
        raise typer.Exit(1)

    db_path = ctx.db_path
    if not db_path.exists():
        console.print("[red]Error:[/red] No active Ralph run found (no database)")
        raise typer.Exit(1)

    db = RalphDB(str(db_path))
    try:
        run = db.get_latest_run()
        if not run:
            console.print("[red]Error:[/red] No Ralph run found")
            raise typer.Exit(1)

        if run.status != "running":
            console.print(f"[yellow]Warning:[/yellow] Run {run.id} is {run.status}, not running")
            raise typer.Exit(1)

        human_input = HumanInput(
            id=None,
            run_id=run.id,
            input_type="abort",
            content="abort",
            created_at=datetime.now(),
            consumed_at=None
        )
        db.create_human_input(human_input)

        console.print(f"[green]✓[/green] Abort signal sent for run {run.id}")
        console.print("  Ralph will abort after the current iteration completes.")

    finally:
        db.close()


def _format_status(status: str) -> str:
    """Format status with color."""
    status_colors = {
        "running": "[blue]running[/blue]",
        "completed": "[green]completed[/green]",
        "stuck": "[yellow]stuck[/yellow]",
        "paused": "[blue]paused[/blue]",
        "aborted": "[red]aborted[/red]",
        "max_iterations": "[yellow]max_iterations[/yellow]"
    }
    return status_colors.get(status, status)


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
