# Per-harness ENV snippets — the ONLY place harness flags live

`rh` never learns a flag name. Each file here is a copy-paste `rh env set`
snippet for one harness; the Orchestrator edits it with the user and runs it
once per project. Python contains zero harness branches (ROADMAP principle 1).

| File | Harness | Notes |
|---|---|---|
| `pi.sh` | pi | `--system-prompt-file {agent_file}`, `--skill {skills}` |
| `claude.sh` | claude | `--append-system-prompt-file {agent_file}` (appends to the harness default) |
| `codex.sh` | codex | `--system-prompt-file {agent_file}` |

To add a harness: copy one file, replace the binary + the system-prompt flag
with what that harness actually accepts, keep `{agent_file}`, `{prompt_file}`,
`{model}`, `{skills}`, `{thinking}`. Nothing else changes.
