# research-helper

**`rh` — orchestrate an AI research project end to end from the terminal.**

[![CI](https://github.com/hitaishi2222/research-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/hitaishi2222/research-helper/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/research-helper.svg)](https://pypi.org/project/research-helper/)
[![Python](https://img.shields.io/pypi/pyversions/research-helper.svg)](https://pypi.org/project/research-helper/)
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
# once published to PyPI
uv tool install research-helper

# or straight from git
uv tool install git+https://github.com/hitaishi2222/research-helper

# or from a clone
git clone https://github.com/hitaishi2222/research-helper
cd research-helper
uv tool install .
```

`pipx install research-helper` and `pip install --user research-helper` work too.
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
rh init --slug my-project
rh env set agents.count=2 agents.backend=tmux \
  literature.search=crw project.git=true
rh env show                 # config as a table, validated
rh phase 4                  # gated: refuses to skip unmet exits
rh describe                 # the map an agent reads
```

The Orchestrator (your agent) interviews you for the environment and writes the
`## Environment` section of `ENV.md`; `rh` never probes or auto-fills binaries.
A tool on `PATH` does not mean this project should use it.

---

## Commands

| Command | What it does |
|---|---|
| `rh init [--slug NAME] [--clean]` | create the `.rh/` workspace |
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
| `rh task set <id> <idle\|working\|complete>` | change a task state |
| `rh task list [--phase N] [--state S]` | filter the board |
| `rh tasks [--phase N]` | lanes + progress bars + table |
| `rh status` | header, phase rail, per-phase progress |
| `rh workflow` | display the agent-authored `.rh/workflow.mmd` as ASCII (`--tools`, `--example`, `--png`, `--svg`) |
| `rh phase <0-9>` | set the current phase — **gated**; `--force` records a waiver |
| `rh plan import [--dry-run]` | mirror `PLAN.md` steps into `tasks.json` |
| `rh resume` / `rh -r` | open the agent harness with a go-forward prompt |
| `rh skill install [--dest DIR] [--force]` | install the bundled skill globally |
| `rh describe [--json]` | the AI map: layout, phases, env keys, budget |

Global flags (before the subcommand): `--root DIR`, `--json`, `--version`.
Every command supports `--json` for agent reads — never parse the pretty UI.

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
  .rh/                machine mirror + logs, notes, managed PDFs, tasks
  src/                implementation
  results/            every number + the script that produced it
  papers/             unmanaged PDFs
  ENV.md              config block + Orchestrator-written environment notes
  PROBLEM.md          goal, scope, success criteria, falsifier
  OUTPUT_LAYOUT.md    output skeleton + patterns from comparable papers
  PLAN.md             approved steps
  STATUS.md           truth
  LITERATURE.md       paper takes with DOI
  GAPS.md             implementation sourcing + upstream gaps
  MANUSCRIPT.md       write-up
```

`ENV.md` is the single config source; `.rh/env.json` mirrors it. `rh env set`
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

- **Roles** — Orchestrator, Literature, Researcher, Reviewer, Critique, Writer,
  with a budget mapping for 1–4 agents.
- **Gates** — user approves the plan, critique veto, "no result without a file".
- **Templates** — `ENV.md`, `STATUS.md`, `OUTPUT_LAYOUT.md`, `PLAN.md` steps, logs.
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
docs/IDEA.md            original design notes
ROADMAP.md              where this is going
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md). Short version: publish to PyPI, harden the CLI,
then add real agent orchestration.

## License

[MIT](LICENSE) © 2026 Hitaishi V
