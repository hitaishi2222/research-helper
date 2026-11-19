# Roadmap

`research-helper` is a terminal-first toolkit for running an AI-assisted research
project: a small CLI that owns state and gates, plus a skill that teaches an agent
to use it well. This file is the plan, not a promise; items move as the CLI gets
used on real projects.

---

## Vision

A research project should be reproducible from its files alone:

- every artifact is plain Markdown, every number has a generating script;
- every phase has a hard exit gate the CLI can check;
- an agent can resume from `STATUS.md` and `rh describe` without a transcript;
- the skill adds judgement, the CLI adds structure — neither reimplements the other.

---

## Principles

These hold for every item below. If a change would need an exception, it needs a
discussion first.

1. **No role info is hardcoded in `rh`.** Roles are `.rh/agents/<role>.md` files.
   `rh` only scaffolds an empty file on request; the Orchestrator fills it with
   the user. The launch command per role lives in `.rh/env.json`
   (`agents.commands.<role>`), and `{agent_file}` puts the role file into the
   harness's system-prompt area. **The harness flag itself is never hardcoded**
   (`--system-prompt-file`, `--append-system-prompt-file`, `--system-file`, …):
   the Orchestrator writes it in env.json for the harness in use. There is no
   `if harness == "pi"` branch anywhere in `rh`.
2. **Harness knowledge lives in data, never in Python.** `src/rh/harnesses.json`
   supplies the `rh init` start template (the user picks one), and
   `examples/envs/` carries the same snippets as copy-paste starting points the
   user edits. Python never learns a flag name.
3. **Placeholders are the only extension point.** New ways of passing a value to
   a harness (a list repeated as a flag, file contents inline, …) are new
   placeholders with a clear name, not special cases per harness.
4. **Checks are against disk, never self-reported.** `rh doctor` reads files and binaries and reports what is actually there;
   `rh tasks` / `rh status` print the phase-gate problems the same way.
   An agent saying "done" is not evidence.
5. **The Orchestrator does less, not more.** Every new command must remove a
   manual step the Orchestrator had to do by eye, or it does not ship.
6. **`rh` never calls an LLM, never downloads, never installs.** It displays,
   validates, mirrors, and opens what env.json names. Full stop.

---

## v0.1 — CLI core ✅

- [x] `.rh/` workspace, `.rh/env.json` as the single config source
- [x] `rh init`, `rh env show|set|list`, `rh describe`
- [x] heading-structured artifacts: `add note|literature|layout|gaps|problem|plan|status|manuscript`
- [x] task board: `add task` (with `--subtask`), `tasks`, `tasks set`
- [x] ~~`plan import`~~ removed: the plan is prose, the board is created explicitly
- [x] phase pipeline with gated `rh tasks phase` (no-arg shows the exit gate) and waivers
- [x] `rh status` — phase rail, progress bars, per-phase tasks
- [x] `rh search` — rg-first, Python fallback, no indexing
- [x] `rh workflow` — viewer for the agent-authored mermaid DAG (`bm`-first renderer priority + built-in text fallback)
- [x] `rh resume` — exec the configured agent in the current terminal with a go-forward prompt
- [x] rich-based UI (tables, bars, banners, phase rail); `--json` everywhere
- [x] environment is interviewed, never auto-probed (`rh env audit` removed)

## v0.2 — Distribution & skill 🚧

- [ ] publish `rh-cli` to PyPI (trusted publishing workflow)
- [ ] `uv tool install rh-cli` verified on a clean machine
- [x] bundle the skill in the wheel
- [x] `rh skill install` → `~/.agents/skills/research-helper/`
- [ ] add `rh skill install --dest ~/.pi/agent/skills/...` docs to the skill itself
- [x] README, ROADMAP, LICENSE, CI, publish workflow
- [x] pytest smoke tests in CI (3.11 / 3.12 / 3.13)
- [ ] tag v0.2.1 and cut the GitHub release (v0.1.0–v0.1.7 are tagged; 0.2.x carries the typer port, bounded `STATUS.md` and the board edits, and is not released)
- [ ] screenshot / asciinema of `rh status` and `rh tasks` in the README

## v0.2.1 — Board edits & upgrades ✅

The board could be created and advanced but not corrected, and a CLI upgrade had no
procedure. Both shipped in 0.2.1 (see `CHANGELOG.md`).

- [x] `rh tasks info <id>` — one task or subtask in full: fields, dependencies,
      subtasks, timestamps (`--json`)
