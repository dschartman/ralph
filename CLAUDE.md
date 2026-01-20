# Ralph2

An agentic loop runner for Claude Code.

> **Note:** This project was renamed from Temper back to Ralph2. Both `ralph` (legacy) and `ralph2` (active) CLIs exist.

## What is Ralph2?

Ralph2 is built on a core insight: **LLMs in agentic loops are stateless within invocations.** They can do genuine work, but they cannot maintain continuity of intention across context boundaries.

Ralph2 provides external scaffolding for the executive functions the model cannot provide internally.

## Architecture

Ralph2 uses a **multi-agent architecture** with three distinct agents per iteration:

- **Planner** — Reads spec + Trace + feedback, curates project memory, outputs iteration intent
- **Executor** — Does the assigned work, leaves comments in Trace, outputs efficiency notes
- **Verifier** — Compares spec to reality, outputs DONE/CONTINUE/STUCK (no iteration context)

Each agent runs as a fresh Claude session with its own tools and responsibilities.

## Project Structure

```
ralph/                      # Repo name
├── CLAUDE.md               # This file
├── Ralph2file              # Spec for Ralph2 (active development)
├── Ralphfile               # Spec for Ralph (legacy)
├── pyproject.toml          # UV-managed dependencies
├── docs/                   # Theory and architecture docs
│   ├── understanding-ralph.md
│   ├── agent-orchestration-model.md
│   ├── data-analysis-methodology.md
│   └── soda-loop.md
├── scripts/
│   └── analyze-ralph2-data.sh  # Data analysis utility
├── src/
│   ├── ralph/              # Original implementation (frozen)
│   └── ralph2/             # New implementation (active development)
│       ├── cli.py          # Typer CLI commands
│       ├── runner.py       # Main iteration loop
│       ├── project.py      # Project context, memory functions
│       ├── trace.py        # Trace CLI wrapper
│       ├── agents/
│       │   ├── planner.py  # Planner agent
│       │   ├── executor.py # Executor agent
│       │   └── verifier.py # Verifier agent
│       └── state/
│           ├── db.py       # SQLite operations
│           └── models.py   # Data models
└── tests/                  # Test suite
```

## Development Workflow

**Two CLIs exist:**
- `uv run ralph` — Uses `src/ralph/`, `Ralphfile`, `~/.ralph/`
- `uv run ralph2` — Uses `src/ralph2/`, `Ralph2file`, `~/.ralph2/`

**Active development is on Ralph2.** Ralph is frozen and can be used to build Ralph2 (bootstrapping).


## Common Commands

```bash
# Run tests
uv run pytest tests/ -v

# Run Ralph2 (requires Ralph2file)
uv run ralph2 run
uv run ralph2 status
uv run ralph2 history

# Run Ralph (requires Ralphfile) - legacy
uv run ralph run

# Trace commands (work tracking)
trc ready              # What's unblocked
trc list               # Full backlog
trc show <id>          # Task details
trc create "title" --description "context"
trc close <id>         # Mark complete
```

## Using Trace for Work Tracking

This project uses [Trace](https://github.com/dschartman/trace) for persistent
work tracking across AI sessions.

**When to use trace vs TodoWrite:**

Use trace instead of TodoWrite for any non-trivial work. If it involves multiple
files, could span sessions, or needs to persist - use trace.

- **TodoWrite**: Single-session trivial tasks only
- **Trace**: Everything else (features, bugs, planning, multi-step work)
- **When in doubt**: Use trace

**Why this matters:** Trace persists across sessions and commits to git. TodoWrite
is ephemeral. For a tool designed around persistent work tracking, using TodoWrite
defeats the purpose.

**Setup (required once per project):**

```bash
trc init  # Run this first in your git repo
```

If you forget, you'll see: "Error: Project not initialized. Run 'trc init' first"

**Core workflow:**

```bash
# Create work
trc create "title" --description "context"
trc create "subtask" --description "details" --parent <id>

# Discover work
trc ready              # What's unblocked and ready to work on
trc list               # Current backlog (excludes closed)
trc show <id>          # Full details with dependencies

# Complete work
trc close <id> [...]   # Close one or more issues
```

**Essential details:**

- `--description` is required (preserves context across sessions for AI agents)
  - Use `--description ""` to explicitly skip if truly not needed
- Structure is fluid: Break down or reorganize as understanding evolves
- Use `--parent <id>` to create hierarchical breakdowns
- Cross-project: Add `--project <name>` to work across repositories
- Use `trc <command> --help` for full options

For more details: https://github.com/dschartman/trace

## State Location

**Ralph2:** State stored at `~/.ralph2/projects/<project-id>/`:
- `ralph2.db` — SQLite database (runs, iterations, agent outputs)
- `outputs/` — JSONL files for each agent invocation
- `summaries/` — Markdown summaries for completed runs
- `memory.md` — Project memory (accumulated efficiency knowledge)

The project ID is a UUID stored in `.ralph2-id` at the repo root (gitignored).

**Ralph (legacy):** State at `~/.ralph/projects/<project-id>/` with `.ralph-id`.

## Project Memory

Ralph2 maintains a `memory.md` file that accumulates efficiency knowledge across iterations:
- Planner curates memory at the start of each iteration
- Executor and Verifier output efficiency notes
- Good memory entries are actionable, project-specific, and save 2+ tool calls

## Key Design Decisions

1. **Hermetized agents** — Agents don't read CLAUDE.md or repo settings (SDK defaults)
2. **Verifier has no iteration context** — Only sees spec vs reality, prevents premature DONE
3. **Memory over rediscovery** — Efficiency notes flow to project memory
4. **UV for packages** — Use `uv add`, `uv run`, never edit pyproject.toml manually

## Development

When working on Ralph2:
1. Run `trc ready` to see available tasks
2. Run tests with `uv run pytest tests/ -v`
3. Test changes by running `uv run ralph2 run` on a test Ralph2file
4. All agent prompts are in `src/ralph2/agents/*.py`

## Analyzing Run Data

Ralph2 collects data on every run: iterations, agent outputs, verifier progression, and outcomes. Use this for research and improvement.

**Quick commands:**
```bash
# Overview of all data
./scripts/analyze-ralph2-data.sh overview

# Find runs with most data
./scripts/analyze-ralph2-data.sh find-runs 20

# List stuck/failed runs
./scripts/analyze-ralph2-data.sh stuck

# Deep dive on a project
./scripts/analyze-ralph2-data.sh show <project-uuid>
```

**Key insight:** Filter by `iterations > 0` to exclude test fixtures. Real runs average 2.0 iterations to completion.

See:
- `docs/data-analysis-methodology.md` — SQL queries, research workflow, data volumes
- `docs/soda-loop.md` — The SODA Loop: conceptual model for agentic iteration

## Known Issues

- Claude CLI exits with code 1 after successful completion, causing "Fatal error in message reader" warnings. This is cosmetic—work completes successfully.
