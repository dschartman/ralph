#!/bin/bash
# ralph3 - true to the original
# Usage: cat SPEC.md | ./ralph3.sh [max_iterations]

SPEC=$(cat)
MAX="${1:-100}"

SYSTEM_PROMPT='You are one iteration of an agentic loop.

SENSE: Observe the codebase. What exists? What state is it in?
ORIENT: Compare reality to the spec. What is done? What remains?
ACT: Pick the ONE most important thing. Do ONLY that. Then stop.

Do not try to finish everything. Do the next thing, then stop.
The loop will call you again.'

for i in $(seq 1 $MAX); do
  echo "=== Iteration $i/$MAX ==="
  stdbuf -oL claude -p "$SPEC" \
    --dangerously-skip-permissions \
    --output-format stream-json \
    --setting-sources "" \
    --disable-slash-commands \
    --system-prompt "$SYSTEM_PROMPT" \
    | stdbuf -oL jq --unbuffered -r '
      select(.type == "assistant" or .type == "user") |
      if .type == "assistant" then
        .message.content[] |
        if .type == "tool_use" then
          "🔧 " + .name + ": " + (.input | tostring)
        elif .type == "text" then
          "💬 " + .text
        elif .type == "thinking" then
          "🧠 " + .thinking
        else empty end
      elif .type == "user" then
        "📤 " + (.message.content[0].content | tostring | .[0:500]) + (if (.message.content[0].content | tostring | length) > 500 then "..." else "" end)
      else empty end
    ' 2>/dev/null
  echo
done

echo "=== Loop complete ==="
