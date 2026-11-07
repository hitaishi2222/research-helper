---
name: research-helper
description: Orchestrate a research project end to end — intake, environment setup, literature survey, dual-model planning, implementation with adversarial review, critique gate, manuscript, close — driven by `.rh/env.json` (agent count, per-role models, launch commands, literature tooling, approval gates) and `.rh/ENVIRONMENT.md` (the environment notes). Use when the user wants to scope a research question, survey literature, build and test an experiment, or write it up.
---

# Research Helper

A research project is a pipeline of phases with hard gates. This skill defines the
phases, who owns each artifact, what must be true to leave a phase, and what the
Orchestrator must ask the user instead of deciding alone.

Nothing here is advisory. If a rule cannot be followed, stop and ask.

---

## 0. Non-negotiables

1. **The current runner is always the Orchestrator.** Whoever loaded this skill is the head.
   It is the default: do not hand the role to a spawned agent. It alone asks the user
   questions, merges the plan, and updates `STATUS.md`.
2. **Never choose a model.** Agent count and every role's model live in
   `.rh/env.json`. To change them, the user asks the Orchestrator to run `rh env set`.
3. **Ask before every state-changing action.** See §6.
4. **No empty placeholder files.** Every artifact is created when it first has content.
5. **No silent scope change.** Anything not in an approved `PLAN.md` needs approval first.
6. **Never substitute a reference.** Paywalled paper → ask the user for the PDF by DOI.
7. **No result without a file.** A number that is not in `results/` with the script that
   produced it does not exist and may not appear in `MANUSCRIPT.md`.
8. **"Done" requires proof.** Tests green, plan steps checked, Critique has zero open
   blocking questions. Claims without evidence are rework.
9. **`STATUS.md` is truth — and it is the Orchestrator's own work.** Update it after every
   step and before every question to the user. Never delegate that update to a spawned agent.
10. **Re-read `.rh/env.json` and `.rh/ENVIRONMENT.md` at the start of every phase.** Never
    cache them — a version recorded in phase 2 may have moved.
11. **The user may waive a rule.** A waiver is not silent: name it in `STATUS.md` history with
    the rule number and in the manuscript's limitations. Without one, an unmet rule stops
    the phase.
12. **Verify the project path before opening any agent.** Resolve the root, confirm `.rh/`
    and `.rh/env.json` are there, and state the path to the user before spawning. Never open
    an agent in `$HOME`, a parent directory, or a neighbouring project.
13. **Close what you opened.** When a spawned agent's job is done, close its pane, window or
    tab and record the close in `STATUS.md`. Agents left running burn the user's credits.
14. **One agent means fresh eyes come from a new session.** With `agents.count = 1` there is
    no independent context to review the work. After a gate-heavy step (plan approved,
    implementation done, critique answered) tell the user to continue in a new session and
    hand over `STATUS.md` + `PLAN.md` as the handoff, instead of stretching this transcript.

---

## 1. Where things live

One location for all state: the **project root**, chosen by the user in phase 0. The skill
directory holds no config and no project data — this file is the whole skill.

Inside the project root:

```
<project root>/
  .rh/env.json      the config (phase 0) — written by `rh env set`   Orchestrator  phase 0
  .rh/ENVIRONMENT.md  tools + versions the user named               Orchestrator  phase 2
  .rh/CHECKLIST.md  generated to-do list (setup + gates + rules)    Orchestrator  phase 0+
  PROBLEM.md        goal, scope, success criteria, falsifier        Orchestrator  phase 1
  PLAN.md           approved step list (links .rh/env.json)         Planners      phase 4
  STATUS.md         current state, roster, blockers, open questions Orchestrator  phase 5+
  LITERATURE.md     what we took from each paper, with citations     Literature    phase 3
  OUTPUT_LAYOUT.md  output skeleton the user asked for + the patterns  Lit/Researcher phase 3+
                    comparable papers follow (sections, equations, figures, emphasis) Writer follows
  GAPS.md           implementation sourcing + upstream gaps          Lit/Researcher phase 3+
  MANUSCRIPT.md     write-up                                         Writer        phase 8
  papers/           downloaded PDFs, named <firstauthor><year>_<slug>.pdf
                    keep them: never delete or move a downloaded paper
  .rh/logs/         event logs, see §7
  .rh/agents/<role>.md  per-role tailored job description; `rh init` scaffolds all
                       starter roles (orchestrator, literature, researcher,
                       reviewer, critique, writer). This file IS the role — edit it
                       with the user. Wire it into the CLI's system-prompt area in
                       agents.commands.<role>.
  src/              implementation
  results/          every produced number, table, figure + the script that made it
```

