---
name: research-helper
description: Orchestrate a research project end to end — intake, environment setup, literature survey, dual-model planning, implementation with adversarial review, critique gate, manuscript, close — driven by an ENV.md in the project root that holds the config block (agent count, per-role models, literature tooling, approval gates) and the environment notes. Use when the user wants to scope a research question, survey literature, build and test an experiment, or write it up.
---

# Research Helper

A research project is a pipeline of phases with hard gates. This skill defines the
phases, who owns each artifact, what must be true to leave a phase, and what the
Orchestrator must ask the user instead of deciding alone.

Nothing here is advisory. If a rule cannot be followed, stop and ask.

---

## 0. Non-negotiables

1. **The current runner is always the Orchestrator.** Whoever loaded this skill is the head.
2. **Never choose a model.** Agent count and every role's model live in the config block at
   the top of `ENV.md`. To change them, the user asks the Orchestrator to edit that block.
3. **Ask before every state-changing action.** See §6.
4. **No empty placeholder files.** Every artifact is created when it first has content.
5. **No silent scope change.** Anything not in an approved `PLAN.md` needs approval first.
6. **Never substitute a reference.** Paywalled paper → ask the user for the PDF by DOI.
7. **No result without a file.** A number that is not in `results/` with the script that
   produced it does not exist and may not appear in `MANUSCRIPT.md`.
8. **"Done" requires proof.** Tests green, plan steps checked, Critique has zero open
   blocking questions. Claims without evidence are rework.
9. **`STATUS.md` is truth.** Update it after every step and before every question to the user.
10. **Re-read the `ENV.md` config block at the start of every phase.** Never cache it. The
    environment notes below it are re-read too — a version recorded in phase 2 may have moved.
11. **The user may waive a rule.** A waiver is not silent: name it in `STATUS.md` history with
    the rule number and in the manuscript's limitations. Without one, an unmet rule stops
    the phase.

---

## 1. Where things live

One location for all state: the **project root**, chosen by the user in phase 0. The skill
directory holds no config and no project data — this file is the whole skill.

Inside the project root:

```
<project root>/
  PROBLEM.md        goal, scope, success criteria, falsifier        Orchestrator  phase 1
  ENV.md            config block (phase 0) + environment notes      Orchestrator  phase 0/2
  PLAN.md           approved step list (links ENV.md for tooling)   Planners      phase 4
  STATUS.md         current state, roster, blockers, open questions Orchestrator  phase 5+
  LITERATURE.md     what we took from each paper, with citations     Literature    phase 3
  OUTPUT_LAYOUT.md  output skeleton the user asked for + the patterns  Lit/Researcher phase 3+
                    comparable papers follow (sections, equations, figures, emphasis) Writer follows
  GAPS.md           implementation sourcing + upstream gaps          Lit/Researcher phase 3+
  MANUSCRIPT.md     write-up                                         Writer        phase 8
  papers/           downloaded PDFs, named <firstauthor><year>_<slug>.pdf
  logs/             event logs, see §7
  src/              implementation
  results/          every produced number, table, figure + the script that made it
```

Artifacts are created on first write, in the phase that first needs them. If a phase is
skipped with the user's agreement, its artifact simply never exists — that is allowed;
an empty file is not.

The `rh` CLI (§10) keeps a machine-readable mirror of this state under `.rh/`
(`env.json`, `tasks.json`, `logs/`, `notes/`, `workflow.mmd`) — the artifacts
above remain the truth; `.rh/` is derived display state, with the single
exception that `rh env set` writes ENV.md itself.

---

## 2. `ENV.md` — config block

Location: `<project root>/ENV.md`. The `jsonc` block at its top is the only config in this
system; there is no separate config file and nothing config-like lives in the skill
directory. If the block is absent or unparseable, run phase 0. Never hand-edit it silently;
propose a diff, get approval, then write. Phase 2 appends the environment notes below the block.

Ask the user each key (batch only unrelated ones). Offer only what the user actually names
or confirms — never invent model or tool names, and never infer them from what happens to be
installed on the machine. A binary on PATH does not mean this project should use it.

```jsonc
{
  "agents": {
    "count": 1, // how many agents may run at once, 1..4
    "backend": "tmux", // tmux | herdr | tuios | none (none = no panes, serial)
    "roles": {
      // provider+model per role; the Orchestrator slot must be
      "orchestrator": {}, //   the model actually running this session
      "literature": {},
      "researcher": {},
      "reviewer": {},
      "critique": {},
      "writer": {},
    },
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
    "slug": "", // short kebab-case name
    "git": false, // true only if user says the project is already a repo
  },
  "gates": {
    "user_approves_plan": true,
    "critique_veto": true,
  },
}
```

Interview order (batch 2–3 unrelated keys per question; show the resulting block before
moving on): project root → slug → agent count → backend → per-role models → planner models →
search/browse tool → reference manager → reading method → paywall policy → git → confirm
gates. The root is never stored: it is the directory `ENV.md` sits in.

---

## 3. Phase pipeline

```
0 CONFIG → 1 INTAKE → 2 ENVIRONMENT → 3 LITERATURE → 4 PLAN → 5 STATE
        → 6 IMPLEMENT → 7 CRITIQUE → 8 MANUSCRIPT → 9 CLOSE
                            ↑            │
                            └── replan ──┘  (verdicts go back to 3, 4 or 6)
```

Every phase states its **exit gate**. Do not enter the next phase with an unmet gate.

