#!/bin/sh
# configure-env.sh — put the agent launch commands into .rh/env.json (once per project).
#
# These values are EXAMPLES shaped for a `pi`-style CLI and tmux. Replace the
# binary and every flag with the ones your harness actually accepts: `rh` only
# substitutes {placeholders} into what you write here, it never invents a flag.
set -eu

MODEL="${RH_MODEL:-<model>}"          # e.g. glm-5
THINKING="${RH_THINKING:-high}"       # e.g. high | medium | low
SKILL_FLAG="${RH_SKILL_FLAG:---skill}"  # how your CLI loads a skill, if it can

rh env set \
  agents.count=2 \
  agents.backend=tmux \
  agents.skills=research-helper \
  "agents.roles.orchestrator={\"provider\":\"pi\",\"model\":\"$MODEL\",\"thinking\":\"$THINKING\"}" \
  "agents.roles.researcher={\"provider\":\"pi\",\"model\":\"$MODEL\",\"thinking\":\"medium\"}" \
  "agents.roles.critique={\"provider\":\"pi\",\"model\":\"$MODEL\",\"thinking\":\"medium\"}" \
  "agents.commands.orchestrator=pi --model {model} --thinking {thinking} --append-system-prompt {agent_file} {prompt}" \
  "agents.commands.researcher=pi --model {model} --thinking {thinking} $SKILL_FLAG {skills} --append-system-prompt {agent_file} {prompt}" \
  "agents.commands.critique=pi --model {model} --thinking {thinking} $SKILL_FLAG {skills} --append-system-prompt {agent_file} {prompt}" \
  "agents.commands.default=pi --model {model} --thinking {thinking} $SKILL_FLAG {skills} --append-system-prompt {agent_file} {prompt}" \
  'agents.spawn=tmux new-window -n rh-{project}-{agent} -c {root} {command}'

# The same selection drives `rh resume`: model + thinking level from
# agents.roles.orchestrator, skills from agents.skills.
rh env show
