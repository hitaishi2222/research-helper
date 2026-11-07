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
   the user. The launch command per role lives in `.rh/ENV.md`
   (`agents.commands.<role>`), and `{agent_file}` puts the role file into the
   harness's system-prompt area. **The harness flag itself is never hardcoded**
   (`--system-prompt-file`, `--append-system-prompt-file`, `--system-file`, …):
   the Orchestrator writes it in ENV.md for the harness in use. There is no
   `if harness == "pi"` branch anywhere in `rh`.
2. **Harness knowledge lives in `examples/envs/` only.** Per-harness ENV snippets
   (`pi.sh`, `claude.sh`, `codex.sh`, …) are copy-paste starting points the user
   edits. Python never learns a flag name.
3. **Placeholders are the only extension point.** New ways of passing a value to
   a harness (a list repeated as a flag, file contents inline, …) are new
   placeholders with a clear name, not special cases per harness.
4. **Checks are against disk, never self-reported.** `rh checklist`, `rh doctor`,
   and `rh gate check` read files and binaries and report what is actually there.
   An agent saying "done" is not evidence.
5. **The Orchestrator does less, not more.** Every new command must remove a
   manual step the Orchestrator had to do by eye, or it does not ship.
6. **`rh` never calls an LLM, never downloads, never installs.** It displays,
   validates, mirrors, and opens what ENV.md names. Full stop.

---

## v0.1 — CLI core ✅

- [x] `.rh/` workspace, `.rh/ENV.md` as the single config source + `.rh/env.json` mirror
- [x] `rh init`, `rh env show|set|list`, `rh describe`
- [x] heading-structured artifacts: `add note|literature|layout|gaps|problem|plan|status|manuscript`
- [x] task board: `add task`, `tasks`, `tasks set`, `plan import` (titles refresh)
- [x] phase pipeline with gated `rh phase` (no-arg shows the exit gate) and waivers
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
- [x] pytest smoke tests in CI (3.9 / 3.12 / 3.13)
- [ ] tag `v0.1.0`, cut the first GitHub release
- [ ] screenshot / asciinema of `rh status` and `rh tasks` in the README

## v0.3 — Orchestration

The CLI now both prepares and opens the harness: `rh resume` runs the Orchestrator
with the model/thinking/skills from ENV.md, and `rh spawn <role>` opens any other
role agent with the command written there.

- [x] `rh spawn <role>` — pane via `agents.spawn`, or a detached process with a log
  in `.rh/logs/`; session facts (model, skills, board tasks) appended to the prompt
- [x] `rh info <FILE.md>` — purpose / owner / phase / sections / template per artifact
- [x] `rh resume` honours `agents.roles.orchestrator` (model + thinking) and
      `agents.commands.orchestrator`, loading only `agents.skills`
- [x] `examples/` — starter spawn scripts + per-role prompt templates
- [x] `rh spawn terminal <cmd>` — shell terminal in a new pane (`agents.shell`, `agents.split`)
- [x] `.rh/agents/<role>.md` per-role files + `rh agents [ROLE] [--write]` (no role
  info hardcoded; `{agent_file}` wires the role file into the CLI system-prompt flag)
- [x] `rh checklist` — live SKILL.md §0 + phase-exit checklist

## v0.4 — Make the Orchestrator do less

Every item here removes a manual Orchestrator step. Ordered roughly by value.

- [x] `rh doctor` — one command that checks what the Orchestrator currently has
  to eyeball: `agents.shell` exists, `agents.split` valid, every
  `agents.commands.*` has `{agent_file}` (+ `{prompt}`/`{prompt_file}`),
  role file exists for every role with a command, `agents.spawn` template is
  shell-splittable. Checks by name, never probes *what* to use.
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
- [x] `rh gate check` — machine-readable gate report for agents (`--json`).
- [x] `rh log tail` — read the §7 event log without opening files.
- [x] Concurrent budget enforcement from `agents.count` — track spawns in
  `.rh/logs/`; refuse the (count+1)th concurrent agent without `--force`.

## v0.5 — UX & retrieval

- [ ] `rh status --watch` — live refresh while an agent works
- [ ] `rh search --context N` — show surrounding lines / section anchors
- [ ] `rh tasks --edit` — move a task between lanes interactively
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
  data files (`.rh/phases.md`, `.rh/agents/`), validated the same way ENV.md is

---

## Non-goals (explicit)

- A web UI or a hosted service.
- A model gateway — `rh` never calls an LLM.
- A reference manager — it delegates to `zot`, `bibtex`, or the user.
- Replacing the agent. The skill is instructions, not an agent runtime.
- **A harness registry / adapter layer.** `rh` does not learn flag names per
  harness. `examples/envs/` + ENV.md placeholders are the whole integration
  surface. If a harness needs a flag `rh` cannot express as a placeholder, the
  answer is a new placeholder, not a harness branch.
- **Auto-probing the machine** ("which harness is installed, which shell, which
  shell layout"). `rh doctor` verifies *named* things exist; it never decides
  what the user should use. A binary on PATH is not a project decision.

---

## How to help

Open an issue with the phase and command you were using, the exact output, and
what you expected. Small, focused PRs are easier to review than rewrites; tests
live in `tests/` and run with `uv run pytest -q`.
