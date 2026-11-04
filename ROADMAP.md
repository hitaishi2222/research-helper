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

## v0.1 — CLI core ✅

- [x] `.rh/` workspace, `ENV.md` as the single config source + `.rh/env.json` mirror
- [x] `rh init`, `rh env show|set|list`, `rh describe`
- [x] heading-structured artifacts: `add note|literature|layout|gaps|problem|plan|status|manuscript`
- [x] task board: `add task`, `task set|list`, `tasks`, `plan import`
- [x] phase pipeline with gated `rh phase` and waivers
- [x] `rh status` — phase rail, progress bars, per-phase tasks
- [x] `rh search` — rg-first, Python fallback, no indexing
- [x] `rh workflow` — viewer for the agent-authored mermaid DAG
- [x] `rh resume` — open the configured harness with a go-forward prompt
- [x] rich-based UI (tables, bars, banners, phase rail); `--json` everywhere
- [x] environment is interviewed, never auto-probed (`rh env audit` removed)

## v0.2 — Distribution & skill 🚧

- [ ] publish `research-helper` to PyPI (trusted publishing workflow)
- [ ] `uv tool install research-helper` verified on a clean machine
- [x] bundle the skill in the wheel
- [x] `rh skill install` → `~/.agents/skills/research-helper/`
- [ ] add `rh skill install --dest ~/.pi/agent/skills/...` docs to the skill itself
- [x] README, ROADMAP, LICENSE, CI, publish workflow
- [x] pytest smoke tests in CI (3.9 / 3.12 / 3.13)
- [ ] tag `v0.1.0`, cut the first GitHub release
- [ ] screenshot / asciinema of `rh status` and `rh tasks` in the README

## v0.3 — Orchestration

The CLI currently prepares the harness; the agent still opens it by hand.

- [ ] `rh agent spawn <role>` — tmux/herdr/tuios pane, roster recorded in `STATUS.md`
- [ ] `rh agent status` — who is running, on which model, in which pane
- [ ] `rh plan vote` — collect the two planner candidates and the merged diff
- [ ] `rh gate check` — machine-readable gate report for agents (`--json`)
- [ ] `rh log tail` — read the §7 event log without opening files
- [ ] concurrent budget enforcement from `agents.count`

## v0.4 — UX & retrieval

- [ ] `rh status --watch` — live refresh while an agent works
- [ ] `rh search --context N` — show surrounding lines / section anchors
- [ ] `rh tasks --edit` — move a task between lanes interactively
- [ ] `rh add literature` resolves DOI metadata when a resolver is configured
- [ ] shell completions (`rh completion bash|zsh|fish`)
- [ ] `rh doctor` — check the workspace, config, and optional binaries

## v1.0 — Stable

- [ ] freeze the `--json` schema for `describe`, `status`, `tasks`, `env show`
- [ ] deprecation policy for config keys and artifacts
- [ ] end-to-end fixture: a toy project that runs phases 0–9 in CI
- [ ] plugin hook for custom phases / roles
- [ ] docs site with the skill rendered as a readable guide

---

## Non-goals

- A web UI or a hosted service.
- A model gateway — `rh` never calls an LLM.
- A reference manager — it delegates to `zot`, `bibtex`, or the user.
- Replacing the agent. The skill is instructions, not an agent runtime.

---

## How to help

Open an issue with the phase and command you were using, the exact output, and
what you expected. Small, focused PRs are easier to review than rewrites; tests
live in `tests/` and run with `uv run pytest -q`.