- [x] `rh tasks rm <id> [--force]` — drop a task (with its subtasks) or one subtask;
      refuses `working` work and tasks others depend on unless `--force`; ids are
      never renumbered
- [x] `rh tasks reorder <id> (--before|--after) <id>` — move a task inside its phase;
      list order is display order
- [x] hand-editing `.rh/tasks.json` sanctioned for removal and reordering (SKILL.md §1),
      with the invariants written down
- [x] `.rh/ENVIRONMENT.md` records the `rh` version; the checklist flags a missing or
      stale record (`setup-rh-version`)
- [x] `rh init --force` keeps manual checklist ticks and recomputes generated ones;
      the upgrade procedure lives in SKILL.md §10

## v0.3 — Orchestration

The CLI now both prepares and opens the harness: `rh resume` runs the Orchestrator
with the model/thinking/skills from env.json, and `rh spawn <role>` opens any other
role agent with the command written there.

- [x] `rh spawn <role>` — pane via `agents.spawn`, or a detached process with a log
      in `.rh/logs/`; session facts (model, skills, board tasks) appended to the prompt
- [x] `rh info <FILE.md>` — purpose / owner / phase / sections / template per artifact
- [x] `rh resume` honours `agents.roles.orchestrator` (model + thinking) and
      `agents.commands.orchestrator`, loading only `agents.skills`
- [x] `examples/` — starter spawn scripts + per-role prompt templates
- [x] `rh spawn terminal <cmd>` — shell terminal in a new pane (`agents.shell`, `agents.split`)
- [x] `.rh/agents/<role>.md` per-role files + `rh agent list|info|write` (no role
      info hardcoded; `{agent_file}` wires the role file into the CLI system-prompt flag)

### Sidequest tracking (next version)

A tangent is real work, so it goes on the board instead of living in the chat:
whoever notices it records it, timeboxes it, and brings it back to the user.

- [ ] `rh add task --kind sidequest "..."` — a sidequest carries the step it branched
      from, why it came up, a timebox, and its own state; it shows on `rh tasks` under
      that step, so "what are we actually doing" stays honest while the plan waits
- [ ] closing one records an outcome — `kept` (fed back into the step), `dropped`
      (with the one-line reason) or `promoted` (becomes a `PLAN.md` step via
      `rh add task`), plus where its result landed (`results/`, `LITERATURE.md`) —
      so a sidequest never silently becomes the main line or disappears
- [ ] `rh status` counts open sidequests next to the working tasks and flags one that
      blew its timebox; `rh tasks -k sidequest` (or `--kind`) filters them
- [ ] `SKILL.md` rule: do not chase a tangent mid-step — record it, timebox it, ask
      the user, then promote or drop it (rule 11 waivers stay separate)

No new command namespace: sidequests ride the board, the task states and the phase
gates, so `rh tasks` remains the one place work is visible.

## v0.4 — Make the Orchestrator do less

Every item here removes a manual Orchestrator step. Ordered roughly by value.

- [x] `rh doctor` — one command that checks what the Orchestrator currently has
      to eyeball: `agents.shell` exists, `agents.split` valid, every
      `agents.commands.*` has `{agent_file}` (+ `{prompt}`/`{prompt_file}`),
      role file exists for every role with a command, `agents.spawn` template is
      shell-splittable. Checks by name, never probes _what_ to use.
- [x] `examples/envs/pi.sh`, `examples/envs/claude.sh`, `examples/envs/codex.sh` —
      copy-paste ENV snippets per harness (the only place harness flags live).
- [x] Placeholder list-expansion — `{skills}` today expands to one token
      (`research-helper,crw`); harnesses usually want `--skill a --skill b`. Add
      syntax-or-placeholder for repeated expansion, and `{agent_file_contents}` for
      harnesses that want the file inline rather than by path.
- [x] Validate `agents.commands.*` templates at `rh env set` time (warn there,
      not only at spawn time): missing `{agent_file}`, missing `{prompt}`/
      `{prompt_file}`, unsplittable template.
- [x] `rh handoff` — rule 14 as a file: `STATUS.md` + `PLAN.md` + checklist +
      env tail in one pack a fresh session can read without a transcript.
- [ ] Interactive terminal pane for `rh spawn terminal` — open a live shell in the
      pane and run the command in it, instead of one-shot `fish -c '<cmd>'` which
      exits immediately. Needs verification against a real backend before claiming.
