---
name: research-helper
description: "Orchestrate a research project end to end: intake, environment, literature survey, planning, implementation with review, critique gate, manuscript, close. Driven by `.rh/env.json` (agent count, per-role models, launch commands, literature tools, gates) and the environment record (`.rh/ENVIRONMENT.md`, or `project.environment` in the config). Use when the user wants to scope a research question, survey literature, build and test an experiment, or write it up."
---

# Research helper

A research project runs as a pipeline of phases with hard gates. This file states the phases,
who owns each artifact, what must be true to leave a phase, and what to ask the user instead of
deciding alone.

Nothing here is advice. If a rule cannot be followed, stop and ask.

## 0. Non-negotiables

1. **You are the Orchestrator.** Whoever loads this skill is the head, and stays the head: do not
   hand the role to a spawned agent. You alone ask the user questions, merge the plan and update
   `STATUS.md`.
2. **Never choose a model.** Agent count and every role's model live in `.rh/env.json`. To change
   them, the user asks you to run `rh env set`.
3. **Ask before every state-changing action.** See §6.
4. **No empty placeholder files.** An artifact appears when it first has content.
5. **No silent scope change.** Anything outside an approved `PLAN.md` needs approval first.
6. **Never substitute a reference.** For a paywalled paper, ask the user for the PDF by DOI.
7. **No result without a file.** A number that is not in `results/` with the script that produced
   it does not exist and may not appear in `MANUSCRIPT.md`.
8. **"Done" requires proof.** Tests green, plan steps checked, Critique has no open blocking
   question. A claim without evidence is rework.
9. **`STATUS.md` is the truth, and it is your own work.** Update it after every step and before
   every question to the user. Never delegate that update.
10. **Re-read `.rh/env.json` and the environment record at the start of every phase.** Never cache
    them: a version recorded in phase 2 may have moved.
11. **The user may waive a rule.** Name the waiver in `STATUS.md` history with the rule number, and
    in the manuscript's limitations. Without one, an unmet rule stops the phase.
12. **Verify the project path before opening an agent.** Resolve the root, confirm `.rh/` and
    `.rh/env.json` are there, state the path to the user, then spawn. Never open an agent in
    `$HOME`, a parent directory, or a neighbouring project.
13. **Close what you opened.** When a spawned agent finishes, close its pane, window or tab and
    record the close in `STATUS.md`. Agents left running spend the user's credits.
14. **One agent means fresh eyes come from a new session.** With `agents.count = 1` nothing
    independent reviews the work. After a gate-heavy step (plan approved, implementation done,
    critique answered), tell the user to continue in a new session and hand over `STATUS.md` and
    `PLAN.md` instead of stretching this transcript.

## 1. Where things live

All state lives in one project root, chosen by the user in phase 0. The skill directory holds no
config and no project data.

```
<project root>/
  .rh/env.json         the config (§2), written by `rh env set`      Orchestrator   phase 0
  .rh/ENVIRONMENT.md   tools and versions the user named             Orchestrator   phase 2
  .rh/CHECKLIST.md     generated to-do list: setup, gates, rules     Orchestrator   phase 0+
  PROBLEM.md           goal, scope, success criteria, falsifier      Orchestrator   phase 1
  PLAN.md              approved step list                            Planners or user  phase 4
  STATUS.md            state, roster, blockers, open questions       Orchestrator   phase 5+
  LITERATURE.md        what we took from each paper, with citations   Literature    phase 3
  OUTPUT_LAYOUT.md     output skeleton plus the patterns comparable
                       papers follow (sections, equations, figures)   Literature    phase 3+
  GAPS.md              implementation sourcing and upstream gaps     Literature, Researcher  phase 3+
  MANUSCRIPT.md        the write-up                                  Writer         phase 8
  papers/              downloaded PDFs, named <firstauthor><year>_<slug>.pdf
                       keep them: never delete or move a downloaded paper
  .rh/logs/            event logs (§7)
  .rh/agents/<role>.md the role itself. `rh init` writes the six starter roles, each carrying
                       its §5 scope; narrow a role file with the user, and wire it into the
                       CLI's system-prompt area in `agents.commands.<role>`.
  src/                 implementation
  results/             every produced number, table and figure, with the script that made it
```

