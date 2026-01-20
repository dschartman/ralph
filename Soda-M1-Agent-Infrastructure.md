# Soda Milestone 1: Agent Infrastructure

## Context

Soda needs a foundation layer that can invoke Claude agents in different patterns (narrow, walked, bookended) and handle their structured outputs reliably. This infrastructure enables all subsequent milestones.

## Acceptance Criteria

### Narrow Agent Pattern

- [ ] WHEN a narrow agent is invoked with a prompt and expected output schema, THEN it returns structured output matching the schema
- [ ] WHEN a narrow agent is invoked with a tool allowlist, THEN the agent only has access to those tools
- [ ] WHEN a narrow agent completes, THEN its full conversation is captured to a JSONL file

### Walked Agent Pattern

- [ ] WHEN a walked conversation is started, THEN subsequent prompts are sent to the same agent context
- [ ] WHEN multiple prompts are sent to a walked agent, THEN each response is captured in sequence
- [ ] WHEN a walked conversation is ended, THEN the full conversation is captured to a JSONL file

### Bookended Agent Pattern

- [ ] WHEN a bookended agent is invoked, THEN setup prompts execute before the main work prompt
- [ ] WHEN main work completes, THEN wrap-up prompts execute in the same context
- [ ] WHEN wrap-up completes, THEN the full conversation (setup + work + wrap-up) is captured

### Structured Output

- [ ] WHEN an agent returns output matching the expected schema, THEN the output is parsed and returned as a typed object
- [ ] WHEN an agent returns output not matching the schema, THEN a validation error is raised with details
- [ ] WHEN schema validation fails, THEN the system halts (does not retry at agent level)

### Error Handling

- [ ] WHEN a transient error occurs (rate limit, timeout, connection error, 5xx), THEN the system retries with exponential backoff (max 3 attempts)
- [ ] WHEN a fatal error occurs (invalid API key, 401, 403, permission denied), THEN the system halts immediately
- [ ] WHEN max retries are exhausted, THEN the error is surfaced with full context
- [ ] WHEN an unknown error occurs, THEN it is treated as transient (retry)

### Output Capture

- [ ] WHEN any agent invocation completes, THEN raw output is saved to `outputs/` directory
- [ ] WHEN output is captured, THEN it includes timestamp, agent type, and prompt summary
- [ ] WHEN output capture fails, THEN the agent result is still returned (capture is non-blocking)

## Technical Constraints

- Must use Python 3.11+
- Must use `uv` for package management
- Must use Claude Agent SDK for agent invocations
- Must use Pydantic for structured output validation
- Output files must be JSONL format for append-friendly logging

## Assets

- Claude Agent SDK documentation: https://platform.claude.com/docs/en/agent-sdk/python
- Ralph2 agent implementation for reference: `src/ralph2/agents/`

## Definition of Done

- [ ] All acceptance criteria have passing tests
- [ ] Can invoke narrow, walked, and bookended agents programmatically
- [ ] Structured output validation works with custom schemas
- [ ] Error handling distinguishes transient vs fatal correctly
- [ ] Output capture works for all agent patterns
