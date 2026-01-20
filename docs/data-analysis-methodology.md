# Ralph2 Data Analysis Methodology

This document describes how to efficiently analyze Ralph2 run data to derive insights about agent performance, identify patterns, and improve the system.

## Data Location

Ralph2 stores state at `~/.ralph2/projects/<project-id>/`:

```
~/.ralph2/projects/<uuid>/
├── ralph2.db          # SQLite database (runs, iterations, agent outputs)
├── outputs/           # JSONL files with full Claude SDK message logs
├── summaries/         # Markdown summaries for completed runs (if generated)
└── memory.md          # Project memory (efficiency knowledge)
```

## Database Schema

```sql
-- Runs: Top-level execution of a Ralph2file
runs (
    id TEXT PRIMARY KEY,           -- e.g., "ralph2-b517b893"
    spec_path TEXT,                -- Path to Ralph2file
    spec_content TEXT,             -- Full spec content
    status TEXT,                   -- completed|running|stuck|max_iterations|aborted
    config TEXT,                   -- JSON config
    started_at TEXT,               -- ISO timestamp
    ended_at TEXT,                 -- ISO timestamp (null if running)
    root_work_item_id TEXT,        -- Trace work item ID
    milestone_branch TEXT          -- Git branch for this run
)

-- Iterations: One planning/execution cycle within a run
iterations (
    id INTEGER PRIMARY KEY,
    run_id TEXT,                   -- FK to runs
    number INTEGER,                -- 1, 2, 3...
    intent TEXT,                   -- What planner decided to do
    outcome TEXT,                  -- CONTINUE|DONE|STUCK (empty if incomplete)
    started_at TEXT,
    ended_at TEXT
)

-- Agent Outputs: Results from each agent invocation
agent_outputs (
    id INTEGER PRIMARY KEY,
    iteration_id INTEGER,          -- FK to iterations
    agent_type TEXT,               -- planner|executor_N|verifier|code_reviewer
    raw_output_path TEXT,          -- Path to JSONL file
    summary TEXT                   -- Extracted summary of agent's work
)

-- Human Inputs: User interventions during a run
human_inputs (
    id INTEGER PRIMARY KEY,
    run_id TEXT,
    input_type TEXT,               -- feedback|abort|etc
    content TEXT,
    created_at TEXT,
    consumed_at TEXT
)
```

## Key Metrics

### 1. Run Outcomes
- **completed**: Spec satisfied, work done successfully
- **running**: In progress (may be abandoned)
- **stuck**: Verifier returned STUCK, couldn't progress
- **max_iterations**: Hit iteration limit without completion
- **aborted**: User or system terminated

### 2. Iteration Efficiency
- Fewer iterations = better (completed in 2-3 iterations is ideal)
- Many iterations suggest unclear spec or difficult task
- STUCK outcomes indicate blockers worth investigating

### 3. Verifier Progression
- Verifier tracks criteria satisfaction (e.g., "5/13 criteria")
- Monotonic increase = healthy progress
- Plateaus or decreases = problems

### 4. Agent Performance
- Planner quality: Does intent match what executor does?
- Executor efficiency: How much work per iteration?
- Verifier accuracy: Does it correctly assess spec satisfaction?

## Analysis Queries

### Quick Overview
```bash
# Count all runs by status
for proj in $(ls ~/.ralph2/projects/); do
  db=~/.ralph2/projects/$proj/ralph2.db
  [ -f "$db" ] && sqlite3 "$db" "SELECT status FROM runs" 2>/dev/null
done | sort | uniq -c | sort -rn
```

### Real Runs (with actual work)
```bash
# Runs with iterations > 0, grouped by outcome
for proj in $(ls ~/.ralph2/projects/); do
  db=~/.ralph2/projects/$proj/ralph2.db
  [ -f "$db" ] && sqlite3 "$db" "
    SELECT r.status, COUNT(i.id) as iters
    FROM runs r JOIN iterations i ON r.id = i.run_id
    GROUP BY r.id HAVING iters > 0
  " 2>/dev/null
done | awk -F'|' '{status[$1]++; iters[$1]+=$2} END {
  for(s in status) printf "%s: %d runs, avg %.1f iterations\n", s, status[s], iters[s]/status[s]
}' | sort -t: -k2 -rn
```

### Find Interesting Runs
```bash
# Projects with most iterations (most data)
for proj in $(ls -t ~/.ralph2/projects/ | head -100); do
  db=~/.ralph2/projects/$proj/ralph2.db
  iters=$(sqlite3 "$db" "SELECT COUNT(*) FROM iterations" 2>/dev/null)
  [ "$iters" -gt 2 ] && echo "$iters $proj"
done | sort -rn | head -20
```

### Examine a Specific Run
```bash
PROJECT_ID="8bb5a476-f9b8-4ed0-b632-111ba9571704"
DB=~/.ralph2/projects/$PROJECT_ID/ralph2.db

# Run overview
sqlite3 -header -column $DB "SELECT id, status, started_at, ended_at FROM runs"

# Spec content
sqlite3 $DB "SELECT spec_content FROM runs LIMIT 1"

# Iteration progression
sqlite3 -header -column $DB "
SELECT i.number, i.intent, i.outcome
FROM iterations i ORDER BY i.number"

# Agent outputs per iteration
sqlite3 -header -column $DB "
SELECT i.number as iter, a.agent_type, substr(a.summary, 1, 100)
FROM iterations i
JOIN agent_outputs a ON i.id = a.iteration_id
ORDER BY i.number, a.agent_type"
```

