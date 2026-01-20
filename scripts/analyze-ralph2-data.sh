#!/bin/bash
# analyze-ralph2-data.sh - Utility script for analyzing Ralph2 run data
# Usage: ./scripts/analyze-ralph2-data.sh [command] [args...]

RALPH2_DIR="${RALPH2_DIR:-$HOME/.ralph2/projects}"

usage() {
    cat << EOF
Ralph2 Data Analysis Utility

Usage: $0 <command> [args]

Commands:
  overview              Quick stats on all data
  find-runs [n]         Find runs with most data (default: top 20)
  list-real             List all runs with actual iterations
  show <project-id>     Deep dive on a specific project
  show-run <proj> <run> Show details for a specific run
  stuck                 List all stuck/failed runs
  recent [n]            Show n most recent projects (default: 10)
  export <project-id>   Export project data to JSON

Examples:
  $0 overview
  $0 find-runs 10
  $0 show 8bb5a476-f9b8-4ed0-b632-111ba9571704
  $0 stuck

EOF
    exit 1
}

cmd_overview() {
    echo "=== Ralph2 Data Overview ==="
    echo ""
    echo "Total projects: $(ls "$RALPH2_DIR" 2>/dev/null | wc -l | tr -d ' ')"
    echo "Total DB size: $(du -sh "$RALPH2_DIR" 2>/dev/null | cut -f1)"
    echo ""
    echo "=== Run Status Distribution ==="
    for proj in $(ls "$RALPH2_DIR" 2>/dev/null); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        [ -f "$db" ] && sqlite3 "$db" "SELECT status FROM runs" 2>/dev/null
    done | sort | uniq -c | sort -rn
    echo ""
    echo "=== Real Runs (with iterations) ==="
    for proj in $(ls "$RALPH2_DIR" 2>/dev/null); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        [ -f "$db" ] && sqlite3 "$db" "
            SELECT r.status, COUNT(i.id) as iters
            FROM runs r JOIN iterations i ON r.id = i.run_id
            GROUP BY r.id HAVING iters > 0
        " 2>/dev/null
    done | awk -F'|' '{status[$1]++; iters[$1]+=$2} END {
        for(s in status) printf "%s: %d runs, avg %.1f iterations\n", s, status[s], iters[s]/status[s]
    }' | sort -t: -k2 -rn
}

cmd_find_runs() {
    local limit="${1:-20}"
    echo "=== Top $limit Projects by Iteration Count ==="
    for proj in $(ls "$RALPH2_DIR" 2>/dev/null); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        if [ -f "$db" ]; then
            iters=$(sqlite3 "$db" "SELECT COUNT(*) FROM iterations" 2>/dev/null)
            if [ "$iters" -gt 0 ]; then
                run_stat=$(sqlite3 "$db" "SELECT status FROM runs LIMIT 1" 2>/dev/null)
                spec=$(sqlite3 "$db" "SELECT substr(spec_content, 1, 50) FROM runs LIMIT 1" 2>/dev/null | tr '\n' ' ')
                echo "$iters|$run_stat|$proj|$spec"
            fi
        fi
    done | sort -rn -t'|' -k1 | head -"$limit" | column -t -s'|'
}

cmd_list_real() {
    echo "=== All Runs with Actual Iterations ==="
    for proj in $(ls "$RALPH2_DIR" 2>/dev/null); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        if [ -f "$db" ]; then
            sqlite3 "$db" "
                SELECT '$proj', r.id, r.status, COUNT(i.id), substr(r.spec_content, 1, 40)
                FROM runs r JOIN iterations i ON r.id = i.run_id
                GROUP BY r.id HAVING COUNT(i.id) > 0
            " 2>/dev/null
        fi
    done | column -t -s'|'
}

cmd_show() {
    local proj_id="$1"
    [ -z "$proj_id" ] && { echo "Error: project-id required"; usage; }

    local db="$RALPH2_DIR/$proj_id/ralph2.db"
    [ ! -f "$db" ] && { echo "Error: Database not found at $db"; exit 1; }

    echo "=== Project: $proj_id ==="
    echo ""
    echo "--- Runs ---"
    sqlite3 -header -column "$db" "SELECT id, status, started_at, ended_at FROM runs"

    echo ""
    echo "--- Spec (first 500 chars) ---"
    sqlite3 "$db" "SELECT substr(spec_content, 1, 500) FROM runs LIMIT 1"

    echo ""
    echo "--- Iterations ---"
    sqlite3 -header -column "$db" "
        SELECT i.number, substr(i.intent, 1, 80) as intent, i.outcome
        FROM iterations i ORDER BY i.number"

    echo ""
    echo "--- Agent Outputs ---"
    sqlite3 -header -column "$db" "
        SELECT i.number as iter, a.agent_type, substr(a.summary, 1, 100) as summary
        FROM iterations i
        JOIN agent_outputs a ON i.id = a.iteration_id
        ORDER BY i.number, a.agent_type"

    echo ""
    echo "--- Output Files ---"
    ls -la "$RALPH2_DIR/$proj_id/outputs/" 2>/dev/null || echo "No outputs directory"
}