- [x] Checklist v2 (content, not just existence): `STATUS.md` has the
      `phase: | step: | updated:` header, every `PLAN.md` step has a `verify:`
      command, every `LITERATURE.md` entry has a DOI, `OUTPUT_LAYOUT.md` has
      exactly one layout.
- [x] `rh agent status` — who is running, on which model, in which pane
      (reads `.rh/logs/` spawn records).
- [x] ~~`rh gate check`~~ folded into `rh tasks` / `rh status` (warnings + the `gate` object in `--json`) in 0.2.
- [x] `rh log tail` — read the §7 event log without opening files.
- [x] Concurrent budget enforcement from `agents.count` — track spawns in
      `.rh/logs/`; refuse the (count+1)th concurrent agent without `--force`.

## v0.5 — Custom agents

A role in `rh` is a file (`.rh/agents/<role>.md`) plus a launch command
(`agents.commands.<role>`) and optionally a model (`agents.roles.<role>`).
Today all three must be set one at a time, and only the starter roles are
scaffolded by `rh agent write`.

- [ ] `rh agent new <role>` — create a custom role in one step: ask for the
      one-line purpose, scaffold `.rh/agents/<role>.md` with it, then record
      `agents.commands.<role>` (copy `agents.commands.default`, or ask for the
      flags with the user) and `agents.roles.<role>.model` in `.rh/env.json`. Refuse
      to overwrite an existing role file without `--force` (archive first).
- [ ] `rh agent edit <role>` — open the role file, and show which ENV keys
      belong to that role (command, model, thinking) so they are edited together.
- [ ] `rh agent rm <role>` — archive the role file to `.rh/.bak/` and remove
      `agents.commands.<role>` / `agents.roles.<role>`, refusing while that role
      still owns open tasks.
- [ ] `rh agent write` scaffolds every role that has a command or a model in
      env.json, not only the starter six (custom roles included).
- [ ] `rh doctor` checks custom roles the same way as starter roles: file
      present, command splittable, `{agent_file}` + `{prompt}` wired, model set —
      and names any role that appears in one place but not the others.
- [ ] `rh describe --json` lists each role with its file path, model and
      command source, so an Orchestrator can see the roster without reading env.json.

## v0.5 — UX & retrieval

- [ ] `rh status --watch` — live refresh while an agent works
- [ ] `rh search --context N` — show surrounding lines / section anchors
- [ ] `rh tasks --edit` — move a task between lanes interactively
      (non-interactive ordering already ships as `rh tasks reorder`)
- [ ] `rh add literature` resolves DOI metadata when a resolver is configured
- [ ] shell completions (`rh completion bash|zsh|fish`)
- [ ] docs site with the skill rendered as a readable guide

## v1.0 — Stable

- [ ] freeze the `--json` schema for `describe`, `status`, `tasks`, `env show`
- [ ] deprecation policy for config keys and artifacts
- [ ] end-to-end fixture: a toy project that runs phases 0–9 in CI
- [ ] plugin hook for custom phases / roles
- [ ] drop the hardcoded role/phase lists that still live in `tasks.PHASES`,
      `PHASE_EXIT`, `cli.REQUIRED_BEFORE`, `artifacts.ARTIFACTS`, and
      `config.ENV_SCHEMA` `agents.roles.*` entries — phases and roles become
      data files (`.rh/phases.md`, `.rh/agents/`), validated the same way env.json is

---

## Non-goals (explicit)

- A web UI or a hosted service.
- A model gateway — `rh` never calls an LLM.
- A reference manager — it delegates to `zot`, `bibtex`, or the user.
- Replacing the agent. The skill is instructions, not an agent runtime.
- **A harness registry / adapter layer.** `rh` does not learn flag names per
  harness. `examples/envs/` / `harnesses.json` + placeholders are the whole integration
  surface. If a harness needs a flag `rh` cannot express as a placeholder, the
  answer is a new placeholder, not a harness branch.
- **Auto-probing the machine** ("which harness is installed, which shell, which
  shell layout"). `rh doctor` verifies _named_ things exist; it never decides
  what the user should use. A binary on PATH is not a project decision.

---

## How to help

Open an issue with the phase and command you were using, the exact output, and
what you expected. Small, focused PRs are easier to review than rewrites; tests
live in `tests/` and run with `uv sync --extra dev` then `uv run pytest -q` (plus
`uv run pyflakes src/rh tests` — the same gate CI runs).
