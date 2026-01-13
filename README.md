# Ralph

An agentic loop runner for Claude Code.

## Quick Start

```bash
# Install
git clone https://github.com/dschartman/ralph.git
cd ralph
uv sync

# Run Ralph in a project with a Ralphfile
uv run ralph
```

## What is Ralph?

Ralph is built on a core insight: **LLMs in agentic loops are stateless within invocations.** They can do genuine work, but they cannot maintain continuity of intention across context boundaries.

The name comes from Ralph Wiggum—a character who exists entirely in the present moment:
- No memory across invocations
- No self-monitoring for drift
- Genuine labor happens, but continuity is absent

Ralph (the tool) embraces this reality instead of fighting it. It provides external scaffolding for the executive functions the model cannot provide internally.

## Architecture

Ralph uses a **multi-agent architecture** with three distinct agents per iteration:

```
Iteration N:
  ┌─────────────┐
  │   Planner   │  Reads spec + memory + feedback, outputs iteration intent
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │  Executor   │  Does the assigned work, outputs efficiency notes
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │  Verifier   │  Compares spec to reality, outputs DONE/CONTINUE/STUCK
  └──────┬──────┘
         │
         ▼
    Next iteration or exit
```

Each agent runs as a fresh Claude session with its own tools and responsibilities:

| Agent | Role | Tools |
|-------|------|-------|
| **Planner** | Reads spec + trace + feedback, curates memory, outputs iteration intent | Bash, Read, Write |
| **Executor** | Does the assigned work, leaves comments in Trace | Read, Edit, Write, Bash, Glob, Grep |
| **Verifier** | Compares spec vs reality (no iteration context) | Read, Bash, Glob, Grep |

## Usage

### Core Commands

```bash
uv run ralph              # Run Ralph (requires Ralphfile in current directory)
uv run ralph status       # Show current run status
uv run ralph history      # Show past runs
uv run ralph input "msg"  # Add human input for next iteration
uv run ralph pause        # Pause current run gracefully
uv run ralph resume       # Resume a paused run
uv run ralph abort        # Abort current run
```

### Trace Commands (Task Management)

Ralph uses [Trace](https://github.com/trevorklee/trace) for task management:

```bash
trc ready                              # Show unblocked tasks
trc list                               # Show full backlog
trc show <id>                          # Show task details
trc create "title" --description "..."  # Create a task
trc close <id>                         # Mark task complete
```

## Installation

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Git repository (Ralph requires git)
- [Trace CLI](https://github.com/trevorklee/trace) (`trc` command)

### Setup

```bash
git clone https://github.com/dschartman/ralph.git
cd ralph
uv sync
```

Or install as a tool:

```bash
uv tool install --editable .
ralph  # Now available globally
```

## The Ralphfile

A Ralphfile is a specification that Ralph tries to satisfy. Place it in your project root:

```markdown
# My Project Spec

Build a CLI tool that does X.

## Acceptance Criteria

- [ ] CLI accepts --verbose flag
- [ ] Output is JSON formatted
- [ ] Tests pass with >80% coverage
```

Ralph iterates until all criteria are met (checkboxes checked) or it gets stuck.

## State Storage

Ralph stores state **outside your repo** at `~/.ralph/projects/<project-id>/`:

```
~/.ralph/projects/<uuid>/
├── ralph.db      # SQLite database (runs, iterations, agent outputs)
├── outputs/      # JSONL files for each agent invocation
├── summaries/    # Markdown summaries for completed runs
└── memory.md     # Project memory (accumulated efficiency knowledge)
```

The project ID is a UUID stored in `.ralph-id` at your repo root (gitignored).

## Project Memory

Ralph maintains a `memory.md` file that accumulates efficiency knowledge across iterations:

```markdown
- Use UV for packages: `uv run pytest`, `uv add <pkg>` (not pip)
- Tests live in tests/, run with `uv run pytest -v`
- Database schema is in src/db/schema.sql
```

Good memory entries are:
- Actionable and project-specific
- Save 2+ tool calls when consulted
- Not ephemeral state ("tests passed") or obvious facts ("uses Python")

## Project Structure

```
ralph/
├── src/ralph/
│   ├── cli.py          # Typer CLI commands
│   ├── runner.py       # Main iteration loop
│   ├── project.py      # Project context and memory
│   ├── trace.py        # Trace CLI wrapper
│   ├── agents/
│   │   ├── planner.py  # Planner agent
│   │   ├── executor.py # Executor agent
│   │   └── verifier.py # Verifier agent
│   └── state/
│       ├── db.py       # SQLite operations
│       └── models.py   # Data models
└── tests/              # Test suite
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run Ralph on itself
uv run ralph

# Check task backlog
trc ready
```

## Design Philosophy

1. **Hermetized agents** — Agents don't read CLAUDE.md or repo settings (SDK defaults only)
2. **Verifier has no iteration context** — Only sees spec vs reality, prevents premature DONE
3. **Memory over rediscovery** — Efficiency notes flow to shared project memory
4. **Test-driven executor** — Write failing tests first, then make them pass
5. **External state** — All Ralph data lives outside the repo

## License

MIT