cmd_show_run() {
    local proj_id="$1"
    local run_id="$2"
    [ -z "$proj_id" ] || [ -z "$run_id" ] && { echo "Error: project-id and run-id required"; usage; }

    local db="$RALPH2_DIR/$proj_id/ralph2.db"
    [ ! -f "$db" ] && { echo "Error: Database not found at $db"; exit 1; }

    echo "=== Run: $run_id ==="
    sqlite3 -header -column "$db" "SELECT * FROM runs WHERE id = '$run_id'"

    echo ""
    echo "--- Iterations ---"
    sqlite3 -header -column "$db" "
        SELECT i.number, i.intent, i.outcome, i.started_at, i.ended_at
        FROM iterations i WHERE i.run_id = '$run_id' ORDER BY i.number"

    echo ""
    echo "--- Verifier Progression ---"
    sqlite3 "$db" "
        SELECT i.number, a.summary
        FROM iterations i
        JOIN agent_outputs a ON i.id = a.iteration_id
        WHERE i.run_id = '$run_id' AND a.agent_type = 'verifier'
        ORDER BY i.number"
}

cmd_stuck() {
    echo "=== Stuck/Failed Runs ==="
    for proj in $(ls "$RALPH2_DIR" 2>/dev/null); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        if [ -f "$db" ]; then
            sqlite3 "$db" "
                SELECT '$proj', r.id, r.status, COUNT(i.id), substr(r.spec_content, 1, 50)
                FROM runs r LEFT JOIN iterations i ON r.id = i.run_id
                WHERE r.status IN ('stuck', 'max_iterations', 'aborted')
                GROUP BY r.id
            " 2>/dev/null
        fi
    done | column -t -s'|'
}

cmd_recent() {
    local limit="${1:-10}"
    echo "=== $limit Most Recently Modified Projects ==="
    for proj in $(ls -t "$RALPH2_DIR" 2>/dev/null | head -"$limit"); do
        db="$RALPH2_DIR/$proj/ralph2.db"
        if [ -f "$db" ]; then
            iters=$(sqlite3 "$db" "SELECT COUNT(*) FROM iterations" 2>/dev/null)
            run_stat=$(sqlite3 "$db" "SELECT status FROM runs LIMIT 1" 2>/dev/null)
            spec=$(sqlite3 "$db" "SELECT substr(spec_content, 1, 50) FROM runs LIMIT 1" 2>/dev/null | tr '\n' ' ')
            echo "$proj|$iters|$run_stat|$spec"
        else
            echo "$proj|0|no-db|"
        fi
    done | column -t -s'|'
}

cmd_export() {
    local proj_id="$1"
    [ -z "$proj_id" ] && { echo "Error: project-id required"; usage; }

    local db="$RALPH2_DIR/$proj_id/ralph2.db"
    [ ! -f "$db" ] && { echo "Error: Database not found at $db"; exit 1; }

    echo "{"
    echo '  "project_id": "'$proj_id'",'
    echo '  "runs": '
    sqlite3 -json "$db" "SELECT * FROM runs"
    echo ','
    echo '  "iterations": '
    sqlite3 -json "$db" "SELECT * FROM iterations"
    echo ','
    echo '  "agent_outputs": '
    sqlite3 -json "$db" "SELECT * FROM agent_outputs"
    echo "}"
}

# Main dispatch
case "${1:-}" in
    overview)   cmd_overview ;;
    find-runs)  cmd_find_runs "$2" ;;
    list-real)  cmd_list_real ;;
    show)       cmd_show "$2" ;;
    show-run)   cmd_show_run "$2" "$3" ;;
    stuck)      cmd_stuck ;;
    recent)     cmd_recent "$2" ;;
    export)     cmd_export "$2" ;;
    *)          usage ;;
esac