### Phase 0 — CONFIG → `ENV.md` config block

Ask for the project root, then load `<root>/ENV.md`; if absent or its config block does not
parse, interview and write the block. Print it and get a yes. Exit gate: the block parses,
the user confirmed, and the file sits in the root the user named.

### Phase 1 — INTAKE → `PROBLEM.md`

Ask, do not assume: research question in one sentence; why it matters; what would count
as success; what would **falsify** the result; constraints (time, hardware, data licence);
explicitly out of scope. Exit gate: `PROBLEM.md` has all six sections and the user has read
it back to the Orchestrator in their own words or approved it.

### Phase 2 — ENVIRONMENT → `ENV.md` environment notes, under the config block

Interview the user; do not probe. Ask which runtimes, packages, simulators, solvers, GPU
stack and CLI tools this project will actually use, and which versions they expect. Record
what the user names in an `## Environment` section below the config block — including tools
the CLI has never heard of. Never run `command -v` to decide the environment: a binary being
installed says nothing about whether this project should use it.

This section is the source for the manuscript's methods section — never re-type versions
later, and amend it later only with a dated note.

Exit gate: the user has named the tools and versions for every part of the phase-1 scope,
and the `## Environment` section records them. Unknown or user-named tools are valid.

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
writing its own candidate plan. Then they argue directly with each other: defend, concede,
or counter. Planners run one after the other, so they are exempt from the `agents.count`
concurrency budget (§5). `planners.max_rounds = 0` means three rounds; past that, record the
unresolved split in `PLAN.md` and ask the user — never keep arguing on the user's credits.
Every round is logged (§7).

The merged `PLAN.md` is ordered steps, each with: id, action, owner role, deliverable file,
**verification command or check**, dependencies on other steps, and estimated risk. Plus the
tooling table from `ENV.md` (link it, never copy it). Steps that are pure research (unknown
feasibility) are marked `spike` and carry a `timebox`.

Exit gate: both planners state agreement in `PLAN.md` ("agreed by <model> / <model> on
<date>"), and the user approves the plan (`gates.user_approves_plan`). No implementation
before that yes.

### Phase 5 — STATE → `STATUS.md`, `logs/`

`STATUS.md` holds: current phase and step id, agent roster (role → model → backend window),
blockers, open questions aimed at the user, and a timestamped one-line change history.
Every step transition edits it. Exit gate: it accurately describes reality (re-read and
check before answering any "where are we" question).

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

### Phase 7 — CRITIQUE → verdict in `STATUS.md` + `logs/`

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

Writer drafts from artifacts only: methods cite the `ENV.md` versions, every claim traces to
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

Spawn agents with `agents.backend` (`tmux new-window`, `herdr`, `tuios`; see those skills).
Record each spawn in `STATUS.md`. Confirm count and models with the user before spawning if
anything differs from the `ENV.md` config block.

---

## 6. Ask-before list

Free without asking: reading, searching, writing the skill's own artifacts, running tests,
downloading open-access papers, spawning agents up to `agents.count` with the `ENV.md` models.

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

`logs/YYYY-MM-DD-HHMM-<role>-<slug>.md`:

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

`ENV.md` — the config block from §2 on top, then the environment notes the Orchestrator
writes after asking (free-form; any tool the user names is valid):

```
## Environment

- meep 1.29.0 — FDTD, 2D/3D (user-confirmed)
- jax — not used; the user prefers numpy on this machine
- custom solver "foo" 2.0 — user-named, not on PATH
```

`STATUS.md`

```
# Status — <project slug>
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
  env.json        machine mirror of the ENV.md config block (written by rh env set)
  tasks.json      task board: phases + steps + subtasks, states idle|working|complete
  logs/ papers/ notes/ tmp/
  workflow.mmd    the project workflow diagram — AUTHORED by the Orchestrator
                  or Researcher (see below); `rh workflow` only displays it
```

Commands agents use per phase:

| Command | Phase | Notes |
|---|---|---|
| `rh init --slug NAME` | 0 | creates the `.rh/` layout; config is still asked per §2 |
| `rh env show` / `env list` | 0–2 | read and validate the config block + environment notes |
| `rh env set KEY=VALUE ...` | 0 | writes ENV.md's block **and** the `.rh/env.json` mirror; preserves the notes below it |
| `rh add note\|literature\|gaps\|log <h> -m "..."` | 3+ | appends under a heading, creating it if missing; literature accepts a DOI |
| `rh search <query>` | any | rg-first local search over `.rh/` + artifacts, no indexing |
| `rh add task / plan import` | 4–6 | mirrors PLAN.md steps into the board (`rh plan import`) |
| `rh task set <id> idle\|working\|complete` | 5–6 | board state; `rh tasks` / `rh status` display it |
| `rh phase <0-9>` | any | **gated**: refuses to advance past unmet exit gates; `--force` is a waiver → record it in STATUS.md (rule 11) |
| `rh resume` / `rh -r` | any | opens the agent harness as the Orchestrator with a go-forward prompt (skill loaded). If backend/agent CLI are unset it asks in the CLI. Pane/spawn bookkeeping is still the Orchestrator's job (§5) |
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
3. **The board mirrors the plan, not the reverse.** `rh plan import` reads
   PLAN.md; replanning (§4) updates PLAN.md first, then re-imports. STATUS.md
   remains the truth (rule 9) — the board is display state for `rh tasks`.
4. **`--json` works on every command** for agent reads; never parse the pretty UI.