Artifacts are created on first write, in the phase that first needs them. If a phase is
skipped with the user's agreement, its artifact simply never exists — that is allowed;
an empty file is not. **Pre-existing `PLAN.md` is adopted, never overwritten:**
read it, ask the user (adopt / diff / skip), and turn its steps into board tasks with
`rh add task` — there is no parser; the plan is prose and the board must not guess.
A forced write first archives the old file to `.rh/.bak/<timestamp>/`.

Before writing any artifact, run `rh info <FILE.md>`: it prints that file's purpose, owner,
phase, the sections it must have, the template to follow and the rules that bite there — so
no agent has to guess (and a user can read the same description).

The `rh` CLI (§10) keeps its machine state under `.rh/`
(`env.json`, `ENVIRONMENT.md`, `CHECKLIST.md`, `tasks.json`, `agents/`, `logs/`,
`notes/`, `workflow.mmd`) — the artifacts above remain the truth; `.rh/` is
derived display state, with two exceptions: `rh env set` writes `.rh/env.json`
itself, and `rh` never deletes downloaded `papers/`.

---

## 2. `.rh/env.json` — the config (write it through `rh env`)

Location: `<project root>/.rh/env.json`. It is the only config in this system, and `rh env set
KEY=VALUE` is the interface — it writes the file and `rh env show` reads it back. Do not
hand-edit the JSON silently: propose a diff, get approval, then run `rh env set` (or edit the
file and say so). The environment notes are a separate artifact, `.rh/ENVIRONMENT.md` (§3
phase 2); config and prose never share a file. If the file is absent or unparseable, run
phase 0.

The JSON below is the schema `rh env set` fills in (`jsonc` comments are for this document
only — the file itself is plain JSON).

Ask the user each key (batch only unrelated ones). Offer only what the user actually names
or confirms — never invent model or tool names, and never infer them from what happens to be
installed on the machine. A binary on PATH does not mean this project should use it.

```jsonc
{
  "agents": {
    "count": 1, // how many agents may run at once, 1..4 (asked as: how many
                //   parallel agents do you need for planning and research?)
    "backend": "tmux", // tmux | herdr | tuios | none (none = no panes, serial)
    "cli": "pi", // the agent binary this project runs (rh resume execs it)
    "skills": ["research-helper"], // skills every spawned agent must read first
    "roles": {
      // provider+model(+thinking) per role; the Orchestrator slot must be
      "orchestrator": { "provider": "pi", "model": "<model>", "thinking": "high" },
      "literature": {}, //   the model actually running this session
      "researcher": {},
      "reviewer": {},
      "critique": {},
      "writer": {},
    },
    "commands": {
      // how an agent CLI is STARTED — asked for, never invented. rh substitutes
      // the placeholders below; every {model} {thinking} {skills} {prompt}
      // {prompt_file} {agent_file} {root} {name} {role} must be written by the user/you.
      // {agent_file} is .rh/agents/<role>.md — put it in the harness's
      // system-prompt-APPEND flag (pi: --append-system-prompt {agent_file};
      // claude: --append-system-prompt-file {agent_file}; others: --system-file /
      // reading AGENTS.md). Never a flag that REPLACES the system prompt — the
      // session then loses its own harness rules. rh never hardcodes the flag name.
      // The prompt goes positionally ({prompt}); {prompt_file} only for a CLI that
      // really has such a flag. pi has none: --prompt-template registers a /command
      // and sends no message, so it cannot carry the launch prompt.
      // The orchestrator gets NO skill restriction: it must see every skill to
      // decide which one each spawned agent is given.
      "orchestrator": "pi --model {model} --thinking {thinking} --append-system-prompt {agent_file} {prompt}",
      "researcher": "pi --model {model} --thinking {thinking} --skill {skills} --append-system-prompt {agent_file} {prompt}",
      "default": "", //  used for any role without its own command
    },
    "spawn": "tmux new-window -n rh-{agent} -c {root} {command}", // how `rh spawn`
    //   opens a parallel agent ({command} = the launch command, shell-quoted);
    //   empty = start it detached and log to .rh/logs/
    "shell": "fish", // user's shell for `rh spawn terminal` (blank = $SHELL, else sh); asked, never probed
    "split": "vertical", // pane layout for `rh spawn` pane mode: vertical | horizontal | window (new workspace/window); asked, never assumed

    "planners": {
      // the two independent planners in phase 4
      "models": [{}, {}], // must be different models
      "max_rounds": 0, // 0 = cap at 3 rounds, then escalate with the split
    },
  },
  "literature": {
    "ref_manager": "zot", // user-named tool, e.g. zot | bibtex | none
    "reading": "lit", // user-named reader, e.g. lit | pdftotext | images
    "paywall": "ask_user", // ask_user | skip   (skip = proceed without that paper)
    "search": "crw", // user-named search tool; any binary or service is valid
  },
  "project": {
    "name": "", // the project's name — a label in prompts and status
    "git": false, // true only if user says the project is already a repo
  },
  "gates": {
    "user_approves_plan": true,
    "critique_veto": true,
  },
}
```

