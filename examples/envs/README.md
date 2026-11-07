# Per-harness ENV snippets — the ONLY place harness flags live

`rh` never learns a flag name. Each file here is a copy-paste `rh env set`
snippet for one harness; the Orchestrator edits it with the user and runs it
once per project. `rh init` can also apply the same start template when the user
picks a harness (`src/rh/harnesses.json` — data, not code). Python contains zero
harness branches (ROADMAP principle 1).

| File | Harness | Notes |
|---|---|---|
| `pi.sh` | pi | `--append-system-prompt {agent_file}` (never `--system-prompt`), `--skill {skills}` for worker roles apart from the orchestrator; the prompt is positional |
| `claude.sh` | claude | `--append-system-prompt-file {agent_file}` (appends to the harness default) |
| `codex.sh` | codex | `--system-prompt-file {agent_file}` |

To add a harness: copy one file, replace the binary + the system-prompt flag
with what that harness actually accepts, keep `{agent_file}`, `{prompt}` (or
`{prompt_file}` only if the CLI really has such a flag), `{model}`, `{skills}`,
`{thinking}`. Nothing else changes. Note: pi's `--prompt-template` is NOT a
prompt — it registers a `/command` and sends no message.
