# Soda Orchestration

> **Document Scope:** This is a tactical architecture document for Soda (Ralph3). It defines the responsibilities of the orchestrator vs. agents, the data flow between phases, and the contracts at each boundary. For the conceptual model, see [The SODA Loop](./soda-loop.md).

---

## Overview

Soda implements the SODA loop (Sense → Orient → Decide → Act) through a combination of:

- **Orchestrator code** — Deterministic operations: reading state, routing decisions, git operations
- **Agents** — Reasoning operations: verification, assessment, planning, implementation

The key principle: **anything that requires reasoning gets an agent; everything else is orchestrator code.**

All agents use **structured output** so the orchestrator can parse results and route data between phases.

---

## Phase Responsibilities

### SENSE — Orchestrator

SENSE gathers claims from systems. No reasoning required—just bounded queries.

| Sub-group | Source | What to Gather | Bounds |
|-----------|--------|----------------|--------|
| CODE_STATE | Git | Current branch, uncommitted changes, commits since milestone base, diff summary | Not full history—just since milestone base |
| WORK_STATE | Trace | Open tasks, blocked tasks, recent comments under milestone | Not entire trace history |
| PROJECT_STATE | DB | Current iteration number, recent iteration outcomes and summaries | Recent iterations in current run (for loop detection), not all prior runs |
| HUMAN_INPUT | Queue | Pending corrections, overrides, spec modifications | Just the queue |

**Why orchestrator:** These are defined queries with structural bounds, not judgment calls about what matters.

**Output:** Structured claims document passed to ORIENT.

---

### ORIENT — Agent(s)

ORIENT is where judgment lives. It verifies claims, assesses reality against the spec, and plans the next iteration.

**Inputs:**
- Claims from SENSE (structured)
- Spec (the goal)
- Learnings (efficiency knowledge)
- Codebase access (for verification)