Interview order (batch 2–3 unrelated keys per question; show the resulting values before
moving on): project root → name → **how many parallel agents the user wants for planning and
research (1..4)** → backend → agent CLI → **the exact launch command for that CLI** (model,
thinking level, how a skill is selected; write `{model}` `{thinking}` `{skills}` `{prompt}`
wherever the flag goes) → the command that opens a pane (`agents.spawn`) → skills to read →
per-role models (+ thinking level) → planner models → search/browse tool → reference manager →
reading method → paywall policy → git → confirm gates. The root is never stored: it is the
directory `.rh/env.json` sits in, and `.rh/` is what needs verifying before any agent is
opened (rule 12).

---

## 3. Phase pipeline

```
0 CONFIG → 1 INTAKE → 2 ENVIRONMENT → 3 LITERATURE → 4 PLAN → 5 STATE
        → 6 IMPLEMENT → 7 CRITIQUE → 8 MANUSCRIPT → 9 CLOSE
                            ↑            │
                            └── replan ──┘  (verdicts go back to 3, 4 or 6)
```

Every phase states its **exit gate**. Do not enter the next phase with an unmet gate.

### Phase 0 — CONFIG → `.rh/env.json` (+ `.rh/agents/`, `.rh/CHECKLIST.md`)

`rh init` writes the workspace in one pass: `.rh/env.json` (the config), six
`.rh/agents/<role>.md` role scaffolds, and `.rh/CHECKLIST.md` — **your to-do
list for the rest of the session** (missing environment values to ask about,
launch commands to wire, role files to tailor, `.rh/workflow.mmd` after the
plan). It also walks a short rich questionnaire (name, agent count, backend, CLI,
shell, split, harness start template): the keys are shown once, then one
compact question frame lists the installed options. It does not ask which skills
to load — that is your call (`rh env set agents.skills=...`). Defaults are the values already in env.json, so Enter
keeps a configured project as it is; Tab submits and moves on; `s` really skips
(`s` is never written as a value) — a skipped question is yours to ask later;
`q` finishes with the answers so far. It never
overwrites existing files without archiving them first (`.rh/.bak/`): `--force`
archives a copy, `--clean` archives the whole `.rh/` (event logs, notes) before
recreating it, `--dry-run` writes nothing at all. If `PLAN.md` already exists in
the project, adopt it — read it, create its tasks with `rh add task`, never overwrite it.

Ask for the project root, then load `<root>/.rh/env.json`; if absent or it does not parse,
interview the user and write it with `rh env set`. Show the values and get a yes. Exit gate:
the file parses, the user confirmed it, and it sits in `.rh/` of the root the user named.

### Phase 1 — INTAKE → `PROBLEM.md`

Ask, do not assume: research question in one sentence; why it matters; what would count
as success; what would **falsify** the result; constraints (time, hardware, data licence);
explicitly out of scope. Exit gate: `PROBLEM.md` has all six sections and the user has read
it back to the Orchestrator in their own words or approved it.

### Phase 2 — ENVIRONMENT → `.rh/ENVIRONMENT.md`

Interview the user; do not probe. Ask which runtimes, packages, simulators, solvers, GPU
stack and CLI tools this project will actually use, and which versions they expect. Record
what the user names in `.rh/ENVIRONMENT.md` (`## Environment`, one line per tool) — including
tools the CLI has never heard of. Config stays in `.rh/env.json`; this file is prose.
Never run `command -v` to decide the environment: a binary being installed says nothing about
whether this project should use it.

This file is the source for the manuscript's methods section — never re-type versions
later, and amend it later only with a dated note.

Exit gate: the user has named the tools and versions for every part of the phase-1 scope,
and `.rh/ENVIRONMENT.md` records them. Unknown or user-named tools are valid.

### Phase 3 — LITERATURE → `papers/`, `LITERATURE.md`, `OUTPUT_LAYOUT.md`, `GAPS.md`

