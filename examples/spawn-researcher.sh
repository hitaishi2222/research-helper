#!/bin/sh
# spawn-researcher.sh — hand ONE approved PLAN.md step to a fresh Researcher agent.
#
# Fill the <angle-bracket> values, then run it from the project root. The script
# renders examples/prompts/researcher.md, then lets `rh spawn` append the role
# contract (owned artifacts, board tasks, model, skills) and open the agent with
# the command written in .rh/ENV.md.
set -eu

ROOT="${RH_ROOT:-$(pwd)}"
STEP="<S07>"                        # plan step id (PLAN.md / `rh tasks`)
TASK="<one-line action>"            # what this agent must do right now
DELIVERABLE="<results/S07.csv>"     # where the evidence lands
VERIFY='<verify command from PLAN.md>'

echo "project: $ROOT"
if [ ! -f "$ROOT/.rh/ENV.md" ]; then
  echo "✗ no .rh/ENV.md in $ROOT — verify the path before opening an agent" >&2
  exit 1
fi

# 1. render the task template ({{PLACEHOLDER}} style, filled here, not by rh)
PROMPT="$ROOT/.rh/tmp/researcher-prompt.md"
mkdir -p "$ROOT/.rh/tmp"
sed -e "s|{{STEP}}|$STEP|g" \
    -e "s|{{TASK}}|$TASK|g" \
    -e "s|{{DELIVERABLE}}|$DELIVERABLE|g" \
    -e "s|{{VERIFY}}|$VERIFY|g" \
  "$ROOT/examples/prompts/researcher.md" > "$PROMPT"

# 2. note the spawn where the Orchestrator's own log lives (SKILL.md rule 12)
printf -- '- %s spawn researcher %s (see .rh/logs/)\n' "$(date -u +%FT%TZ)" "$STEP" \
  >> "$ROOT/.rh/logs/spawns.md"

# 3. open it: pane via agents.spawn, or a detached process with a log
rh --root "$ROOT" spawn researcher --prompt-file "$PROMPT"

echo "→ record the window in STATUS.md and close it when the step is verified (rule 13)"
