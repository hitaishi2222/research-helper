#!/bin/sh
# codex (OpenAI CLI) — copy-paste ENV snippet. Flag names live ONLY here.
set -eu
MODEL="${RH_MODEL:-<model>}"
rh env set \
  agents.count=2 \
  agents.backend=tmux \
  agents.cli=codex \
  agents.skills=research-helper \
  agents.shell=sh \
  agents.split=vertical \
  "agents.commands.orchestrator=codex --model {model} --system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  "agents.commands.default=codex --model {model} --system-prompt-file {agent_file} --prompt-file {prompt_file}" \
  'agents.spawn=tmux new-window -n rh-{project}-{agent} -c {root} {command}'
rh doctor
