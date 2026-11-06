#!/bin/sh
# spawn-critique.sh — open Critique on the artifacts that must survive scrutiny.
#
# Critique asks numbered questions against what exists (not against the plan's
# intentions), and with gates.critique_veto it can refuse the phase-7 gate.
set -eu

ROOT="${RH_ROOT:-$(pwd)}"
PHASE="${1:-7}"                               # phase being critiqued
FOCUS="${2:-<the claims, numbers or artifacts to attack>}"

echo "project: $ROOT · phase $PHASE"
if [ ! -f "$ROOT/.rh/ENV.md" ]; then
  echo "✗ no .rh/ENV.md in $ROOT — verify the path before opening an agent" >&2
  exit 1
fi

PROMPT="$ROOT/.rh/tmp/critique-prompt.md"
mkdir -p "$ROOT/.rh/tmp"
sed -e "s|{{PHASE}}|$PHASE|g" \
    -e "s|{{FOCUS}}|$FOCUS|g" \
    -e "s|{{STATUS}}|$ROOT/.rh/STATUS.md|g" \
    -e "s|{{RESULTS}}|$ROOT/results/|g" \
  "$ROOT/examples/prompts/critique.md" > "$PROMPT"

rh --root "$ROOT" spawn critique --prompt-file "$PROMPT"

echo "→ answers land in STATUS.md; zero open blocking questions closes phase 7"