`rh` keeps the artifact markdown under `.rh/` when `.rh/` exists, and at the root otherwise. Both
locations work; use the one `rh info <FILE.md>` reports.

Create an artifact on first write, in the phase that needs it. If the user agrees to skip a phase,
its artifact never exists. That is allowed; an empty file is not. **An existing `PLAN.md` is
adopted, never overwritten:** read it, ask the user (adopt, diff, or skip), then create its tasks
with `rh add task`. No parser reads a plan. A forced write first archives the old file to
`.rh/.bak/<timestamp>/`.

Before writing any artifact, run `rh info <FILE.md>`. It prints the purpose, owner, phase, required
sections, template and the rules that apply, so no agent has to guess.

The `rh` CLI (§10) keeps its machine state under `.rh/`: `env.json`, `ENVIRONMENT.md`,
`CHECKLIST.md`, `tasks.json`, `agents/`, `logs/`, `notes/`, `workflow.mmd`. The artifacts above
remain the truth. `.rh/` is derived display state, with two exceptions: `rh env set` writes
`env.json`, and `rh` never deletes a downloaded paper.

## 2. `.rh/env.json`, the config

It is the only config. Write it with `rh env set KEY=VALUE`; read it back with `rh env show`. Do not
hand-edit the JSON silently: propose a diff, get approval, then set it (or edit the file and say
so). Environment notes are a separate artifact, `.rh/ENVIRONMENT.md` (§3 phase 2). Config and prose
never share a file. If the file is missing or unparseable, run phase 0.

The block below is the schema `rh env set` fills in. Comments are for this document only; the file
is plain JSON.

```jsonc
{
  "agents": {
    "count": 1,            // agents that may run at once, 1..4
    "backend": "tmux",     // tmux | herdr | tuios | none (none = serial, no panes)
    "cli": "pi",           // the agent binary this project runs
    "skills": ["research-helper"],  // skills every spawned agent must read first
    "roles": {
      // provider+model(+thinking) per role. The orchestrator slot is the model
      // actually running this session.
      "orchestrator": { "provider": "pi", "model": "<model>", "thinking": "high" },
      "literature": {}, "researcher": {}, "reviewer": {}, "critique": {}, "writer": {}
    },
    "commands": {
      // How an agent CLI is STARTED. Ask for it; never invent it. rh substitutes the
      // placeholders {model} {thinking} {skills} {prompt} {prompt_file} {agent_file}
      // {root} {name} {role}.
      // {agent_file} is .rh/agents/<role>.md: put it in the harness's system-prompt
      // APPEND flag (pi: --append-system-prompt {agent_file}; claude:
      // --append-system-prompt-file {agent_file}; others: their equivalent). Never a
      // flag that REPLACES the system prompt, or the session loses its harness rules.
      // rh never hardcodes the flag name.
      // The prompt goes positionally ({prompt}). Use {prompt_file} only for a CLI that
      // has such a flag. pi has none: --prompt-template registers a /command and sends
      // no message, so it cannot carry the launch prompt.
      // The orchestrator gets no skill restriction: it must see every skill to decide
      // what each spawned agent receives.
      "orchestrator": "pi --model {model} --thinking {thinking} --append-system-prompt {agent_file} {prompt}",
      "researcher": "pi --model {model} --thinking {thinking} --skill {skills} --append-system-prompt {agent_file} {prompt}",
      "default": ""         // used by any role without its own command
    },
    "spawn": "tmux new-window -n rh-{agent} -c {root} {command}",  // how `rh spawn` opens
                       // an agent; {command} is the launch command, shell-quoted. Empty =
                       // start detached and log to .rh/logs/.
    "shell": "fish",       // shell for `rh spawn terminal`; blank = $SHELL, else sh. Ask, never probe.
    "split": "vertical",   // pane layout for `rh spawn`: vertical | horizontal | window. Ask, never assume.
    "planners": {
      "models": [{}, {}],  // two different models. Empty (`none`) means the user plans.
      "max_rounds": 0      // 0 = cap at 3 rounds, then escalate the split to the user
    }
  },
  "literature": {
    "ref_manager": "zot",  // user-named, e.g. zot | bibtex | none
    "library": "papr",     // user-named PDF library / arXiv fetch tool, e.g. papr | zot | none
    "reading": "lit",      // user-named reader, e.g. lit | pdftotext | images
    "paywall": "ask_user", // ask_user | skip (skip = continue without that paper)
    "search": "crw"        // user-named search tool; any binary or service is valid
  },
  "project": {
    "name": "",            // label in prompts and status
    "git": false,          // true only if the user says this is already a repo
    "environment": []      // [{name, version, note}]: the software this project runs
  },
  "gates": { "user_approves_plan": true, "critique_veto": true }
}
```

