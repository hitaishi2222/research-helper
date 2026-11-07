#!/bin/sh
# pi — copy-paste ENV snippet. NOT executed by rh; the Orchestrator edits it
# with the user. The pi-specific flags live ONLY here and in .rh/ENV.md —
# rh never hardcodes them (see ROADMAP principle 1).
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
  "agents.commands.orchestrator=pi --model {model} --thinking {thinking} --skill {skills} --system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  "agents.commands.default=pi --model {model} --thinking {thinking} --skill {skills} --system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  'agents.spawn=tmux new-window -n rh-{agent} -c {root} {command}'
rh doctor
