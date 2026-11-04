# Changelog

All notable changes to `rh` (distribution `rh-cli`). Format follows
[Keep a Changelog](https://keepachangelog.com/1.1.0/); this project uses
[semantic versioning](https://semver.org/).

## [0.1.1] — 2026-11-04

Config, orchestration and task-board cleanup driven by real-project use
(`jmcc_cepo4_gcn`).

### Added

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

[0.1.1]: https://github.com/hitaishi2222/research-helper/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/hitaishi2222/research-helper/releases/tag/v0.1.0
