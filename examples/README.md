# Examples — how an agent hands work to another role

These are **starting points for agents, not code `rh` runs**. They show the two
halves of delegation:

1. **The command** — what binary/flags start an agent. It lives in `.rh/env.json`
   (`agents.commands.<role>`, `agents.spawn`), written by the user or the
   Orchestrator. `rh` never hardcodes a flag: it substitutes placeholders into
   whatever you wrote there.
2. **The prompt** — what that agent is being asked to do. `rh spawn` builds the
   role contract (owns / may / may-not / its board tasks / its artifacts) and
   appends your instructions.

## Placeholders

Two different placeholder styles, deliberately different so they never collide:

| Where | Style | Who fills it |
|---|---|---|
| `agents.commands.<role>`, `agents.spawn` (`.rh/env.json`) | `{model}` `{thinking}` `{skills}` `{prompt}` `{prompt_file}` `{root}` `{name}` `{role}` `{command}` | `rh` (from the config block) |
| These example scripts / prompt templates | `{{STEP}}` `{{TASK}}` `{{DELIVERABLE}}` `{{VERIFY}}` | you, the agent, with `sed`/`envsubst` before calling `rh spawn` |

`${HOME}`-style shell variables survive untouched; only `{lowercase}` braces are
substituted by `rh`.

## Files

| File | What it shows |
|---|---|
| `configure-env.sh` | writing the launch commands and the pane command into `.rh/env.json` once |
| `spawn-researcher.sh` | handing one `PLAN.md` step to a fresh Researcher agent |
| `spawn-critique.sh` | opening Critique with the artifacts to attack |
| `prompts/orchestrator.md` | the session prompt for `rh resume` (`rh` adds project state around it) |
| `prompts/{literature,researcher,reviewer,critique,writer}.md` | per-role task templates with `{{…}}` placeholders |

## The loop these scripts belong to

```bash
# 1. once per project: put the commands in env.json
./examples/configure-env.sh

# 2. what would run? (never guess, always look)
rh spawn researcher "dry run" --dry-run

# 3. hand over a step
./examples/spawn-researcher.sh

# 4. record it, and close it when the job is done (SKILL.md rules 12-13)
rh add note spawns -m "researcher opened for S07 (tmux window 3)"
```

`rh spawn` only *opens* the agent. Updating `STATUS.md`, checking the gate, and
closing the pane stay with the Orchestrator — that is rule 9 and rule 13.

## Writing your own

```bash
rh env set \
  'agents.commands.researcher=<your binary> --model {model} --thinking {thinking} {prompt}' \
  'agents.roles.researcher={"provider":"<vendor>","model":"<model>","thinking":"medium"}' \
  'agents.spawn=tmux new-window -n rh-{agent} -c {root} {command}'
rh spawn researcher "read S07 of PLAN.md and implement it"
```

Nothing above is `rh`-specific knowledge: if your harness takes `--prompt-file`
instead of a positional prompt, write `... --prompt-file {prompt_file}` and `rh`
uses the file it just wrote (`.rh/tmp/spawn-<role>-prompt.md`).

> These files ship in the **source** distribution (`MANIFEST.in`). A plain
> `uv tool install rh-cli` installs the CLI and the bundled skill only — copy
> `examples/` from the [repository](https://github.com/hitaishi2222/research-helper)
> if you want them alongside an installed tool.