Interview order, two or three unrelated keys per question, values shown back before moving on:
project root, name, how many parallel agents the user wants for planning and research (1..4),
backend, agent CLI, the exact launch command for that CLI (model, thinking level, how a skill is
selected: write `{model}` `{thinking}` `{skills}` `{prompt}` where the flags go), the pane command
(`agents.spawn`), skills to load, per-role models with thinking levels, planner models, search
tool, reference manager, reading method, paywall policy, git, gates.

Offer only what the user names or confirms. Never invent a model or tool name, and never infer one
from what happens to be installed: a binary on PATH does not mean this project should use it.

The root is never stored. It is the directory `.rh/env.json` sits in, and `.rh/` is what to verify
before opening any agent (rule 12).

## 3. Phase pipeline

```
0 CONFIG → 1 INTAKE → 2 ENVIRONMENT → 3 LITERATURE → 4 PLAN → 5 STATE
        → 6 IMPLEMENT → 7 CRITIQUE → 8 MANUSCRIPT → 9 CLOSE
                            ↑            │
                            └── replan ──┘  (verdicts go back to 3, 4 or 6)
```

Every phase states its exit gate. Do not enter the next phase with a gate unmet.

### Phase 0, CONFIG: `.rh/env.json`, `.rh/agents/`, `.rh/CHECKLIST.md`

`rh init` writes the workspace in one pass: the config, six role files (each with its §5 scope) and
`.rh/CHECKLIST.md`, your to-do list for the session (environment values still to ask about, launch
commands to wire, role files to tailor, `.rh/workflow.mmd` after the plan). It walks a short
questionnaire (name, agent count, backend, CLI, shell, split, start template) that shows the keys
once, then offers the installed options. It does not ask which skills to load; that is your call
with `rh env set agents.skills=...`. Enter keeps a configured value, Tab submits and moves on, `s`
really skips (a skipped question is yours to ask later), `q` finishes with the answers so far.

It never overwrites without archiving first: `--force` archives a copy, `--clean` archives the whole
`.rh/` (event logs, notes) before recreating it, `--dry-run` writes nothing.

Ask for the project root, then load `<root>/.rh/env.json`. If it is missing or does not parse,
interview the user and write it with `rh env set`. Show the values and get a yes.

Exit gate: the file parses, the user confirmed it, and it sits in `.rh/` of the root the user named.

### Phase 1, INTAKE: `PROBLEM.md`

Ask, do not assume: the research question in one sentence, why it matters, what counts as success,
what would falsify the result, constraints (time, hardware, data licence), and what is explicitly
out of scope.

Exit gate: `PROBLEM.md` has all six sections, and the user either read it back in their own words
or approved it.

### Phase 2, ENVIRONMENT: the environment record

Interview the user; do not probe. Ask which runtimes, packages, simulators, solvers, GPU stack and
CLI tools this project will use, and which versions they expect. Record what the user names,
including tools the CLI has never heard of. Never run `command -v` to decide the environment: an
installed binary says nothing about whether this project should use it.

Record it in `.rh/env.json` as `project.environment` (`{name, version, note}`, printed by
`rh env show`), or in `.rh/ENVIRONMENT.md` as prose when the user prefers that. This record is the
source for the manuscript's methods section: never retype a version, and amend it only with a dated
note.

