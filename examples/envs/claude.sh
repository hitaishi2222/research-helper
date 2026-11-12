#!/bin/sh
# claude (Anthropic CLI) — copy-paste ENV snippet. Flag names live ONLY here.
set -eu
MODEL="${RH_MODEL:-<model>}"
rh env set \
  agents.count=2 \
  agents.backend=tmux \
  agents.cli=claude \
  agents.skills=research-helper \
  agents.shell=sh \
  agents.split=vertical \
  "agents.commands.orchestrator=claude --model {model} --append-system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  "agents.commands.default=claude --model {model} --append-system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  'agents.spawn=tmux new-window -n rh-{project}-{agent} -c {root} {command}'
rh doctor