**Activities (all require reasoning):**
- Verify claims against codebase (is "closed" actually done in code?)
- Assess spec satisfaction (are acceptance criteria met?)
- Apply constraint filters (security, quality, test validity)
- Identify gaps (what's missing?)
- Update task breakdown (close verified tasks, create gap tasks)
- Plan iteration (select tasks, define intent)

**Outputs (structured):**
- `spec_satisfied`: boolean
- `actionable_work_exists`: boolean
- `verified_task_states`: list of task updates for Trace
- `gaps`: list of identified gaps
- `iteration_plan`: tasks to execute, iteration intent
- `learnings`: curated efficiency knowledge

**Output destinations:**
- → DECIDE: `spec_satisfied`, `actionable_work_exists`
- → Trace: `verified_task_states`
- → ACT: `iteration_plan`
- → Memory: `learnings`

**Open question:** Is ORIENT one agent or multiple? See [Agent Granularity](#agent-granularity-open-question).

---

### DECIDE — Orchestrator

DECIDE is simple routing logic based on ORIENT's structured output.

```
if spec_satisfied:
    return DONE
elif not actionable_work_exists:
    return STUCK
else:
    return CONTINUE
```

**Why orchestrator:** No reasoning required—just conditional logic on structured data.

**Output:** Decision enum: `DONE | STUCK | CONTINUE`

---

### ACT — Mixed

ACT modifies reality. Some parts are orchestrator code, some require agents.

| Activity | Responsibility | Why |
|----------|---------------|-----|
| SETUP_WORKSPACE | Orchestrator | Git operations: create branch, establish test baseline |
| EXECUTE | Agent(s) | Reasoning required: implement tasks, TDD cycle |
| FINALIZE | Orchestrator | Git operations: merge, handle conflicts |

**EXECUTE Inputs:**
- Iteration plan from ORIENT
- Learnings
- Codebase access

**EXECUTE Outputs (structured):**
- `task_updates`: status changes, comments for Trace
- `blockers`: documented blockers encountered
- `learnings`: efficiency discoveries

**Output destinations:**
- → Git: commits (during execution)
- → Trace: `task_updates`, `blockers`
- → Memory: `learnings`
- → (loop back to SENSE)

---

## Data Flow Summary

```
┌─────────────┐
│    SENSE    │  Orchestrator
│             │
│ Git ────────┼──► code_claims
│ Trace ──────┼──► work_claims
│ DB ─────────┼──► project_claims
│ Human ──────┼──► human_input
└──────┬──────┘
       │ claims (structured)
       ▼
┌─────────────┐
│   ORIENT    │  Agent(s)
│             │
│ claims ─────┼──► verified_reality
│ spec ───────┼──► spec_satisfied
│ learnings ──┼──► gaps, iteration_plan
│ codebase ───┼──► task_updates, learnings
└──────┬──────┘
       │ structured outputs
       ▼
┌─────────────┐
│   DECIDE    │  Orchestrator
│             │
│ spec_satisfied ────┼──► DONE
│ actionable_work ───┼──► STUCK / CONTINUE
└──────┬──────┘
       │ decision
       ▼ (if CONTINUE)
┌─────────────┐
│     ACT     │  Mixed
│             │
│ SETUP ──────┼──► Orchestrator (git)
│ EXECUTE ────┼──► Agent(s) (implement)
│ FINALIZE ───┼──► Orchestrator (merge)
└──────┬──────┘
       │ modified reality
       ▼
    (loop to SENSE)
```

---

## Agent Granularity (Open Question)

For phases that require reasoning (ORIENT, ACT.EXECUTE), there are two patterns:

### Pattern A: Orchestrator-Walked Conversation

One agent context, orchestrator guides through milestones via prompts.

```
Orchestrator
    │
    └──► Single Agent Context
              │
              ├── "Verify these claims against the codebase"
              │        → structured output
              │
              ├── "Assess spec satisfaction"
              │        → structured output
              │
              └── "Plan the iteration"
                       → structured output
```

**Pros:**
- Context carries forward (agent can reference earlier findings)
- Simpler state passing

**Cons:**
- Context accumulates cruft
- One bad step can contaminate subsequent steps
- Harder to test/optimize individual steps

### Pattern B: Multiple Specialized Agents

Fresh context for each responsibility.

```
Orchestrator
    │
    ├──► Verifier Agent
    │         claims → verified_reality
    │
    ├──► Assessor Agent
    │         verified_reality + spec → satisfaction + gaps
    │
    └──► Planner Agent
              gaps + learnings → iteration_plan
```

**Pros:**
- Fresh context prevents drift (core Ralph principle)
- Each agent optimized for one job
- Testable in isolation
- Failure contained

**Cons:**
- More orchestration complexity
- State must be serialized at every boundary
- Potential information loss at handoffs

### Decision Criteria

The right pattern depends on:
- Complexity of instructions for each step
- Whether context carryover helps or hurts
- How tightly coupled the sub-steps are
- Iterations-to-solution (the real efficiency measure)

**This remains an open question.** May require prototyping both to determine. The comparison should focus on whether each iteration produces value, not on token usage.

---

## Structured Output Contracts

All agents return structured output. The orchestrator parses and routes.

### ORIENT Output Schema (Draft)

```
{
  "spec_satisfied": boolean,
  "actionable_work_exists": boolean,
  "confidence": "high" | "medium" | "low",

  "task_updates": [
    {
      "task_id": string,
      "action": "close" | "update" | "block",
      "reason": string
    }
  ],

  "new_tasks": [
    {
      "title": string,
      "description": string,
      "parent_id": string | null
    }
  ],

  "gaps": [
    {
      "description": string,
      "severity": "blocking" | "important" | "minor"
    }
  ],

  "iteration_plan": {
    "intent": string,
    "tasks": [string],  // task IDs to execute
    "approach": string
  },

  "learnings": [string]
}
```

### ACT.EXECUTE Output Schema (Draft)

```
{
  "tasks_completed": [string],  // task IDs
  "tasks_blocked": [
    {
      "task_id": string,
      "reason": string
    }
  ],

  "task_comments": [
    {
      "task_id": string,
      "comment": string
    }
  ],

  "new_subtasks": [
    {
      "title": string,
      "description": string,
      "parent_id": string
    }
  ],

  "learnings": [string]
}
```

---

## Error Handling Philosophy

Errors fall into two categories that require different responses:

### Transient Failures

Network timeouts, API rate limits, temporary unavailability. These are expected in distributed systems.

**Handling:** Retry at the base communication layer (the "bronze" layer that wraps API calls). This is built into the infrastructure, not the orchestration logic. A reasonable retry with backoff, then surface the failure.

### Structural Failures

Validation errors, malformed agent output, schema mismatches. These indicate a problem with the system design, not a temporary condition.

**Handling:** Halt and investigate. Do not retry at the agent level.

```
Agent returns output
         │
         ▼
Structured output validation
         │
    ┌────┴────┐
    │         │
  VALID    INVALID
    │         │
    ▼         ▼
 Continue   HALT
            (investigate prompts,
             schemas, agent design)
```

**Why no agent-level retries:** Asking an agent "you did this wrong, do it right" creates an inefficient loop. If the agent couldn't produce valid output the first time, the problem is likely in the prompt design or schema definition—not something retrying will fix. Investigation and correction is the appropriate response.

**Efficiency measure:** The real measure of system efficiency is iterations-to-solution and whether each iteration produced value, not token usage. Minimizing wasted iterations matters more than minimizing tokens per iteration.

---

## Loop Detection

PROJECT_STATE in SENSE includes recent iteration history to detect loops.

**What to track:**
- Last N iteration intents
- Last N iteration outcomes
- Patterns: "same intent repeated 3+ times with same outcome"

**How ORIENT uses it:**
- If loop detected, ORIENT should note it in gaps
- May trigger different planning approach or STUCK recommendation

**Open question:** How many iterations constitute a "loop"? What's the threshold?

---

## Relationship to SODA Loop

This document is the tactical counterpart to [soda-loop.md](./soda-loop.md):

| SODA Loop (Conceptual) | Soda Orchestration (Tactical) |
|------------------------|-------------------------------|
| What the phases ARE | Who performs each activity |
| Data flow between phases | Structured contracts at boundaries |
| Design principles | Implementation patterns |
| Why this works | How to build it |

---

## Open Questions

1. **ORIENT granularity:** One agent walked through steps, or multiple specialized agents?

2. **Loop detection threshold:** How many repeated iterations before flagging?

3. **SENSE bounds for new projects:** If milestone base is empty, CODE_STATE is "everything." Is that okay, or do we need different handling?

4. **Constraint filters:** Are these part of ORIENT agent(s), or separate specialist agents?