Exit gate: the user has named the tools and versions for every part of the phase 1 scope, and the
record holds them. Unknown or user-named tools are valid.

### Phase 3, LITERATURE: `papers/`, `LITERATURE.md`, `OUTPUT_LAYOUT.md`, `GAPS.md`

Survey with the `literature.search` tool (finding and fetching) and read with `literature.reading`.
For every paper that survives reading, `LITERATURE.md` gets: citation, DOI or URL, a paragraph on
relevance, exactly what we take (method, number, parameter), what we reject and why, and page or
section anchors. Anything useful found mid-read (a method, a number, a parameter, a dataset, a
tool, an author to contact) gets its own line with that paper's DOI even when the paper is
rejected: a finding without its DOI cannot be cited later.

`OUTPUT_LAYOUT.md` is written while reading, not afterwards. Literature decides it from what the
user asked for (a manuscript, a report, a letter) and asks when the output is unclear. Never impose
a paper structure the user did not want. Literature owns the file; the Researcher appends whenever
it reads a paper or a source repo mid-implementation. It holds exactly one layout (ours) plus the
notes that justify it. For every paper read, add one row: DOI, what to copy or avoid, the equations
it uses (form and placement), the figures it produces (what they show, axes, units), how it
explains (what comes first, intuition against derivation, how much space), and what it never shows
(no error bars, no baseline, no uncertainty). Keep a running tally at the top: it is the evidence
for "every paper in this field does X". Never transcribe several layouts side by side. A note
either changes the single layout or stays a note, and every layout edit names the paper that drove
it. The layout is the output's skeleton: one entry per section, with heading, topics, equations,
figures and tables with axes and units, and the source of every number. If the deliverable is not a
manuscript or report, say so and this file may not exist.

`GAPS.md` records implementation sourcing: repo or paper, licence, what we borrow, what the source
lacks, who to credit, whether an upstream fix or PR is warranted. Anything suspicious you find in a
source's code goes to the Orchestrator or Critique, not into the implementation.

Downloading: `literature.library` is the tool that fetches and keeps PDFs. When it is `papr`
(`papr download <arxiv-id>`, a TUI for the library, arXiv fetching and the manuscript), point its
`download_path` at this project's `papers/` — or leave it in papr's own library and record the path in
`.rh/ENVIRONMENT.md` — then read from there. Whatever the tool, `LITERATURE.md` stays the record of
what we took: a PDF in a library is not a citation, and `papr`'s manuscript view is a workspace, not
evidence. Never cite from a library entry you have not opened.

Paywall: ask the user for the PDF by DOI. With a `ref_manager` it joins that collection, which then
holds the authoritative copy and `papers/` keeps only unmanaged PDFs; without one it goes into
`papers/`. If the user cannot get it, continue with what exists. Never swap in a different paper,
never paraphrase a paper you have not read. Record the absence in `LITERATURE.md` under "not
obtained".

Exit gate: the question in `PROBLEM.md` is either answered by existing work (say so, then stop or
re-scope with the user) or has a named gap we can attack. When the output is a manuscript or
report, `OUTPUT_LAYOUT.md` carries a pattern tally over every paper read and exactly one layout.

### Phase 4, PLAN: `PLAN.md`

Two planners on different models plan independently, with no shared transcript, each writing its
own candidate. Then they argue with each other, not with you: defend, concede, or counter until one
plan is agreed. You stay out of the argument. You are the chair, not a third planner. When they hand
over a final candidate, review it, reconcile it with `PROBLEM.md` and the approved artifacts, and
bring it to the user for the plan gate.

Planners run one after the other, so they sit outside the `agents.count` budget (§5).
`planners.max_rounds = 0` means three rounds; past that, record the unresolved split in `PLAN.md`
and ask the user rather than arguing on their credits. Log every round (§7). With `agents.count = 1`
there is no second planner context: say so, plan alone, and hand the user to a fresh session for the
plan gate (rule 14).

