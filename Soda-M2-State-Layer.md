# Soda Milestone 2: State Layer

## Context

Soda needs persistent state that provides continuity across stateless agent invocations. This layer manages project identity, run history, iteration tracking, learnings, and integrations with external systems (Trace, git).

## Acceptance Criteria

### Project Management

- [ ] WHEN Soda runs in a directory without `.soda-id`, THEN a new project ID (UUID) is created and stored in `.soda-id`
- [ ] WHEN Soda runs in a directory with `.soda-id`, THEN the existing project ID is used
- [ ] WHEN a project is initialized, THEN a project directory is created at `~/.soda/projects/<project-id>/`
- [ ] WHEN `.soda-id` exists but project directory is missing, THEN the project directory is recreated

### Database Operations

- [ ] WHEN a new run starts, THEN a Run record is created with status, spec content, and timestamp
- [ ] WHEN an iteration begins, THEN an Iteration record is created linked to the run
- [ ] WHEN an agent completes, THEN an AgentOutput record is created with agent type, output path, and summary
- [ ] WHEN querying iteration history, THEN records are returned in order with intent and outcome
- [ ] WHEN a run completes, THEN run status is updated to DONE or STUCK

### Memory Management

- [ ] WHEN reading memory for a project, THEN `memory.md` content is returned (empty string if file doesn't exist)
- [ ] WHEN writing memory, THEN content is saved to `~/.soda/projects/<project-id>/memory.md`
- [ ] WHEN memory is updated, THEN previous content is preserved unless explicitly overwritten
- [ ] WHEN memory exceeds 50KB, THEN a warning is logged (memory may need curation)

### Trace Integration

- [ ] WHEN reading work state, THEN open tasks under the milestone root are returned
- [ ] WHEN reading work state, THEN blocked tasks are identified separately
- [ ] WHEN reading work state, THEN recent comments on tasks are included
- [ ] WHEN creating a task, THEN it is created in Trace with title, description, and optional parent
- [ ] WHEN closing a task, THEN it is marked closed in Trace
- [ ] WHEN posting a comment, THEN it appears on the specified task in Trace

### Git Operations

- [ ] WHEN reading code state, THEN current branch name is returned
- [ ] WHEN reading code state, THEN uncommitted changes (staged/unstaged) are detected
- [ ] WHEN reading code state, THEN commits since a base ref are listed
- [ ] WHEN reading code state, THEN diff summary since a base ref is returned
- [ ] WHEN creating a branch, THEN it is created from the specified base
- [ ] WHEN a branch already exists, THEN a numbered suffix is added (e.g., `feature/name-2`)
- [ ] WHEN checking out a branch, THEN the working tree switches to that branch

### Human Input

- [ ] WHEN human input is provided, THEN it is stored in the database linked to the current run
- [ ] WHEN reading human input, THEN pending input for the run is returned
- [ ] WHEN human input is consumed, THEN it is marked as processed

## Technical Constraints

- Must use SQLite for database storage
- Database location: `~/.soda/projects/<project-id>/soda.db`
- Must use Trace CLI (`trc`) for work tracking integration
- Must use git CLI for repository operations
- Memory file must be plain markdown

## Assets

- Trace CLI: https://github.com/dschartman/trace
- Ralph2 state implementation for reference: `src/ralph2/state/`
- Ralph2 project management for reference: `src/ralph2/project.py`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] Project initialization works on fresh directories
- [ ] Database CRUD operations work for Run, Iteration, AgentOutput, HumanInput
- [ ] Memory read/write works correctly
- [ ] Trace integration can read tasks and post comments
- [ ] Git operations can read state and manage branches
