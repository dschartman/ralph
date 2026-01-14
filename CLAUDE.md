# Ralph

An agentic loop runner for Claude Code.

## What is Ralph?

Ralph is built on a core insight: **LLMs in agentic loops are stateless within invocations.** They can do genuine work, but they cannot maintain continuity of intention across context boundaries.

The name comes from Ralph Wiggum—a character who exists entirely in the present moment:
- No memory across invocations
- No self-monitoring for drift
- Genuine labor happens, but continuity is absent
- Each stimulus is equally weighted (flat salience)

Ralph (the tool) embraces this reality instead of fighting it. It provides external scaffolding for the executive functions the model cannot provide internally.

## Architecture

Ralph uses a **multi-agent architecture** with three distinct agents per iteration:

- **Planner** — Reads spec + Trace + feedback, curates project memory, outputs iteration intent
- **Executor** — Does the assigned work, leaves comments in Trace, outputs efficiency notes
- **Verifier** — Compares spec to reality, outputs DONE/CONTINUE/STUCK (no iteration context)

Each agent runs as a fresh Claude session with its own tools and responsibilities.

## Project Structure

```
ralph/
├── CLAUDE.md           # This file
├── Ralphfile           # Spec for Ralph itself
├── pyproject.toml      # UV-managed dependencies
├── src/ralph/
│   ├── cli.py          # Typer CLI commands
│   ├── runner.py       # Main iteration loop
│   ├── project.py      # Project context, memory functions
│   ├── agents/
│   │   ├── planner.py  # Planner agent
│   │   ├── executor.py # Executor agent
│   │   └── verifier.py # Verifier agent
│   └── state/
│       ├── db.py       # SQLite operations
│       └── models.py   # Data models
└── tests/              # Comprehensive test suite
```

## Common Commands

```bash
# Run tests
uv run pytest tests/ -v

# Run Ralph in current directory (requires Ralphfile)
uv run ralph

# Check Ralph status
uv run ralph status

# View run history
uv run ralph history

# Trace commands (work tracking)
trc ready              # What's unblocked
trc list               # Full backlog
trc show <id>          # Task details
trc create "title" --description "context"
trc close <id>         # Mark complete
```

## State Location

Ralph state is stored **outside the repo** at `~/.ralph/projects/<project-id>/`:
- `ralph.db` — SQLite database (runs, iterations, agent outputs)
- `outputs/` — JSONL files for each agent invocation
- `summaries/` — Markdown summaries for completed runs
- `memory.md` — Project memory (accumulated efficiency knowledge)

The project ID is a UUID stored in `.ralph-id` at the repo root (gitignored).

## Project Memory

Ralph maintains a `memory.md` file that accumulates efficiency knowledge across iterations:
- Planner curates memory at the start of each iteration
- Executor and Verifier output efficiency notes
- Good memory entries are actionable, project-specific, and save 2+ tool calls

## Key Design Decisions

1. **Hermetized agents** — Agents don't read CLAUDE.md or repo settings (SDK defaults)
2. **Verifier has no iteration context** — Only sees spec vs reality, prevents premature DONE
3. **Memory over rediscovery** — Efficiency notes flow to project memory
4. **UV for packages** — Use `uv add`, `uv run`, never edit pyproject.toml manually

## Development

When working on Ralph:
1. Run `trc ready` to see available tasks
2. Run tests with `uv run pytest tests/ -v`
3. Test changes by running `uv run ralph` on a test Ralphfile
4. All agent prompts are in `src/ralph/agents/*.py`

## Known Issues

- Claude CLI exits with code 1 after successful completion, causing "Fatal error in message reader" warnings. This is cosmetic—work completes successfully. (ralph-1dln8j)