Survey with the `literature.search` tool (finding, fetching) and read with
`literature.reading`. For every paper that survives reading, `LITERATURE.md` gets:
citation, DOI/URL, one-paragraph relevance, exactly what we take (method, number,
parameter), what we reject and why, and page/section anchors. Anything useful noticed
mid-read — a method, a number, a parameter, a dataset, a tool, an author to contact — gets
its own line with that paper's DOI even when the paper is rejected, because a finding
without its DOI cannot be cited later and will be lost.

`OUTPUT_LAYOUT.md` is written while reading, not afterwards. The Literature agent decides it
from what the user asked for — a manuscript, a report, a letter — and asks if the output is
unclear; never impose a paper structure the user did not want. Literature owns the file; the
Researcher appends whenever it reads a paper or source repo mid-implementation. It holds
**exactly one layout** (ours) plus the notes that justify it. For every paper that survives
reading, add one row: DOI, what to copy or avoid, the equations it uses (form and where they
appear), the figures/images it produces (what they show, axes, units), how it explains (what
is emphasised first, intuition vs derivation, how much space), and what it conspicuously
never shows (no error bars, no baseline, no uncertainty). Keep a running tally at the top —
it is the evidence for "every paper in this field does X". Never transcribe several papers'
layouts side by side; a note either changes the single layout or stays a note, and every
layout edit names the paper that drove it. The layout is the output's skeleton: one entry per
section naming its heading, topics, equations, figures/tables with axes and units, and the
source of every number. If the deliverable is not a manuscript or report, say so and this
file may not exist.

`GAPS.md` records implementation sourcing: repo or paper, licence, what we borrow, what the
source is missing, who to credit, and whether an upstream fix/PR is warranted. While
reading a source's code, anything suspicious goes to the Orchestrator or Critique, not into
the implementation.

Paywall: ask the user for the PDF by DOI. With a `ref_manager` it goes into that collection,
which is then authoritative and `papers/` holds only unmanaged PDFs; otherwise it goes into
`papers/`. If they cannot get it, continue with what exists — never swap in a different
paper, never paraphrase a paper you have not read. Absences are recorded in
`LITERATURE.md` under "not obtained".

Exit gate: the question in `PROBLEM.md` is either addressed by existing work (say so, and
stop or re-scope with the user) or has a named gap we can attack; when the output is a
manuscript or report, `OUTPUT_LAYOUT.md` has a pattern tally over every paper read and
exactly one layout.

### Phase 4 — PLAN → `PLAN.md`

Two planners on different models plan **independently** (no shared transcript), each
writing its own candidate plan. Then they talk **to each other, not to the Orchestrator**:
defend, concede, or counter until they have one agreed plan. The Orchestrator stays out of
the argument — it is the chair, not a third planner. Only when the planners hand over a
finalized candidate does the Orchestrator review it, reconcile it with `PROBLEM.md` and the
approved artifacts, and bring it to the user for the plan gate.

Planners run one after the other, so they are exempt from the `agents.count` concurrency
budget (§5). `planners.max_rounds = 0` means three rounds; past that, record the unresolved
split in `PLAN.md` and ask the user — never keep arguing on the user's credits. Every round
is logged (§7). With `agents.count = 1` there is no second planner context: say so, plan
alone, and hand the user to a fresh session for the plan gate (rule 14).

The merged `PLAN.md` is ordered steps, each with: id, action, owner role, deliverable file,
**verification command or check**, dependencies on other steps, and estimated risk. Plus the
tooling table from `.rh/env.json` (link it, never copy it). Steps that are pure research (unknown
feasibility) are marked `spike` and carry a `timebox`.

