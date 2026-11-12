#!/bin/sh
# pi — copy-paste ENV snippet. NOT executed by rh; the Orchestrator edits it
# with the user. The pi-specific flags live ONLY here, in .rh/env.json, and in
# src/rh/harnesses.json (the init start template) — rh never hardcodes them.
set -eu
MODEL="${RH_MODEL:-<model>}"
THINKING="${RH_THINKING:-high}"
rh env set \
  agents.count=2 \
  agents.backend=tmux \
  agents.cli=pi \
  agents.skills=research-helper \
  agents.shell=sh \
  agents.split=vertical \
  "agents.roles.orchestrator={\"provider\":\"pi\",\"model\":\"$MODEL\",\"thinking\":\"$THINKING\"}" \
  "agents.commands.orchestrator=pi --model {model} --thinking {thinking} --append-system-prompt {agent_file} {prompt}" \
  "agents.commands.default=pi --model {model} --thinking {thinking} --skill {skills} --append-system-prompt {agent_file} {prompt}" \
  'agents.spawn=tmux new-window -n rh-{project}-{agent} -c {root} {command}'
rh doctor
