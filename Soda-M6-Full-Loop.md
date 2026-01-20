# Soda Milestone 6: Full Loop

## Context

The full SODA loop integrates all components into an end-to-end autonomous system. It handles project bootstrap, milestone setup, iteration cycling, human participation on STUCK, and run completion.

## Acceptance Criteria

### Bootstrap Phase (First Run)

- [ ] WHEN Soda runs on a fresh directory, THEN project is initialized (`.soda-id`, project directory)
- [ ] WHEN Soda runs on a fresh repo (no commits), THEN an initial empty commit is created
- [ ] WHEN bootstrap completes, THEN Soda proceeds to milestone phase

### Milestone Phase (Per Spec)

- [ ] WHEN a spec is provided, THEN spec content is loaded and stored in run record
- [ ] WHEN milestone begins, THEN milestone branch is created from main
- [ ] WHEN milestone branch name conflicts, THEN a numbered suffix is added
- [ ] WHEN milestone begins, THEN root work item is created in Trace from spec title
- [ ] WHEN resuming an interrupted run, THEN existing milestone branch and root work item are reused

### Iteration Loop

- [ ] WHEN iteration starts, THEN SENSE gathers claims from all sources
- [ ] WHEN SENSE completes, THEN ORIENT receives claims and produces assessment + plan
- [ ] WHEN ORIENT completes, THEN DECIDE routes based on structured output
- [ ] WHEN DECIDE returns CONTINUE, THEN ACT executes the iteration plan
- [ ] WHEN ACT completes, THEN loop returns to SENSE for next iteration
- [ ] WHEN DECIDE returns DONE, THEN iteration loop exits with success
- [ ] WHEN DECIDE returns STUCK, THEN iteration loop pauses for human input

### Human Participation

- [ ] WHEN STUCK occurs, THEN system outputs reason and waits for input
- [ ] WHEN human provides input via Trace (comment, task update), THEN input is detected on next SENSE
- [ ] WHEN human modifies spec, THEN modified spec is used in next iteration
- [ ] WHEN human provides correction, THEN it flows through SENSE → ORIENT as human_input claim
- [ ] WHEN human input resolves blocker, THEN iteration loop resumes

### Kickstart Handling

- [ ] WHEN project has no existing code, THEN first iteration focuses on scaffolding
- [ ] WHEN kickstart iteration runs, THEN basic project structure is created (pyproject.toml, src/, tests/)
- [ ] WHEN scaffolding is complete, THEN subsequent iterations can follow TDD cycle
- [ ] WHEN project already has structure, THEN kickstart is skipped

### Run Completion

- [ ] WHEN run completes with DONE, THEN summary is written to `summaries/` directory
- [ ] WHEN run completes with STUCK, THEN summary includes blocker details
- [ ] WHEN run completes, THEN run status is updated in database
- [ ] WHEN run completes, THEN milestone branch contains all committed work
- [ ] WHEN run completes successfully, THEN PR can be created from milestone branch

### Iteration Limits

- [ ] WHEN iteration count exceeds configured max (default: 20), THEN run is halted as STUCK
- [ ] WHEN max iterations reached, THEN summary includes progress made and remaining work
- [ ] WHEN interrupted (Ctrl+C), THEN current state is preserved for resumption

### CLI Interface

- [ ] WHEN `soda run` is executed, THEN iteration loop starts with spec from Sodafile
- [ ] WHEN `soda run --spec <path>` is executed, THEN spec is loaded from specified path
- [ ] WHEN `soda status` is executed, THEN current run state is displayed
- [ ] WHEN `soda history` is executed, THEN recent runs and iterations are listed
- [ ] WHEN `soda resume` is executed, THEN interrupted run is resumed

## Technical Constraints

- CLI must use Typer for command-line interface
- Default spec file is `Sodafile` in current directory
- State directory is `~/.soda/projects/<project-id>/`
- Max iterations is configurable via CLI flag or config
- Human input is detected through Trace, not stdin

## Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SODA RUN                                       │
│                                                                             │
│   BOOTSTRAP ──► MILESTONE ──► ┌──────────────────────────────────────┐     │
│                               │         ITERATION LOOP               │     │
│                               │                                      │     │
│                               │   SENSE ──► ORIENT ──► DECIDE        │     │
│                               │     ▲                    │           │     │
│                               │     │              ┌─────┴─────┐     │     │
│                               │     │              │           │     │     │
│                               │     │          CONTINUE      DONE    │     │
│                               │     │              │           │     │     │
│                               │     │              ▼           │     │     │
│                               │     │            ACT           │     │     │
│                               │     │              │           │     │     │
│                               │     └──────────────┘           │     │     │
│                               │                                │     │     │
│                               │   STUCK ──► wait ──► input ────┘     │     │
│                               │                                      │     │
│                               └──────────────────────────────────────┘     │
│                                                │                           │
│                                                ▼                           │
│                                           COMPLETE                         │
│                                        (summary, status)                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Assets

- SODA Loop documentation: `docs/soda-loop.md`
- Understanding Ralph: `docs/understanding-ralph.md`
- Ralph2 runner for reference: `src/ralph2/runner.py`
- Ralph2 CLI for reference: `src/ralph2/cli.py`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] Full loop runs autonomously until DONE or STUCK
- [ ] Human input on STUCK resumes the loop
- [ ] Kickstart handles new projects correctly
- [ ] Run completion produces summaries
- [ ] CLI provides run, status, history, resume commands
- [ ] Interrupted runs can be resumed
- [ ] End-to-end test: spec → autonomous iterations → DONE with working code