**No planner configured** (`agents.planners.models = none` or empty) means the user is the planner.
They write `PLAN.md`; you reconcile it against `PROBLEM.md`, create its tasks with `rh add task`,
and the user approves it. `rh phase` states this gate in those words.

The merged `PLAN.md` is ordered steps, each with an id, the action, the owner role, the deliverable
file, the verification command or check, dependencies, and the estimated risk. It links the tooling
from `.rh/env.json` rather than copying it. A step whose feasibility is unknown is marked `spike`
and carries a `timebox`.

Exit gate: planners that exist state agreement in `PLAN.md` ("agreed by <model> / <model> on
<date>"), or the user authored the plan, and the user approves it (`gates.user_approves_plan`). No
implementation before that yes.

### Phase 5, STATE: `STATUS.md`, `.rh/logs/`

`STATUS.md` holds the current phase and step id, the agent roster (role, model, backend window),
blockers, open questions aimed at the user, and a timestamped one-line history. Edit it on every
step transition. You do this yourself, never a spawned agent (rule 9).

Exit gate: it describes reality. Re-read it and check before answering any "where are we" question.

### Phase 6, IMPLEMENT: `src/`, `results/`

The Researcher implements step by step: implement, test, record the result, tick the plan step. With
`agents.count >= 2` the tests are written by a different context than the implementer; otherwise the
Reviewer hat writes them and the Researcher may not edit them to make them pass.

Tests are the contract. A step is done when its verification command succeeds and its output lands
in `results/` with the generating script, the exact command, the seed and the date. Fix a bug at the
root cause once, not at each call site.

Anything outside the approved plan (a new dependency, a new experiment, scope drift) stops and asks.
Drastic changes never happen on an agent's own initiative.

Exit gate: every plan step except open `spike`s is checked, the full suite is green, and `results/`
reproduces from a clean run.

### Phase 7, CRITIQUE: verdict in `STATUS.md` and `.rh/logs/`

Critique writes numbered must-answer questions against the artifacts, not the plan's intentions:
why this baseline, why this parameter, does the claim follow from the data, what breaks under load
or edge cases, what was never tested, what a hostile reviewer would say. Each question gets an
answer with evidence (file path, command, number), or the user closes it as `non-blocking`.

A blocking question sends the work back to phase 6, and to phase 4 if the answer changes scope. Then
re-run Critique on the changed parts only.

Exit gate: zero open blocking questions. With `gates.critique_veto` true, Critique can refuse the
gate, and its refusal names the questions.

### Phase 8, MANUSCRIPT: `MANUSCRIPT.md`

The Writer drafts from artifacts only. Methods cite the versions from the environment record, every
claim traces to a file in `results/` or an entry in `LITERATURE.md`, and every borrowed
implementation is credited through `GAPS.md`. The setup comes from the single layout in
`OUTPUT_LAYOUT.md`: open `MANUSCRIPT.md` with those headings in that order, carrying the listed
topics, equations and figures. If the layout is wrong, fix `OUTPUT_LAYOUT.md` first and say why. The
Reviewer checks claim against evidence, number against table, and section against layout; Critique
signs off. Missing evidence is a hard stop: delete the claim, never soften it.

If the user writes in `papr` (`literature.library`), its Typst project can be the writing surface —
the user names the file and `.rh/OUTPUT_LAYOUT.md` still drives the sections. `MANUSCRIPT.md` (or the
named file) stays the record the Reviewer reads: a claim a tool renders is not a claim with evidence.

Exit gate: every claim has an evidence line, no number disagrees with its source, and Critique has
signed off.

### Phase 9, CLOSE

Finalize `STATUS.md` (all steps checked, tests green, gate closed), write one log with lessons and
dead ends, list what is reusable next time, and state what was left undone. Ask whether to push
(`project.git`); never push unasked.

Exit gate: `STATUS.md` shows every step checked and the suite green, the close log exists, and the
push question is answered.

## 4. Replanning

Replanning is normal, not failure. Triggers: a blocking question from Critique, a `spike` that
proves infeasible, literature that invalidates an assumption, a failed reproduction, or a change of
direction from the user.

Write the proposed diff to `PLAN.md` (steps added, removed or reordered, each with the reason), get
the user's approval, then edit. The user decides. Never quietly rewrite the plan to match what was
already built.

## 5. Roles

| Role | Owns | May | May not |
| --- | --- | --- | --- |
| **Orchestrator** (the current runner) | routing, `STATUS.md`, `PLAN.md` merges, every question to the user | delegate, gate, escalate, edit artifacts | implement, fix code, approve its own plan, pick models |
| **Literature** | `papers/`, `LITERATURE.md`, `OUTPUT_LAYOUT.md`, `GAPS.md` | download open-access papers, read, cite, decide the layout from the requested output, flag code smells in a source | paraphrase an unread paper, substitute a reference, change the plan |
| **Researcher** | `src/`, `results/` | implement, test, probe tools, append to `OUTPUT_LAYOUT.md` from what it reads, ask for guidance | change scope, delete user files, install system packages, edit tests to pass |
| **Reviewer** | review verdicts | read everything, file findings, demand evidence | fix what it finds; independence is the point |
| **Critique** | the blocking-question list, the veto | question anything, block a gate, demand falsification | implement, soften its own findings |
| **Writer** | `MANUSCRIPT.md` | draft, restructure, cite from artifacts | introduce evidence absent from `results/` or `LITERATURE.md` |

The Orchestrator wears every hat that has no agent of its own:

| `agents.count` | Separate agents | Hats the Orchestrator wears |
| --- | --- | --- |
| 1 | none | Literature, Researcher, Reviewer, Critique, Writer |
| 2 | Researcher | Literature, Reviewer, Critique, Writer |
| 3 | Researcher, Critique | Literature, Reviewer, Writer |
| 4 | Researcher, Critique, Reviewer | Literature, Writer |

Critique gets its own agent from count 3 up, because a veto needs an independent context. When a
hat's work would be reviewed by the same context that did the work, say so in `STATUS.md`: the user
must know the review was not independent.

`rh` hardcodes no role information. A role is its file, `.rh/agents/<role>.md` (see `rh agents`),
which carries the role's rules and scope. `rh init` writes the starter roles, each with its §5 scope to narrow with the user; add a later one with
`rh agents <role> --write`, edit it with the user's approval, and record its launch command as
`agents.commands.<role>` in `.rh/env.json`. `rh spawn <role>` then runs exactly that command and
puts the role file in its `{agent_file}` slot. For a plain shell rather than an agent, use
`rh spawn terminal <cmd>`: it runs in `agents.shell` (or `$SHELL`) and follows `agents.split`,
asking the user for a layout when none is set.

Spawn with `rh spawn <role> "<instructions>"` (or `--prompt-file`). The launch command, model,
thinking level and skill selection all come from `agents.commands.<role>`; `rh spawn` inserts the
role file, appends the session facts (model, skills, board tasks, current phase) to the prompt, and
opens it with `agents.spawn`. Preview with `rh spawn <role> ... --dry-run`. If `rh` warns that
`{model}`, `{thinking}` or `{skills}` is missing from a template, fix the command with the user
instead of accepting the harness default. Before spawning, print the project path and confirm
`.rh/env.json` is there (rule 12), and record the spawn in `STATUS.md`. Confirm count and models with
the user if anything differs from `.rh/env.json`. Confirm the close the same way (rule 13).
`rh resume` always runs the Orchestrator in the terminal the user called it from; opening panes is
your own work, not the resume command's. The `rh` repo's `examples/` holds starter scripts and
per-role prompt templates with `{{PLACEHOLDER}}`s.

## 6. Ask-before list

No approval needed: reading, searching, writing the skill's own artifacts, running tests,
downloading open-access papers, and spawning agents up to `agents.count` with the models in
`.rh/env.json`.

Ask first, every time: installing system packages or new dependencies, deleting or overwriting a
file the skill did not create, exceeding `agents.count`, changing a model, anything behind a
paywall, changing `PLAN.md` after approval, rewriting `GAPS.md` sourcing decisions, any `git push`
or history rewrite, anything irreversible or outward-facing.

When you ask, state the action, why it is needed, the blast radius, and the alternative.

## 7. Log policy

Log only what must be remembered: a decision, a dead end, a failed run, a plan change, a user
override. Routine success is not logged; the artifacts already show it.

`.rh/logs/YYYY-MM-DD-HHMM-<role>-<title-token>.md`:

```
# <title>
- phase / step:
- what was tried:
- outcome: worked | failed | partial
- evidence: <command, file, number>
- decision taken + why:
- what a future agent must not redo:
```

## 8. Templates

`.rh/env.json` is the config object from §2, written with `rh env set` and never hand-edited
silently. The environment record is written after interviewing the user. Any tool the user names is
valid:

```
## Environment

- meep 1.29.0, FDTD, 2D and 3D (user-confirmed)
- jax: not used; the user prefers numpy on this machine
- custom solver "foo" 2.0: user-named, not on PATH
```

`STATUS.md`

```
# Status, <project name>
phase: 6 IMPLEMENT | step: S07 | updated: <ISO timestamp>
agents: orchestrator=<model>  researcher=<model>  (backend: tmux window 2)
blockers: none
open questions for user: (numbered, each answerable in one line)
history:
- <ISO> S06 done, tests green (24 passed), results/S06.csv
```

`OUTPUT_LAYOUT.md`

```
# Output layout, <manuscript | report | ...>

Target: <what the user asked for> | Venue/audience: <if named> | Length: <target>

## Patterns in comparable papers
| pattern | papers | count | note |
|---|---|---|---|
| setup schematic as Fig 1 | A, B, D | 3 | left to right, labelled a to d |
| governing equation before results | A, C | 2 | Eq. 1, in Methods |
| measured against simulated curve | A, B, C, D | 4 | log y, dB |
| comparison table against prior work | B, C | 2 | includes our metric |
| uncertainty stated | D | 1 | the rest omit it |
| explanation emphasis | A, B | 2 | physical intuition before math |

## Per paper
| paper (DOI) | copy or avoid | equations (form, placement) | figures (what, axes, units) | explanation emphasis | never shows |
|---|---|---|---|---|---|
| 10.1234/abcd | theory before simulation; clean Fig 1 | Eq. 1: <form>, in Methods | Fig 1 schematic; Fig 2 <x> against <y> (nm, dB) | intuition first, then derivation | error bars, baseline |

## Our layout (single, edited in place)
### 1 <Section heading>
- purpose: <what this section must establish>
- topics: <point 1>; <point 2>; <what must be stated explicitly>
- equations: <Eq. n, form, where it comes from>
- figures/tables: Fig 1 <what> (axes and units), data: <results/file>
- evidence: <results/S05.csv | 10.1234/abcd §3>; changed by: <paper DOI, if this was driven by one>
- status: <have data | data missing, step>
### 2 <...>
```

Every note is either folded into this one layout or stays a note. Two layouts in the file is a
defect.

A `PLAN.md` step

```
### S07, <action>
owner: researcher | deliverable: results/S07.csv
verify: `uv run pytest tests/test_s07.py`
depends on: S05 | risk: <what could invalidate it> | kind: build | spike
timebox: 90m   # only for kind: spike
```

The shape is free. The plan is read by people and agents, not parsed. What matters is that each step
names its verification and that someone creates the matching task with `rh add task`.

## 9. Anti-patterns

- Planning before reading the literature, then rewriting `PLAN.md` to fit what got built.
- A plan approved by the Orchestrator alone, or by nobody.
- A rule counted as met because an agent said so, rather than because a command or a file shows it.

## 10. The `rh` CLI, the machine layer

`rh` decides nothing. The artifacts stay the truth; `rh` displays, validates and reports on them.
Its state lives under `.rh/`:

```
.rh/
  env.json        the config (§2)
  ENVIRONMENT.md  the environment notes (phase 2), prose not config
  CHECKLIST.md    the generated to-do list (setup, gates, rules)
  tasks.json      the board: phases, steps, subtasks, states idle|working|complete
  logs/ notes/ tmp/
  workflow.mmd    the workflow diagram, authored by the Orchestrator or Researcher
```

Commands, by phase:

| Command | Phase | Notes |
| --- | --- | --- |
| `rh init [--force] [--dry-run] [--non-interactive]` | 0 | writes `.rh/`, the config, the role files and the checklist; archives before overwriting |
| `rh env show` / `rh env list` | 0-2 | read and validate the config, print the environment record |
| `rh env set KEY=VALUE ...` | 0 | writes `.rh/env.json`, the only config file |
| `rh add note\|literature\|gaps\|log <heading> -m "..."` | 3+ | appends under a heading, creating it if missing; literature takes a DOI |
| `rh search <query>` | any | rg-based search over `.rh/` and the artifacts, no index |
| `rh add task TITLE --id --deliverable --verify --subtask` | 4-6 | creates one board task with its subtasks |
| `rh tasks set <id> idle\|working\|complete` | 5-6 | board state; subtask ids work too. `rh tasks` shows the board |
| `rh phase` / `rh phase N` | any | shows the phase and its gate, or advances it gated; `--force` waives, so record it (rule 11) |
| `rh resume` / `rh -r` | any | execs the Orchestrator here, per `agents.commands.orchestrator`; `--dry-run` prints the command |
| `rh spawn <role> [prompt]` | any | opens a role agent per §5; `--dry-run`, `--inline`, `--prompt-file`, `--split` |
| `rh spawn terminal <cmd>` | any | opens a plain shell, not an agent |
| `rh agents [ROLE] [--write]` | any | list or show the role files |
| `rh doctor` | any | verify what the config names |
| `rh agent status`, `rh gate check`, `rh log tail`, `rh handoff` | any | running agents, gate report, logs, fresh-session pack (rule 14) |
| `rh info [FILE.md]` | any | what an artifact is for: owner, phase, sections, template, rules |
| `rh workflow` | 4+ | displays `.rh/workflow.mmd`; `--tools`, `--example` |

Contracts that keep the two layers consistent:

1. **`workflow.mmd` is agent-authored.** You or the Researcher writes it when the plan changes: the
   step DAG with dependencies and the current position, in the syntax of an installed renderer
   (`rh workflow --tools`). The CLI displays it and can render `--png` or `--svg`. With no renderer
   installed it lists options and the user picks; nothing is downloaded or installed automatically,
   not even through `npx`. `rh` never creates or overwrites `.rh/workflow.mmd` (transient sources go
   to `.rh/tmp/`); with no file it reports the workflow as pending.
2. **`rh phase` enforces the hard gates of §3, but the artifacts are the gate.** Passing the CLI
   check is not an exit gate by itself: user confirmation, planner agreement and critique sign-off
   still happen per §3.
3. **Tasks are created explicitly; nothing parses the plan.** `PLAN.md` stays prose. Whoever owns
   the plan creates its tasks with `rh add task` and moves them with `rh tasks set`. An agent that
   writes the plan creates its own tasks; a user-written plan has them created by the Orchestrator.
   Replanning (§4) edits the file first, then the tasks. `STATUS.md` stays the truth (rule 9); the
   board is display state.
4. **Same-terminal resume, explicit spawning.** Only the Orchestrator follows `rh resume`, and it
   never opens a pane: it execs the agent where the user typed the command. `rh spawn` opens one
   role agent through `agents.spawn`, else detached with a log in `.rh/logs/`, under rules 12 and 13.
5. **`rh workflow` prefers an installed renderer.** `bm` (beautiful-mermaid CLI) first, then
   `mermaid-ascii`, `mermansi`, `mermaid2term`, `merx`, `ma`, and a compact text view when none fits.
6. **`--json` works on every command** for agent reads. Never parse the pretty output.
7. **Launch commands are configuration, not code.** `rh` hardcodes no agent flag;
   `agents.commands.<role>` and `agents.spawn` are the source, and `rh` only substitutes the
   placeholders listed in §2. A template that leaves out `{model}`, `{thinking}` or `{skills}` still
   runs, but `rh resume` and `rh spawn` warn, and that warning means the session is not the one the
   config promised: fix the command with the user.