Exit gate: both planners state agreement in `PLAN.md` ("agreed by <model> / <model> on
<date>"), and the user approves the plan (`gates.user_approves_plan`). No implementation
before that yes.

### Phase 5 — STATE → `STATUS.md`, `.rh/logs/`

`STATUS.md` holds: current phase and step id, agent roster (role → model → backend window),
blockers, open questions aimed at the user, and a timestamped one-line change history.
Every step transition edits it — the Orchestrator does this itself, never a spawned agent
(rule 9). Exit gate: it accurately describes reality (re-read and check before answering any
"where are we" question).

### Phase 6 — IMPLEMENT → `src/`, `results/`

Researcher implements step by step. Move in small steps: implement → test → record result →
tick the plan step. If `agents.count >= 2`, the tests are written by a different context
than the implementer (the second agent); otherwise the Reviewer hat writes them and the
Researcher may not edit them to pass.

Tests are the contract: a step is done when its plan verification command succeeds and its
output lands in `results/` with the generating script, the exact command, the seed and the
date. Bugs are fixed at the root cause once, not patched at call sites.

Anything not in the approved plan — new dependency, new experiment, scope drift — stops and
asks. Drastic changes never happen on the agent's own initiative.

Exit gate: all plan steps (except open `spike`s) checked, full test suite green, `results/`
reproduces from a clean run.

### Phase 7 — CRITIQUE → verdict in `STATUS.md` + `.rh/logs/`

Critique writes numbered must-answer questions against the actual artifacts (not the plan's
intentions): why this baseline, why this parameter, does the claim follow from the data,
what breaks under load/edge cases, what was never tested, what would a hostile reviewer say.
Each question gets an answer with evidence (file path, command, number) or is closed as
`non-blocking` by the user.

Any blocking question → return to phase 6 to fix, and to phase 4 if the answer changes
scope. Then re-run Critique on the changed parts only.

Exit gate: zero open blocking questions. With `gates.critique_veto` true, Critique can
refuse this gate; its refusal names the specific questions.

### Phase 8 — MANUSCRIPT → `MANUSCRIPT.md`

Writer drafts from artifacts only: methods cite the `.rh/ENVIRONMENT.md` versions, every claim traces to
a `results/` file or a `LITERATURE.md` entry, every borrowed implementation is attributed
via `GAPS.md`. Setup comes from the single layout in `OUTPUT_LAYOUT.md`: open `MANUSCRIPT.md`
with those headings in that order, carrying the listed topics, equations and figures. If the
layout is wrong, fix `OUTPUT_LAYOUT.md` first and say why. Reviewer pass checks
claim↔evidence, number↔table, and section↔layout drift; Critique signs off. Missing evidence
is a hard stop — delete the claim, never soften it.

Exit gate: every claim has an evidence line, no number↔source mismatch remains, Critique has
signed off.

### Phase 9 — CLOSE

Finalize `STATUS.md` (all steps checked, tests green, gate closed), write one log with
lessons and dead ends, list what is reusable next time, and state what was left undone.
Ask whether to push (`project.git`) — never push unasked.

Exit gate: `STATUS.md` shows every step checked and the suite green, the close log exists,
and the push question has been answered.

---

## 4. Replanning

Replanning is normal, not failure. Triggers: Critique blocking questions, a `spike` that
proves infeasible, literature that invalidates an assumption, a failed reproduction, or a
user change of direction.

The Orchestrator writes the proposed diff to `PLAN.md` (added / removed / reordered steps
with the reason), gets user approval, then edits. The user is always the decider here.
Never quietly rewrite the plan to match what was already built.

---

## 5. Roles

| Role                                  | Owns                                                       | May                                                           | May not                                                                      |
| ------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Orchestrator** (the current runner) | routing, `STATUS.md`, `PLAN.md` merges, all user questions | delegate, gate, escalate, edit artifacts                      | implement, fix code, approve its own plan, pick models                       |
| **Literature**                        | `papers/`, `LITERATURE.md`, `OUTPUT_LAYOUT.md`, `GAPS.md`                      | download open-access, read, cite, decide the layout from the user's requested output, flag code smells in sources | paraphrase unread papers, substitute references, change the plan             |
| **Researcher**                        | `src/`, `results/`                                         | implement, test, probe tools, append to `OUTPUT_LAYOUT.md` from papers/repos it reads, ask for guidance                | change scope, delete user files, install system packages, edit tests to pass |
| **Reviewer**                          | review verdicts                                            | read everything, file findings, demand evidence               | fix what it finds (independence is the point)                                |
| **Critique**                          | blocking-question list, veto                               | question anything, block a gate, demand falsification         | implement, soften its own findings                                           |
| **Writer**                            | `MANUSCRIPT.md`                                            | draft, restructure, cite from artifacts                       | introduce evidence not in `results/` or `LITERATURE.md`                      |

**Agent budget mapping.** The Orchestrator wears every hat not given its own agent:

| `agents.count` | Separate agents                | Hats worn by Orchestrator                          |
| -------------- | ------------------------------ | -------------------------------------------------- |
| 1              | —                              | Literature, Researcher, Reviewer, Critique, Writer |
| 2              | Researcher                     | Literature, Reviewer, Critique, Writer             |
| 3              | Researcher, Critique           | Literature, Reviewer, Writer                       |
| 4              | Researcher, Critique, Reviewer | Literature, Writer                                 |

Critique gets its own agent from count 3 up because veto power needs an independent context.
When a hat's work would be reviewed by the same context that did the work, say so in
`STATUS.md` — the user must know a review was not independent.

There is **no hardcoded role info** in rh. Each role is entirely its file
`.rh/agents/<role>.md` (see `rh agents`). The file carries the role's rules
and scope so harnesses that read AGENTS.md-style role files can be tailored
to the role. `rh init` scaffolds all starter roles already; use
`rh agents <role> --write` for a later role, edit it with the user's approval, and the
Orchestrator records the launch command for each role in `.rh/env.json`
(`agents.commands.<role>`). `rh spawn <role>` then uses exactly that command
to open the agent, wiring the role file into the harness's system-prompt
area with `{agent_file}` (or, for `rh spawn terminal <cmd>`, a plain shell
terminal in the user's shell and the pane layout in `agents.split`).

Spawn agents with `rh spawn <role> "<instructions>"` (or `--prompt-file`). The launch
command, its model, its thinking level and its skill selection all come from
`agents.commands.<role>` in `.rh/env.json`; `rh spawn` puts the role file at
`{agent_file}` (the template wires it into the CLI's system-prompt area),
appends the session facts (model, skills, board tasks, current phase) to the
prompt, and opens it with `agents.spawn`. For a plain terminal
inside the same backend (not an agent), use `rh spawn terminal <cmd>` — it runs
in `agents.shell` (or `$SHELL`) and respects `agents.split`, asking the user for
the layout when it is not set. Preview first with `rh spawn <role> … --dry-run`; if `rh` warns that
`{model}`, `{thinking}` or `{skills}` is missing from the template, fix the command in `.rh/env.json`
with the user instead of accepting the harness default.
Before spawning, resolve and print the project path and check `.rh/env.json` is there (rule 12);
record each spawn in `STATUS.md`. Confirm count and models with the user before spawning if
anything differs from `.rh/env.json`. When the job is done, close the agent's
pane/window/tab and record the close with the same care (rule 13). `rh resume` always runs the
Orchestrator in the terminal the user called it from — spawning panes is the Orchestrator's
own work, not the resume command's. `examples/` in the `rh` repo carries starter scripts and
per-role prompt templates with `{{PLACEHOLDER}}`s to copy.

---

## 6. Ask-before list

Free without asking: reading, searching, writing the skill's own artifacts, running tests,
downloading open-access papers, spawning agents up to `agents.count` with the `.rh/env.json` models.

Ask first, every time: installing system packages or new dependencies, deleting or
overwriting any file the skill did not create, exceeding `agents.count` or changing a model,
buying/borrowing anything behind a paywall, changing `PLAN.md` after approval, rewriting
`GAPS.md` sourcing decisions, any `git push` or history rewrite, anything irreversible or
outward-facing.

When asking: state the action, why it is needed, the blast radius, and the alternative.

---

## 7. Log policy

Log only when something must be remembered — a decision, a dead end, a failed run, a plan
change, a user override. Routine success is not logged; the artifacts already show it.

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

---

## 8. Templates

`.rh/env.json` — the config object from §2 (written with `rh env set`, never hand-edited
silently). `.rh/ENVIRONMENT.md` — the notes the Orchestrator writes after asking
(free-form; any tool the user names is valid):

```
## Environment

- meep 1.29.0 — FDTD, 2D/3D (user-confirmed)
- jax — not used; the user prefers numpy on this machine
- custom solver "foo" 2.0 — user-named, not on PATH
```

`STATUS.md`

```
# Status — <project name>
phase: 6 IMPLEMENT | step: S07 | updated: <ISO timestamp>
agents: orchestrator=<model>  researcher=<model>  (backend: tmux window 2)
blockers: none
open questions for user: (numbered, each answerable in one line)
history:
- <ISO> S06 done, tests green (24 passed), results/S06.csv
```

`OUTPUT_LAYOUT.md`

```
# Output layout — <manuscript | report | ...>

Target: <what the user asked for>   |   Venue/audience: <if named>   |   Length: <target>

## Patterns in comparable papers
| pattern | papers | count | note |
|---|---|---|---|
| setup schematic as Fig 1 | A, B, D | 3 | left-to-right, labelled a–d |
| governing equation before results | A, C | 2 | Eq. 1, in Methods |
| measured vs simulated curve | A, B, C, D | 4 | log y, dB |
| comparison table vs prior work | B, C | 2 | includes our metric |
| uncertainty stated | D | 1 | the rest omit it |
| explanation emphasis | A, B | 2 | physical intuition before math |

## Per paper
| paper (DOI) | copy / avoid | equations (form, placement) | figures / images (what, axes, units) | explanation emphasis | never shows |
|---|---|---|---|---|---|
| 10.1234/abcd | theory before sim; clean Fig 1 | Eq. 1: <form>, in Methods | Fig 1 schematic; Fig 2 <x> vs <y> (nm, dB) | intuition first, then derivation | error bars, baseline |

## Our layout (single, edited in place)
### 1 <Section heading>
- purpose: <what this section must establish>
- topics: <point 1>; <point 2>; <what must be stated explicitly>
- equations: <Eq. n — form — where it comes from>
- figures/tables: Fig 1 <what> (axes/units) — data: <results/file>
- evidence: <results/S05.csv | 10.1234/abcd §3>   | changed by: <paper DOI, if this was driven by one>
- status: <have data | data missing → step>
### 2 <...>
...
```

Every note above is either folded into this one layout or left as a note. Two layouts in the
file is a defect.

`PLAN.md` step

```
### S07 — <action>
owner: researcher | deliverable: results/S07.csv
verify: `uv run pytest tests/test_s07.py`
depends on: S05 | risk: <what could invalidate it> | kind: build | spike
timebox: 90m   # only for kind: spike
```

---

## 9. Anti-patterns

- Planning before reading the literature, then rewriting `PLAN.md` to fit what got built.
- A plan approved by the Orchestrator alone, or by nobody.
- A rule counted as met because an agent said so, not because a command or a file shows it.

---

## 10. The `rh` CLI — the machine layer for this skill

`rh` (installed from the skill's sibling `cli/` package) is the machine-readable
layer for everything above. It never replaces the artifacts or decides anything:
artifacts stay the truth, `rh` displays, validates, and mirrors them. Its state
lives in `.rh/` at the project root:

```
.rh/
  env.json        the config (§2) — written by rh env set, read by rh env show
  ENVIRONMENT.md  tools + versions the user named (phase 2) — prose, not config
  CHECKLIST.md    your generated to-do list (setup + gates + rules)
  tasks.json      task board: phases + steps + subtasks, states idle|working|complete
  logs/ notes/ tmp/
  workflow.mmd    the project workflow diagram — AUTHORED by the Orchestrator
                  or Researcher (see below); `rh workflow` only displays it
```

Commands agents use per phase:

| Command | Phase | Notes |
|---|---|---|
| `rh init [--force] [--dry-run] [--non-interactive]` | 0 | creates the `.rh/` layout, `env.json`, the `.rh/agents/*.md` role files and `.rh/CHECKLIST.md` in this directory, non-destructively (never overwrites without `--force` backup); project name = the directory, changeable with `rh env set project.name=`; skippable questionnaire per §2 |
| `rh env show` / `env list` | 0–2 | read and validate the config + `.rh/ENVIRONMENT.md` notes |
| `rh env set KEY=VALUE ...` | 0 | writes `.rh/env.json` (the only config file); `rh env show` reads it back |
| `rh add note\|literature\|gaps\|log <h> -m "..."` | 3+ | appends under a heading, creating it if missing; literature accepts a DOI |
| `rh search <query>` | any | rg-first local search over `.rh/` + artifacts, no indexing |
| `rh add task TITLE --id --deliverable --verify --subtask` | 4–6 | creates one board task, with its subtasks, explicitly |
| `rh tasks set <id> idle\|working\|complete` | 5–6 | board state (subtask ids work too); `rh tasks` shows every task, subtask and status |
| `rh phase` / `rh phase N` | any | no argument: the current phase and its exit gate. With N: **gated** advance, refusing unmet gates; `--force` is a waiver → record it in STATUS.md (rule 11) |
| `rh resume` / `rh -r` | any | execs the Orchestrator **in this terminal**: command from `agents.commands.orchestrator` (which wires `.rh/agents/orchestrator.md` in as the system prompt), model + thinking level from `agents.roles.orchestrator`, only `agents.skills` loaded. Its first message is the skill read, not project state; it is not echoed to the terminal. `--dry-run` prints the exact command + prompt |
| `rh spawn <role> [prompt]` | any | opens another role agent with `agents.commands.<role>` + `agents.spawn`; `{agent_file}` puts `.rh/agents/<role>.md` in the template's system-prompt flag, board tasks + session facts go in the prompt; `--dry-run`, `--inline`, `--prompt-file`, `--split` |
| `rh spawn terminal <cmd>` | any | opens a plain shell terminal (not an agent) in a new pane: shell from `agents.shell`/`$SHELL`, layout from `agents.split`; `--dry-run`, `--split` |
| `rh agents [ROLE] [--write]` | any | list or show the per-role files in `.rh/agents/`; `--write` creates a missing one (init already scaffolds the starter roles) |
| `rh doctor` | any | verify what env.json names (shell, split, templates, role files, binaries) |
| `rh agent status` / `rh gate check` / `rh log tail` / `rh handoff` | any | running agents from spawns.jsonl, gate report, §7 logs, fresh-session pack (rule 14) |
| `rh info [FILE.md]` | any | what an artifact is for: owner, phase, required sections, template, rules. Read it before writing any artifact |
| `rh workflow` | 4+ | displays `.rh/workflow.mmd` as ASCII (renderer-dependent); `--tools` lists renderers; `--example` prints a starter source |

Contracts that keep the two layers consistent:

1. **`workflow.mmd` is agent-authored.** The Orchestrator or Researcher creates
   or updates it when the plan changes (the PLAN.md step DAG with dependencies
   and current position), shaped for the renderers available (`rh workflow
   --tools`). `rh workflow` displays it as ASCII when a local renderer is
   installed and can render `--png`/`--svg` artifacts. If no renderer is
   installed, the CLI lists installation options and the USER picks (nothing
   is ever downloaded or installed automatically — not even via `npx`); the
   agent then writes the .mmd in the syntax the chosen renderer consumes.
   The file is the contract, the CLI is only the viewer. **`rh` never creates
   or overwrites `<root>/.rh/workflow.mmd`** (transient render sources live in
   `.rh/tmp/`); when the file is absent the CLI reports the workflow as
   pending and draws nothing.
2. **`rh phase` enforces §3's hard gates, but the artifacts it checks are the
   gate.** Passing the CLI check is not an exit gate by itself; the user
   confirmation, planner agreement, and critique sign-off still happen per §3.
3. **Tasks are created explicitly; nothing parses the plan.** `PLAN.md` is prose
   and stays prose — it is read by people and agents, never by a parser. Whoever
   owns the plan turns its steps into board tasks with `rh add task "<title>" --id
   S0N --owner … --deliverable … --verify … --subtask "…"` (repeatable `--subtask`;
   ids like `S04b` are valid), and `rh tasks set <id> working|complete` moves them.
   If an agent writes the plan, that agent creates the tasks; if the user writes it,
   the Orchestrator creates them. Replanning (§4) edits `PLAN.md` first, then the
   tasks. `STATUS.md` remains the truth (rule 9) — the board is display state for
   `rh tasks`.

4. **Same-terminal resume, explicit agent spawning.** Only the Orchestrator follows
   `rh resume` in the same terminal: it never opens a new pane or workspace, it execs
   the agent where the user typed the command,
   with the command written in `agents.commands.orchestrator`. `rh spawn` opens
   one role agent — via `agents.spawn` when set, otherwise as a detached process
   logging to `.rh/logs/` — with the path check of rule 12 and the close of
   rule 13.

5. **`workflow` prefers the installed renderer.** `bm` (beautiful-mermaid CLI) is
   first in the priority list, then `mermaid-ascii`, `mermansi`, `mermaid2term`,
   `merx`, `ma`; when none fits the terminal, the CLI falls back to its built-in
   compact text view rather than printing a 300-column canvas.
6. **`--json` works on every command** for agent reads; never parse the pretty UI.

7. **Launch commands are configuration, not code.** `rh` hardcodes no agent
   flag: `agents.commands.<role>` and `agents.spawn` in `.rh/env.json` are the
   source, and `rh` only substitutes `{model}` `{thinking}` `{skills}` `{prompt}`
   `{prompt_file}` `{agent_file}` `{root}` `{name}` `{role}` (`{command}` in `agents.spawn`; the shell
   for terminal mode and the pane layout come from `agents.shell`/`agents.split`, asked
   of the user). The role file (`.rh/agents/<role>.md`, via `{agent_file}`) is how
   each specialized agent gets its tailored system prompt — rh only substitutes the
   path, the harness flag itself is in the template.
   A template that leaves `{model}`, `{thinking}` or `{skills}` out still runs,
   but `rh resume`/`rh spawn` say so in their notes — that warning means the
   session is not the one env.json promised, so fix the command with the user.
   Only `agents.skills` may be loaded: fewer skills, smaller context, and the
   skill stays authoritative.
