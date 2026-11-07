# Changelog

All notable changes to `rh` (distribution `rh-cli`). Format follows
[Keep a Changelog](https://keepachangelog.com/1.1.0/); this project uses
[semantic versioning](https://semver.org/).

## [0.1.3] — 2026-11-07

Fixes from the second test pass: one config file, a real Orchestrator to-do list
at init, role files at init, and a silent `rh resume`.

### Changed (breaking)

- **`.rh/ENV.md` is gone.** `.rh/env.json` is the single config file: `rh env set`
  writes it, `rh env show` reads it, and nothing wraps JSON in Markdown anymore.
  The Orchestrator's free-form environment notes moved to the phase-2 artifact
  `.rh/ENVIRONMENT.md`, so config and prose never share a file. A legacy
  `.rh/ENV.md` (or a root `ENV.md`) is folded into `env.json` +
  `ENVIRONMENT.md` on first read and the Markdown is archived to
  `.rh/.bak/<timestamp>/` — never deleted.
- `rh env show` prints the config plus `.rh/ENVIRONMENT.md`; `rh doctor` checks
  `env.json` (`env-json` instead of `env-md`).
- Phase gates, `rh info`, `rh search`, `rh handoff` and `rh workflow` name
  `.rh/ENVIRONMENT.md` / `.rh/env.json`.
- **`rh spawn-terminal` is gone.** `rh spawn terminal <cmd>` is the only form
  (the extra alias is no longer registered or listed).
- **`rh checklist` is gone.** The generated `.rh/CHECKLIST.md` is the checklist;
  the orchestrator role file (its additional system prompt) points the agent at
  it, so there is no separate command to remember. `rh init` still writes the
  file, and `rh handoff` still packs it.

### Added

- **`rh init` creates the Orchestrator's checklist** at `.rh/CHECKLIST.md`: setup
  tasks (missing environment values to ask about, launch commands to wire, role
  files to tailor, `workflow.mmd` after the plan) followed by every phase exit
  gate and the SKILL.md §0 rules, each checked against disk. The orchestrator
  role file tells the agent to read it first, so no CLI command is involved.
- **`rh init` creates the default role files** (`.rh/agents/orchestrator.md` +
  the starter roles) instead of leaving `rh agents --write` as a hidden step.
  The orchestrator file carries the actual contract (owns/may/may-not, the
  checklist, rules 9/12/13), so a fresh session knows its job immediately.
- **A rich `rh init` questionnaire**: key hints once, then one compact question
  frame redrawn in place (no full-screen clear). `rich.prompt` validates the
  answer, numbered options list the agent CLIs, shells and pane backends that
  are actually on PATH (`other` types one that is not), and Enter keeps the
  default, Tab submits and moves on (readline/libedit binding), `s` skips the
  key, `q` finishes with the answers so far, Ctrl-C skips the rest. Skills are
  not asked here — that is the Orchestrator's job (`rh env set agents.skills=`).
- **Harness start templates** (`src/rh/harnesses.json`, data only): the init
  questionnaire's harness answer fills `agents.cli` and
  `agents.commands.orchestrator|default` where still blank, so `rh resume` works
  from a fresh init. Existing commands are never overwritten.

### Fixed

- **The `pi` harness template used flags `pi` does not have.** `--prompt-file`
  does not exist, and `--prompt-template` is not a prompt either — it registers a
  `/command` and sends no message, so `rh resume` opened `pi` with the prompt
  only loaded as a slash command. The launch template now passes the prompt
  **positionally** (`{prompt}`), and the role file goes in through
  `--append-system-prompt {agent_file}` — never `--system-prompt`, which would
  replace `pi`'s own system prompt. Same fix in `examples/envs/pi.sh`,
  `examples/configure-env.sh`, README and the bundled SKILL.md.
- **The orchestrator is no longer handed a skill restriction.** Its launch
  template carries no `--skill`: the Orchestrator must see every skill to decide
  which one each spawned agent is assigned. `rh` also stopped warning that
  "skills are not restricted at the CLI" for the orchestrator role.
- **Bad CLI usage falls back to the full `--help`** and nothing else — no
  `error: invalid choice …` line (exit 2). `rh --help` and `rh --version` exit 0.
- **`rh resume` no longer prints the prompt** before opening the harness. Its
  first message is the skill read (“Load the `research-helper` skill …”), and it
  opens the harness with `.rh/agents/orchestrator.md` wired in through
  `{agent_file}`. If a hand-written template omits `{agent_file}`, the role file
  is prepended to the prompt instead, so the Orchestrator knows its job from the
  get go.

## [0.1.2] — 2026-11-07

Delegation, config honesty and artifact documentation (from the ISSUES list).

### Added

- **`rh spawn <role> [prompt]`** — open one role agent (`literature`,
  `researcher`, `reviewer`, `critique`, `writer`, or any role you define) with
  the launch command written in `.rh/ENV.md`. It passes the role file
  `.rh/agents/<role>.md` and appends the session facts (model, skills, its board
  tasks with deliverable + verify, the current phase) and opens it through `agents.spawn` (tmux/herdr/tuios pane) or as a
  detached process logging to `.rh/logs/`. Flags: `--prompt`, `--prompt-file`,
  `--inline`, `--dry-run`, `--json`.
- **`rh info [FILE.md]`** — one clean description per artifact: purpose, owner,
  phase, required sections, template and the rules that bite there. Accepts
  `status`, `STATUS`, `.rh/STATUS.md`; `--template` prints just the template,
  `--json` for agents, no argument lists every artifact.
- **`agents.commands.<role>`** and **`agents.spawn`** config keys: `rh` hardcodes
  no agent flag. Templates take `{model}` `{thinking}` `{skills}` `{prompt}`
  `{prompt_file}` `{root}` `{slug}` `{role}` (and `{command}` in
  `agents.spawn`); a placeholder with an empty value drops the flag that
  introduced it. Any role name is settable: `rh env set
  agents.commands.<role>=…`, `rh env set agents.roles.<role>.model=…`.
- **`thinking`** level per role: `agents.roles.<role>` now takes
  `{provider, model, thinking}`, shown as `pi/glm-5 (thinking: high)`.
- `rh resume --prompt-file FILE` for this session's instructions.
- `examples/` — starter scripts (`configure-env.sh`, `spawn-researcher.sh`,
  `spawn-critique.sh`) and per-role prompt templates with `{{PLACEHOLDER}}`s, so
  an agent (or a user) can see how commands, roles, tasks and prompts fit.

- **`rh spawn terminal <command>`** — open a plain shell terminal (not an agent) in a
  new pane, e.g. `rh spawn terminal 'pytest -q'`. Shell from `agents.shell` in
  `.rh/ENV.md` (else `$SHELL`, else `sh`); pane layout from `agents.split`
  (`vertical` | `horizontal` | `window` — new workspace/window), asked of the user
  when unset. `--dry-run`, `--split`, `--json`.
- **Per-role agent files** — `.rh/agents/<role>.md` is the *only* role
  description in the system: no role info is hardcoded in `rh`. `rh agents
  [ROLE] [--write]` lists/shows/scaffolds them. The Orchestrator edits them
  with user approval and records the launch command per role in `.rh/ENV.md`
  (`agents.commands.<role>`), which `rh spawn` uses exactly; the `{agent_file}`
  placeholder puts the role file into the harness's system-prompt area
  (e.g. `--system-prompt-file {agent_file}` or the harness equivalent).
- **`rh checklist`** — the Orchestrator's live checklist: every SKILL.md §0
  non-negotiable plus each phase's exit gate, checked against the project on
  disk (via `rh phase` gates), never self-reported. `--json` for agents.
  v2 adds content checks (STATUS header, PLAN `verify:` lines, DOI per
  literature entry, exactly one layout).
- **`rh doctor`** — verifies what ENV.md names: shell on PATH, `agents.split`
  valid, every `agents.commands.<role>` splittable with `{agent_file}` +
  `{prompt}`, role files present, backend binary present. Checks by name only.
- **`rh agent status`, `rh gate check`, `rh log tail`, `rh handoff`** — spawn
  records in `.rh/logs/spawns.jsonl`, machine-readable gate report, §7 log
  reader, fresh-session pack (rule 14).
- **`agents.count` budget enforcement** — `rh spawn` refuses the (count+1)th
  concurrent agent without `--force` (waiver → STATUS.md, rule 11).
- **List/content placeholders** — `{skills:list}` expands to one token per
  skill; `{agent_file_contents}` puts the role file contents inline.
- **`{agent_file}` at `rh env set` time** — missing `{agent_file}` or
  `{prompt}` in a command template is a config warning immediately, not only
  at spawn.
- **`examples/envs/{pi,claude,codex}.sh`** — the only place harness flags live.
- **`rh init` takes no project name.** It initializes the directory you run it
  in and names the project after that directory (a label only — no directory is
  created, no `--slug` flag). Rename it with `rh env set project.name=...`; the
  questionnaire may override it. `project.slug` is read as `project.name` and
  migrated on the next write.
- **`rh init` is non-destructive.** Existing `ENV.md`/`tasks.json` block init
  unless `--force`, which archives a *copy* to `.rh/.bak/<timestamp>/` first
  (originals and their environment notes stay put). `--clean` archives the whole
  `.rh/` tree — event logs and notes included — before recreating it, so nothing
  is deleted that was not archived. Backups never collide inside one second.
  `--dry-run` writes nothing. `PLAN.md` is never touched by init.
- **`rh init` questionnaire.** Few skippable questions (slug, count, backend,
  CLI, shell, split, skills, harness snippet). Defaults are read from the
  ENV.md already on disk, so Enter keeps the project's settings instead of
  resetting them; `s` really skips (the key is not written) and `Ctrl-C` ends
  the questionnaire; skipped questions become the Orchestrator's job. The
  overwrite guard runs *before* the questions, so a configured project is not
  quizzed and then refused. `--non-interactive` / `--json` skip it entirely.
- **`PLAN.md` guard.** Pre-existing `PLAN.md` is adopted, never overwritten:
  `rh` reads it and mirrors it with `rh plan import`; forced writes archive
  to `.rh/.bak/` first. `rh plan import` stays read-only for `PLAN.md`.

### Changed

- **`rh resume` now starts the session `.rh/ENV.md` describes**: command from
  `agents.commands.orchestrator`, model + thinking level from
  `agents.roles.orchestrator`, and only the `agents.skills` list loaded (fewer
  skills, smaller context). It prints the model, skills and the exact command
  before exec'ing, and `--dry-run`/`--json` return them without spawning. When
  the command template omits `{model}`, `{thinking}` or `{skills}`, `rh` warns
  that the ENV.md settings are not being honoured instead of guessing a flag.
- `rh resume`/`rh spawn` prompts list the allowed skills explicitly and point at
  `rh info <FILE>` and `rh spawn` for delegation.
- The `agents.cli` fallback survives only for projects with no command template:
  `rh resume` asks for a binary, persists it and warns that model/thinking/skills
  are not passed.

### Fixed

- **`DEFAULT_ENV` was mutated by `config.load_env()`.** `deep_merge` shared nested
  dicts with the defaults, so any `env set` on a key missing from ENV.md edited
  the process-wide defaults for everything that ran afterwards. Now deep-copied.
- **`rh init` skip wrote `"s"`.** `s` was stored as the value: `project.name="s"`,
  `agents.backend="s"`, `skills=["s"]` — an invalid config. Skip is now absent.
- **`rh init --clean` deleted without archiving** (and `--clean --force` archived
  nothing, since the removal ran first). The archive now happens before any
  deletion, covers the whole `.rh/` tree, and keeps the archives of earlier
  cleans.
- **`rh checklist` header check** missed a bold header (`phase: **6 IMPLEMENT**`)
  and claimed to verify `step:`/`updated:` while only testing `phase:`; it now
  names the missing part. Phases after the current one report `later` instead of
  counting as pending.
- **`rh doctor`** now also checks the role file for every role that has a model
  configured, not only roles with a command template.
- **`--dry-run` wrote prompt files** (`spawn-*.md`, `resume-prompt.md`). It now
  writes nothing.

- **Duplicate progress bars.** `rh status` printed the same completion twice (a
  `Progress:` line plus the bar under the phase rail) and repeated the counts in
  an openspec-style lane block, where idle tasks also rendered as `[x]`. Now:
  one rail, one progress line, then the per-phase breakdown.
- `rh tasks` printed a second bar for subtasks; the subtask count is now a line
  and each task row already carries `[done/total subtasks]`.
- `rh describe` reports the artifacts, `rh info`, and the spawn commands/
  placeholders so an agent can find them without reading the source.

## [0.1.1] — 2026-11-04

Config, orchestration and task-board cleanup driven by real-project use
(`jmcc_cepo4_gcn`).

- **`agents.skills`** config key (list): the skills every spawned agent must read
  before touching the project. Defaults to `["research-helper"]`, settable with
  `rh env set agents.skills=research-helper,crw`.
- **Built-in ASCII workflow view.** When no external ASCII renderer is installed,
  `rh workflow` renders the agent-authored `.rh/workflow.mmd` itself: nodes
  grouped by subgraph with state glyphs (done / current / gate / conditional /
  todo) plus the edge list, instead of ending in "no renderer".
- Renderer **priority list** shared by `rh workflow`: `bm` (beautiful-mermaid
  CLI, also found as `beautiful-mermaid`) first, then `mermaid-ascii`,
  `mermansi`, `mermaid2term`, `merx`, `ma`, then the built-in view. For
  `--svg`/`--png`: `bm`, `mmdr`, `mmdc`.
- `rh tasks set <id> <state>` (task **and** subtask ids); `rh add task --subtask`
  to record subtasks at creation time.
- `rh tasks` now prints every subtask with its own state, not just a count.
- `rh phase` with no argument shows the current phase, its exit gate and whether
  it is met, plus the next phase.

### Changed

- **`ENV.md` now lives at `.rh/ENV.md`**, never at the project root. A root
  `ENV.md` or a `.rh/ENV.md` symlink pointing at one is migrated automatically
  on first read/write.
- **Downloaded papers stay in `./papers/`.** The CLI no longer creates or reads
  `.rh/papers/` and never deletes a paper.
- **`rh resume` runs the agent in the terminal the command was called from**
  (`exec` in place, after printing the project path) instead of opening a new
  tmux window / herdr tab / tuios window. Spawning extra agents is the
  Orchestrator's job via `agents.backend`.
- `rh resume` refuses to start unless the resolved root has `.rh/` and a
  parseable `.rh/ENV.md`, and prints the path it is about to use.
- `rh status` reports progress only: per-phase bars with the working ids. Agent
  configuration is no longer printed (or emitted in `--json`), and task/subtask
  detail points to `rh tasks`.
- `rh workflow --tools` renders a proper table (renderer, state, binary aliases,
  install hint) instead of one unreadable line.
- `rh plan import` treats `PLAN.md` as truth: existing ids get their title,
  owner, deliverable, verify, kind, risk, timebox and dependencies refreshed
  (state and subtasks are kept), and it reports `+ added` / `~ updated` with the
  changed fields.
- Malformed `phase` values in `.rh/tasks.json` (e.g. `"6 IMPLEMENT"`) are
  normalised on load, so mixed task data no longer crashes `rh status`/`rh tasks`.
- Task dependency parsing ignores the `none` placeholder.
- `rh init` output reflects the new layout (`.rh/ENV.md`, root `papers/`, no
  `.rh/papers/`).

### Fixed

- `rh workflow` did not use an installed ASCII renderer at all when its output
  could be wide: the early "no tools" return skipped the fallback and the `bm`
  invocation used a non-existent `--padding-y` flag. Both fixed; output wider
  than the terminal falls back to the built-in view with the reason shown.
- `rh plan import` did not recognise suffixed step ids such as **`S04b`**, and
  never refreshed titles, so retired titles stayed on the board.
- `rh plan import` lost newly added steps instead of saving them.
- `rh task …` is removed; `rh tasks` is the single board command.

### Docs

- `SKILL.md` rewritten around the Orchestrator: it is always the current runner;
  ask the user how many **parallel agents** they want for planning and research;
  the two planners argue with each other and hand a finalized plan to the
  Orchestrator; the single-agent case hands the user to a fresh session at
  gate-heavy steps; spawned agents are closed when their job is done; the project
  path is verified before any agent is opened; `STATUS.md` is updated by the
  Orchestrator itself; `.rh/ENV.md` and `./papers/` locations updated.
- `README.md` / `ROADMAP.md` updated for the command and layout changes.

## [0.1.0] — 2026-11-04

First published release (`rh-cli` on PyPI; the earlier PyPI name was confusable
with `researchhelper`).

- `.rh/` workspace, config block as the single config source + `.rh/env.json`
  mirror, `rh env show|set|list`, `rh describe`, `rh init`.
- Heading-structured artifacts (`rh add note|literature|layout|gaps|problem|
  plan|status|manuscript|log|task`) and rg-first `rh search`.
- Gated phase pipeline (`rh phase`) with waivers, `rh status`, `rh tasks`,
  `rh plan import`.
- `rh workflow` viewer for the agent-authored `.rh/workflow.mmd`.
- `rh resume` / `rh -r`, `rh skill install`, bundled `research-helper` skill.
- rich-based UI with `--json` on every command.

[0.1.3]: https://github.com/hitaishi2222/research-helper/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/hitaishi2222/research-helper/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/hitaishi2222/research-helper/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hitaishi2222/research-helper/releases/tag/v0.1.0
