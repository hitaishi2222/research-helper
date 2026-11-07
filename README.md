# research-helper

**`rh` — orchestrate an AI research project end to end from the terminal.**

[![CI](https://github.com/hitaishi2222/research-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/hitaishi2222/research-helper/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rh-cli.svg)](https://pypi.org/project/rh-cli/)
[![Python](https://img.shields.io/pypi/pyversions/rh-cli.svg)](https://pypi.org/project/rh-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`rh` turns a research idea into a gated pipeline — config → intake → environment →
literature → plan → state → implement → critique → manuscript → close — with every
artifact, task, and decision kept in files an agent can read.

The **CLI is the product**. The **skill is additive**: it teaches an AI agent (pi,
Claude, Codex, …) how to drive `rh`, ask the user the right questions, and respect the
gates. Install the CLI, then optionally install the skill globally.

---

## Install

```bash
# once published to PyPI (distribution name: rh-cli, command: rh)
uv tool install rh-cli

# or straight from git
uv tool install git+https://github.com/hitaishi2222/research-helper

# or from a clone
git clone https://github.com/hitaishi2222/research-helper
cd research-helper
uv tool install .
```

`pipx install rh-cli` and `pip install --user rh-cli` work too.
Verify with:

```bash
rh --version
rh describe
```

### Install the skill (optional)

```bash
rh skill install                 # ~/.agents/skills/research-helper/
rh skill install --dest ~/.pi/agent/skills/research-helper   # pi-specific location
```

Pi and other [Agent Skills](https://agentskills.io/specification) clients discover
`~/.agents/skills/` automatically. The skill is bundled in the wheel, so there is
nothing else to download.

---

## Quickstart

```bash
rh init                          # in the project directory; asks a few questions (Enter keeps values, s=skip)
rh init --dry-run                # preview without writing anything, not even the prompt files
rh init --force                  # archive a copy of ENV.md/tasks.json to .rh/.bak/ before writing
rh init --clean                   # archive the whole .rh/ (event logs, notes) then recreate it
rh env set agents.count=2 agents.backend=tmux agents.cli=pi \
  agents.skills=research-helper,crw literature.search=crw project.git=true
rh env show                 # config as a table, validated
rh phase 4                  # gated: refuses to skip unmet exits
rh phase                    # what the current phase still needs
rh describe                 # the map an agent reads
rh resume --dry-run         # the exact command the orchestrator would start
rh spawn researcher "implement S07 of PLAN.md"
rh info PLAN.md             # what that file is for, its sections, its template
```

The Orchestrator (your agent) interviews you for the environment and writes the
`## Environment` section of `.rh/ENV.md`; `rh` never probes or auto-fills binaries.
A tool on `PATH` does not mean this project should use it.

---

## Commands

| Command | What it does |
|---|---|
| `rh init [--force] [--clean] [--dry-run]` | create the `.rh/` workspace **here**, non-destructively (archives before writing or removing); the project name is the directory, changeable with `rh env set project.name=` |
| `rh env show` | print config as a table + environment notes, validate |
| `rh env set KEY=VALUE ...` | set any key from the §2 schema (`rh env list`) |
| `rh env list` | every settable key, type, choices, help |
| `rh add note <heading> [-m BODY] [--file NAME]` | create/append a note file |
| `rh add literature <DOI-or-heading> [-m BODY]` | append under that DOI/heading in `LITERATURE.md` |
| `rh add layout <heading> [-m BODY]` | append to `OUTPUT_LAYOUT.md` (patterns + our layout) |
| `rh add gaps\|problem\|plan\|status\|manuscript <heading> [-m BODY]` | same for the other artifacts |
| `rh add log --role R --title T [-m BODY]` | §7 log file |
| `rh add task "title" [--id S01] [--phase N] [--owner ROLE] [--state idle\|working\|complete] [--verify CMD] [--deliverable FILE] [--depends-on S01,S02] [--kind build\|spike]` | add a board task |
| `rh search <query> [--max N]` | rg-first local search over `.rh/` + artifacts |
| `rh tasks set <id> <idle\|working\|complete>` | change a task or subtask state |
| `rh tasks [--phase N] [--state S]` | every task + subtask + status, lanes, progress bars |
| `rh status` | header, phase rail, per-phase progress |
| `rh workflow` | display the agent-authored `.rh/workflow.mmd` as ASCII (`--tools`, `--example`, `--png`, `--svg`) |
| `rh phase [0-9]` | show the current phase and its exit gate, or set the phase — **gated**; `--force` records a waiver |
| `rh plan import [--dry-run]` | mirror `PLAN.md` steps into `tasks.json` |
| `rh resume` / `rh -r` | run the orchestrator **in this terminal** — model + thinking level from `agents.roles.orchestrator`, command from `agents.commands.orchestrator`, only `agents.skills` loaded |
| `rh spawn <role> [prompt]` | open another role agent (`literature`, `researcher`, `reviewer`, `critique`, `writer` or your own) with the command written in `.rh/ENV.md`; `--inline`, `--dry-run`, `--prompt-file`, `--split` |
| `rh spawn terminal <cmd>` | open a plain shell terminal in a new pane (shell from `agents.shell`/`$SHELL`, layout from `agents.split`); `--dry-run`, `--split` |
| `rh agents [ROLE] [--write]` | list or show the per-role files in `.rh/agents/` (the only role description — no role info is hardcoded in `rh`); `--write` scaffolds them |
| `rh checklist` | live Orchestrator checklist (SKILL.md §0 rules + phase exit gates) |
| `rh info [FILE]` | what that artifact is for: owner, phase, sections, template, rules (`--json`, `--template`) |
| `rh skill install [--dest DIR] [--force]` | install the bundled skill globally |
| `rh describe [--json]` | the AI map: layout, phases, env keys, artifacts, spawn, budget |

Global flags (before the subcommand): `--root DIR`, `--json`, `--version`.
Every command supports `--json` for agent reads — never parse the pretty UI.

---

## Launching agents (nothing hardcoded)

`rh` does not know any agent CLI's flags. The commands live in `.rh/ENV.md`, and
`rh` substitutes placeholders into them:

```bash
rh env set \
  'agents.roles.orchestrator={"provider":"pi","model":"glm-5","thinking":"high"}' \
  'agents.commands.orchestrator=pi --model {model} --thinking {thinking} --skill {skills} --prompt-file {prompt_file}' \
  'agents.spawn=tmux new-window -n rh-{agent} -c {root} {command}'
rh resume            # → pi --model glm-5 --thinking high --skill research-helper …
rh spawn researcher "read S07 and implement it"
```

Placeholders: `{role} {agent} {prompt} {prompt_file} {root} {name} {provider}
{model} {thinking} {skills}`, plus `{command}` in `agents.spawn`. A template that
omits `{model}`/`{thinking}`/`{skills}` still runs — `rh` warns that your ENV.md
is not being honoured instead of guessing a flag. With no `agents.spawn` the agent
is started as a detached process and its output goes to `.rh/logs/`.
Ready-made scripts and per-role prompt templates live in [`examples/`](examples/README.md).


---

## How it works

```
0 CONFIG → 1 INTAKE → 2 ENVIRONMENT → 3 LITERATURE → 4 PLAN → 5 STATE
        → 6 IMPLEMENT → 7 CRITIQUE → 8 MANUSCRIPT → 9 CLOSE
                            ↑            │
                            └── replan ──┘
```

Each phase has an **exit gate**; `rh phase` refuses to advance past an unmet one.
State lives in plain files, not a database:

```
<project>/
  .rh/                ENV.md, machine mirror, logs, notes, tasks, workflow
  src/                implementation
  results/            every number + the script that produced it
  papers/             downloaded PDFs (kept, never deleted by rh)
  PROBLEM.md          goal, scope, success criteria, falsifier
  OUTPUT_LAYOUT.md    output skeleton + patterns from comparable papers
  PLAN.md             approved steps
  STATUS.md           truth
  LITERATURE.md       paper takes with DOI
  GAPS.md             implementation sourcing + upstream gaps
  MANUSCRIPT.md       write-up
```

`.rh/ENV.md` is the single config source; `.rh/env.json` mirrors it. `rh env set`
rewrites the JSON block and preserves whatever the Orchestrator wrote below it.

---

## The skill (additive)

`src/rh/skills/research-helper/SKILL.md` is the agent-facing half of the project.
It defines the phases, roles, gates, templates, and the ask-before list. The CLI
does not need it; the skill does not need to reimplement the CLI.

```bash
rh skill install
```

What the skill adds:

- **Roles** — Orchestrator (always the current runner), Literature, Researcher,
  Reviewer, Critique, Writer, with a budget mapping for 1–4 parallel agents, and
  `rh spawn <role>` to put one of them to work with the command from `ENV.md`.
- **Gates** — user approves the plan, critique veto, "no result without a file".
- **Templates** — `ENV.md`, `STATUS.md`, `OUTPUT_LAYOUT.md`, `PLAN.md` steps, logs —
  the same descriptions `rh info <FILE>` prints, so an agent can check before writing.
- **Reading discipline** — one layout, a pattern tally, DOI anchors, no paraphrasing
  unread papers.

---

## Development

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest -q
uv build                     # sdist + wheel in dist/
uv tool install dist/*.whl   # smoke-test the installed command
```

Layout:

```
pyproject.toml
src/rh/                 the CLI package
src/rh/skills/          the bundled skill (package data)
tests/                  pytest smoke tests
examples/               agent-facing spawn scripts + role prompt templates
docs/IDEA.md            original design notes
ROADMAP.md              where this is going
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md). Short version: publish to PyPI, harden the CLI,
then add real agent orchestration.

## License

[MIT](LICENSE) © 2026 Hitaishi V