### Verifier Analysis
```bash
# Extract criteria satisfaction progression
sqlite3 $DB "
SELECT i.number, a.summary
FROM iterations i
JOIN agent_outputs a ON i.id = a.iteration_id
WHERE a.agent_type = 'verifier'
ORDER BY i.number"
```

### Find STUCK/Failed Runs
```bash
# All stuck runs with context
for proj in $(ls ~/.ralph2/projects/); do
  db=~/.ralph2/projects/$proj/ralph2.db
  [ -f "$db" ] && sqlite3 "$db" "
    SELECT '$proj', r.id, COUNT(i.id), substr(r.spec_content, 1, 60)
    FROM runs r LEFT JOIN iterations i ON r.id = i.run_id
    WHERE r.status IN ('stuck', 'max_iterations', 'aborted')
    GROUP BY r.id
  " 2>/dev/null
done
```

## JSONL Output Analysis

The `outputs/` directory contains full Claude SDK message logs as JSONL files:
- `iteration_N_planner.jsonl`
- `iteration_N_executor_M_<branch>.jsonl`
- `iteration_N_verifier.jsonl`
- `iteration_N_code_reviewer.jsonl`

### Useful JSONL Queries
```bash
# Get first message (session init)
head -1 outputs/iteration_1_planner.jsonl | python3 -m json.tool

# Count messages per file
wc -l outputs/*.jsonl

# Find tool usage patterns
grep -o '"name": "[^"]*"' outputs/*.jsonl | cut -d'"' -f4 | sort | uniq -c | sort -rn
```

## Research Workflow

### 1. Start with Overview
```bash
# Get lay of the land
echo "Total projects: $(ls ~/.ralph2/projects/ | wc -l)"
echo "Projects with data: $(find ~/.ralph2/projects -name 'ralph2.db' | wc -l)"
```

### 2. Find Interesting Runs
Focus on:
- Completed runs with 3+ iterations (enough data to analyze)
- Stuck/max_iterations runs (failure patterns)
- Recent runs (latest code behavior)

### 3. Deep Dive on Specific Runs
For each run of interest:
1. Read the spec to understand the goal
2. Walk through iterations chronologically
3. Note planner decisions and executor outcomes
4. Track verifier progression
5. Identify where things went well/poorly

### 4. Compare Patterns
- What do successful 2-iteration runs have in common?
- What causes runs to get stuck?
- What specs are too vague or too complex?

### 5. Extract Insights
Document findings as:
- Spec writing best practices
- Common failure modes
- Agent prompt improvements
- Configuration recommendations

## Data Volumes (Reference)

As of 2026-01-19:
- 2,331 total projects
- 1,046 projects with runs
- 104MB total database size
- 296 completed runs with actual iterations
- Avg 2.0 iterations for completed runs
- 7 running, 3 stuck, 2 max_iterations, 1 aborted (with iterations)

## Tips for Efficient Analysis

1. **Filter early**: Most projects are test fixtures. Focus on `iterations > 0`.
2. **Use recent data**: `ls -t` sorts by modification time.
3. **Batch queries**: Loop through projects once, collect all needed data.
4. **Sample first**: Test queries on 1-2 projects before running on all.
5. **Track findings**: Keep notes on what you discover for future reference.

## Utility Script

A utility script is available at `scripts/analyze-ralph2-data.sh`:

```bash
# Quick overview of all data
./scripts/analyze-ralph2-data.sh overview

# Find runs with most data
./scripts/analyze-ralph2-data.sh find-runs 20

# List all stuck/failed runs
./scripts/analyze-ralph2-data.sh stuck

# Deep dive on a project
./scripts/analyze-ralph2-data.sh show <project-uuid>

# Show recent projects
./scripts/analyze-ralph2-data.sh recent 10

# Export project to JSON
./scripts/analyze-ralph2-data.sh export <project-uuid>
```

## Initial Findings (2026-01-19)

### Data Distribution
- 2,331 total projects, but most are test fixtures
- 296 completed runs with actual iterations (work done)
- 507 "completed" runs with 0 iterations (test fixtures or immediate satisfaction)
- Average completed run: 2.0 iterations

### Outcome Patterns
| Status | Runs | Avg Iterations | Notes |
|--------|------|----------------|-------|
| completed | 296 | 2.0 | Healthy runs complete in 2-3 iterations |
| running | 7 | 4.9 | May be abandoned or very complex |
| stuck | 3 | 3.3 | Hit blockers worth investigating |
| max_iterations | 2 | 25.5 | Couldn't converge, possible spec issues |
| aborted | 1 | 5.0 | User terminated |

### Key Observations
1. **Successful runs are efficient**: Avg 2 iterations suggests the planner/executor/verifier loop works well
2. **max_iterations runs ran 25+ cycles**: These likely have spec issues or hit edge cases
3. **Multiple runs per project**: Some projects have 8+ runs (testing/iteration)
4. **Verifier progression is trackable**: Can observe criteria satisfaction over time

### Questions for Further Research
1. What spec characteristics lead to faster completion?
2. What causes STUCK outcomes? (Look at verifier summaries)
3. Are there patterns in code_reviewer feedback that correlate with stuck runs?
4. How does parallel executor count affect efficiency?
