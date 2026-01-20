# Soda Milestone 5: ACT

## Context

ACT modifies reality. It executes the iteration plan from ORIENT, implementing tasks through a TDD cycle. The orchestrator handles git operations (branch, commit, merge); agents handle implementation work.

## Acceptance Criteria

### Setup Workspace (Orchestrator)

- [ ] WHEN ACT begins, THEN a work branch is created from milestone branch
- [ ] WHEN work branch is created, THEN naming follows pattern `soda/iteration-N`
- [ ] WHEN setting up workspace, THEN test baseline is established by running full test suite
- [ ] WHEN test baseline is captured, THEN pass/fail counts are recorded
- [ ] WHEN tests cannot run (no test infrastructure), THEN baseline is recorded as "no tests"

### Execute Task (Agent)

- [ ] WHEN executing a task, THEN agent reads the task assignment from Trace
- [ ] WHEN executing a task, THEN agent reads relevant learnings for efficiency
- [ ] WHEN executing a task, THEN agent understands relevant code context before changing it
- [ ] WHEN task is code work, THEN TDD cycle is followed (write failing test → implement → refactor)
- [ ] WHEN task is non-code work (docs, config, research), THEN it is done directly
- [ ] WHEN task is investigation, THEN findings are documented in Trace comment

### Verify Task (Agent)

- [ ] WHEN implementation is complete, THEN tests are run
- [ ] WHEN tests pass, THEN task is marked completed
- [ ] WHEN tests fail, THEN failures are compared to baseline
- [ ] WHEN new failures exist (not in baseline), THEN agent must fix or document as blocker
- [ ] WHEN agent cannot complete task, THEN task is marked blocked with reason in Trace

### Update Trace (Agent)

- [ ] WHEN work is done on a task, THEN a progress comment is posted to Trace
- [ ] WHEN a task is completed, THEN it is closed in Trace with completion comment
- [ ] WHEN a blocker is encountered, THEN it is documented in Trace with details
- [ ] WHEN subtasks are discovered during work, THEN they are created in Trace under parent

### Commit (Orchestrator)

- [ ] WHEN a task is completed, THEN changes are committed with clear message
- [ ] WHEN committing, THEN commit message references task ID
- [ ] WHEN no changes were made, THEN no commit is created
- [ ] WHEN uncommitted changes exist at end of task, THEN they are committed or stashed

### Capture Learnings (Agent)

- [ ] WHEN task execution reveals efficiency knowledge, THEN it is captured as learning
- [ ] WHEN task completes, THEN agent is prompted: "What do you wish you knew before starting?"
- [ ] WHEN learnings are captured, THEN they are actionable and project-specific
- [ ] WHEN learnings duplicate existing memory, THEN they are noted but not duplicated

### Finalize (Orchestrator)

- [ ] WHEN all tasks are executed, THEN work branch is merged to milestone branch
- [ ] WHEN merge conflicts occur, THEN they are resolved or documented as blocker
- [ ] WHEN merge succeeds, THEN work branch is deleted
- [ ] WHEN merge fails, THEN work branch is preserved for investigation

### Output Structure

- [ ] WHEN ACT completes, THEN output includes `tasks_completed` (list of task IDs)
- [ ] WHEN ACT completes, THEN output includes `tasks_blocked` (list with task ID and reason)
- [ ] WHEN ACT completes, THEN output includes `task_comments` (comments posted)
- [ ] WHEN ACT completes, THEN output includes `new_subtasks` (subtasks created)
- [ ] WHEN ACT completes, THEN output includes `learnings` (efficiency knowledge discovered)

## Technical Constraints

- Git operations (branch, commit, merge) are orchestrator code
- Task execution is agent work with full development tools (Read, Edit, Write, Bash, Glob, Grep)
- Tasks execute serially (one at a time) in this milestone
- Commits happen at task boundaries, not mid-task
- Agent must not push to remote (only local commits)

## Data Structures

### ACT Output Schema

```python
@dataclass
class ActOutput:
    tasks_completed: list[str]      # Task IDs
    tasks_blocked: list[BlockedTask]  # Task ID + reason
    task_comments: list[TaskComment]  # Task ID + comment
    new_subtasks: list[NewTask]       # Created during work
    learnings: list[str]              # Efficiency knowledge
    commits: list[str]                # Commit hashes created
```

## Agent Pattern

ACT uses **bookended narrow** pattern:

1. **Setup**: Load task context, learnings, relevant code understanding
2. **Work**: Execute TDD cycle (narrow, focused implementation)
3. **Wrap-up**: "Did you run tests? Did you commit? Did you update Trace? What did you learn?"

## Assets

- SODA Loop documentation: `docs/soda-loop.md`
- Testing Strategy: `docs/high-leverage-testing-strategy.md`
- Ralph2 executor for reference: `src/ralph2/agents/executor.py`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] Workspace setup creates work branch and captures test baseline
- [ ] Task execution follows TDD cycle for code work
- [ ] Verification compares test results to baseline
- [ ] Trace is updated with progress, completion, and blockers
- [ ] Commits are created at task boundaries
- [ ] Learnings are captured during wrap-up
- [ ] Finalize merges work branch to milestone branch
