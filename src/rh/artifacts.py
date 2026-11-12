"""What every artifact is — the data behind `rh info <FILE>`.

One entry per Markdown file `rh` knows about: what it is for, who owns it, which
phase creates it, the sections it must have, the template the skill prescribes,
and the rules that bite when writing it. Agents call `rh info <FILE>` instead of
guessing, so this table mirrors SKILL.md §1/§3/§8 — keep them in sync.
"""
from __future__ import annotations

ARTIFACTS: dict[str, dict] = {
    "ENVIRONMENT.md": {
        "purpose": "The environment the user named in phase 2: runtimes, packages, "
                   "simulators, hardware and versions, one line each — the source the "
                   "manuscript's methods section copies verbatim.",
        "location": ".rh/ENVIRONMENT.md (config itself lives in .rh/env.json)",
        "owner": "Orchestrator (interview with the user)",
        "phase": "2 ENVIRONMENT",
        "sections": [
            "## Environment — one line per tool the user named: <name> <version> — what it is for",
            "dated amendments only (`- <date>: <change>`) — never re-type, never probe",
        ],
        "template": "## Environment\n\n"
                    "- meep 1.29.0 — FDTD, 2D/3D (user-confirmed)\n"
                    "- jax — not used; the user prefers numpy on this machine\n"
                    "- custom solver \"foo\" 2.0 — user-named, not on PATH\n",
        "rules": [
            "Never invent a version or a tool: the user names them (SKILL.md §2).",
            "A binary on PATH does not mean this project should use it — ask, do not probe.",
            "Re-read this file at the start of every phase; never cache it (rule 10).",
            "This is the only place versions are written; the manuscript links it.",
            "`rh env set KEY=VALUE` writes .rh/env.json — it never touches this file.",
        ],
        "consumers": "MANUSCRIPT.md methods copy the versions verbatim",
    },
    "PROBLEM.md": {
        "purpose": "Why this work now and what it must answer: the purpose (a reference to "
                   "reproduce, a data check, a Q1 submission, a reproduction…), the research "
                   "question, its boundaries, success criteria and falsifier. Everything later "
                   "must answer this file.",
        "location": "PROBLEM.md",
        "owner": "Orchestrator (interview with the user)",
        "phase": "1 INTAKE",
        "sections": [
            "## Purpose — why this work now: reproduce a reference, check data, publish in a Q1 journal, reproduce a result, answer a reviewer, … (one or two lines)",
            "## Question — one sentence, falsifiable",
            "## Why it matters",
            "## Success criteria — measurable",
            "## Falsifier — what result would kill the claim",
            "## Constraints — time, hardware, data licence",
            "## Out of scope — explicit exclusions",
        ],
        "template": "# Problem — <project name>\n\n## Purpose\n<why now: reproduce / verify / publish / …>\n\n## Question\n<one sentence>\n\n## Why it matters\n...\n\n"
                    "## Success criteria\n- <measurable>\n\n## Falsifier\n<what would refute it>\n\n"
                    "## Constraints\n- <time/hardware/licence>\n\n## Out of scope\n- <excluded>",
        "rules": [
            "Seven sections, all non-empty; the user approves it before phase 1 exits.",
            "Ask the purpose; never infer it from the topic (SKILL.md §3 phase 1).",
            "Scope changes go back here first — never silently in PLAN.md.",
        ],
        "consumers": "PLAN.md, OUTPUT_LAYOUT.md, MANUSCRIPT.md",
    },
    "LITERATURE.md": {
        "purpose": "What we took from each paper we actually read: citation, DOI, relevance, "
                   "exactly what we take or reject, and page anchors — so a claim can be cited "
                   "later without re-reading.",
        "location": "LITERATURE.md",
        "owner": "Literature",
        "phase": "3 LITERATURE",
        "sections": [
            "## <citation> — DOI anchor per paper (`## <paper>` with `DOI: 10.x/...`)",
            ("per paper: relevance · what we take (method/number/parameter) · what we reject "
             "and why · page/section anchors"),
            "## Not obtained — paywalled papers the user could not supply",
        ],
        "template": "## Smith 2023 — graphene thermal model\n\nDOI: 10.1234/abcd\n\n"
                    "- relevance: <one paragraph>\n- take: <method/number/parameter>\n"
                    "- reject: <what and why>\n- anchors: §3 p.5, Eq. 4\n",
        "rules": [
            "One DOI line per entry — a finding without its DOI cannot be cited (SKILL.md §3).",
            "Never paraphrase a paper you have not read; paywalled → ask the user for the PDF.",
            "Never substitute a different paper for an unobtainable one.",
        ],
        "consumers": "OUTPUT_LAYOUT.md pattern tally, PLAN.md, MANUSCRIPT.md",
    },
    "OUTPUT_LAYOUT.md": {
        "purpose": "The skeleton of the deliverable: one layout (headings, topics, equations, "
                   "figures) derived from a tally of what comparable papers do — the Writer "
                   "opens MANUSCRIPT.md with exactly these headings.",
        "location": "OUTPUT_LAYOUT.md",
        "owner": "Literature (Researcher appends from sources it reads)",
        "phase": "3 LITERATURE and later",
        "sections": [
            "Target line — what the user asked for (manuscript | report | letter), venue, length",
            "## Patterns in comparable papers — table: pattern | papers | count | note",
            "## Per paper — table: DOI | copy/avoid | equations | figures | emphasis | never shows",
            "## Our layout — exactly ONE layout, one `### <n> <heading>` per section",
        ],
        "template": "# Output layout — <manuscript | report | ...>\n\n"
                    "Target: <what the user asked> | Venue: <if named> | Length: <target>\n\n"
                    "## Patterns in comparable papers\n| pattern | papers | count | note |\n"
                    "|---|---|---|---|\n| setup schematic as Fig 1 | A, B | 2 | labelled a–d |\n\n"
                    "## Per paper\n| paper (DOI) | copy / avoid | equations | figures | emphasis | never shows |\n"
                    "|---|---|---|---|---|---|\n| 10.1234/abcd | theory first | Eq. 1 in Methods | "
                    "Fig 1 schematic | intuition then derivation | error bars |\n\n"
                    "## Our layout\n### 1 <Section heading>\n- purpose: ...\n- topics: ...\n"
                    "- equations: ...\n- figures/tables: Fig 1 <what> (axes/units) — data: <results/file>\n"
                    "- evidence: <results/S05.csv | 10.1234/abcd §3>\n"
                    "- status: <have data | data missing → step>",
        "rules": [
            "Two layouts in the file is a defect — fold every note into the single layout.",
            "Every layout edit names the paper (DOI) that drove it.",
            "Ask if the output type is unclear; never impose a paper structure the user did not want.",
            "If the deliverable is not a manuscript/report, this file may not exist at all.",
        ],
        "consumers": "MANUSCRIPT.md heading order, Writer",
    },
    "GAPS.md": {
        "purpose": "Implementation sourcing: which repo or paper each borrowed piece comes from, "
                   "the licence, what upstream is missing, who to credit, and whether an upstream "
                   "fix/PR is warranted.",
        "location": "GAPS.md",
        "owner": "Literature / Researcher",
        "phase": "3 LITERATURE and later",
        "sections": [
            "## <source> — repo/paper, licence, what we borrow",
            "gaps — what the source does not provide and how we fill it",
            "credit / upstream — who to cite, whether to send a fix upstream",
        ],
        "template": "## <repo or paper> — <url/DOI>\n\n- licence: <MIT | …>\n"
                    "- we borrow: <function/module/equation>\n- upstream gaps: <what is missing>\n"
                    "- credit: <who to cite>\n- upstream fix warranted: <yes/no + why>",
        "rules": [
            "Only code actually read goes here; suspicious code goes to the Orchestrator or Critique.",
            "Never re-type versions — link .rh/ENVIRONMENT.md.",
        ],
        "consumers": "MANUSCRIPT.md attribution, PLAN.md risk",
    },
    "PLAN.md": {
        "purpose": "The approved step list — each step with owner, deliverable, verification "
                   "command, dependencies and risk. Nothing is implemented before the user "
                   "approves this file.",
        "location": "PLAN.md",
        "owner": "the two Planners agree; the Orchestrator merges; the user approves — with no "
                 "planner configured (`agents.planners.models = none`) the user writes it and "
                 "the Orchestrator reconciles it",
        "phase": "4 PLAN (re-opened by replanning from 6/7)",
        "sections": [
            "### S<N> — <action> — one step per heading (ids like S04b are valid); a general "
            "Markdown plan is accepted too (see rules)",
            "step fields (all optional): owner · deliverable · verify · depends on · risk · "
            "kind (build|spike) · timebox",
            "subtasks — bullet lines under a step (`- [ ] profile one cell`)",
            "tooling — link .rh/ENVIRONMENT.md, never copy its versions",
            "agreement line — `agreed by <model> / <model> on <date>` (waived where the user plans)",
        ],
        "template": "### S07 — <action>\nowner: researcher | deliverable: results/S07.csv\n"
                    "verify: `uv run pytest tests/test_s07.py`\ndepends on: S05 | risk: <what could "
                    "invalidate it> | kind: build | spike\ntimebox: 90m   # only for kind: spike\n"
                    "- subtask one\n- [ ] subtask two",
        "rules": [
            "Two planners on different models agree, then the user approves (gates.user_approves_plan).",
            "Every step needs a verification command or check — \"looks right\" is not one.",
            "The board is created **explicitly**: whoever owns this file turns each step into a task "
            "with `rh add task \"<title>\" --id S0N --deliverable … --verify … --subtask …` — there is no "
            "parser, because the plan is prose and the board must not guess.",
            "Shape is free: the file is read by people and agents, not parsed. Write it as prose, "
            "a numbered list or headings — nothing is lost by not matching a template.",
            "Who keeps the board in sync: the agent that writes this file creates its own tasks; a "
            "user-written plan has its tasks created by the Orchestrator.",
            "No planner configured (`rh env set agents.planners.models=none`) means the user is "
            "the planner: the phase-4 gate reads user-authored + user approval, `rh doctor` and "
            "`rh env show` say so, and no planner pane is ever opened.",
        ],
        "consumers": "tasks.json (created with `rh add task`), STATUS.md, MANUSCRIPT.md",
    },
    "STATUS.md": {
        "purpose": "The truth about where the project is: current phase and step, the agent "
                   "roster, blockers, open questions for the user, and a timestamped history.",
        "location": "STATUS.md",
        "owner": "Orchestrator only (never delegated — rule 9)",
        "phase": "5 STATE and later",
        "sections": [
            "header line — `phase: <n NAME> | step: <id> | updated: <ISO>`",
            "agents — role → model → backend window",
            "blockers · open questions for user (numbered, answerable in one line)",
            "history — one line per step transition, timestamped",
        ],
        "template": "# Status — <project name>\nphase: 6 IMPLEMENT | step: S07 | updated: <ISO>\n"
                    "agents: orchestrator=<model>  researcher=<model>  (backend: tmux window 2)\n"
                    "blockers: none\nopen questions for user: (numbered, answerable in one line)\n"
                    "history:\n- <ISO> S06 done, tests green (24 passed), results/S06.csv",
        "rules": [
            "Update after every step and before every question to the user (rule 9).",
            "A waiver of a SKILL.md rule is recorded here by number (rule 11).",
            "Spawn and close of every agent is recorded here (rules 12–13).",
        ],
        "consumers": "the resume handoff, the phase gate (`rh status`), the user",
    },
    "HANDOFF.md": {
        "purpose": "What the next session must do first. Written by the Orchestrator at the "
                   "end of a session, never generated from STATUS/PLAN: it is a decision about "
                   "the next move, not a status dump.",
        "location": ".rh/HANDOFF.md (always under .rh/)",
        "owner": "Orchestrator only",
        "phase": "any — written when a session ends (rule 14)",
        "sections": [
            "## Next session — the first thing to do, and why",
            "## Watch out — blockers, open questions, a trap the last session hit",
        ],
        "template": "# Handoff — <date>\n\n## Next session\n- <first action>\n\n## Watch out\n- <blocker / open question>\n",
        "rules": [
            "Empty at `rh init`; an empty file means nothing was handed over.",
            "`rh resume` reads it only when it has content, then the Orchestrator clears it "
            "with `rh handoff --clear` (rule 14).",
            "Never list what STATUS.md already says; the handoff is what to do next, not where we are.",
            "Never generate it automatically from other artifacts — a handoff is authored.",
        ],
        "consumers": "`rh resume` (first session prompt), the next Orchestrator",
    },
    "MANUSCRIPT.md": {
        "purpose": "The write-up: drafted from artifacts only, following the single layout in "
                   "OUTPUT_LAYOUT.md, with an evidence line for every claim.",
        "location": "MANUSCRIPT.md",
        "owner": "Writer (Reviewer checks, Critique signs off)",
        "phase": "8 MANUSCRIPT",
        "sections": [
            "the headings of the single layout in OUTPUT_LAYOUT.md, in that order",
            "## Limitations — includes every waived rule",
            "## Data availability — results/ files and the scripts that made them",
        ],
        "template": "# <title>\n\n## 1 <Section heading from OUTPUT_LAYOUT.md>\n<prose>\n\n"
                    "<!-- evidence: results/S05.csv | 10.1234/abcd §3 -->\n",
        "rules": [
            "No result without a file: an unsupported number does not exist (rule 7).",
            "Methods cite .rh/ENVIRONMENT.md versions; never re-type them.",
            "Every borrowed implementation is attributed via GAPS.md.",
            "Missing evidence is a hard stop — delete the claim, never soften it.",
        ],
        "consumers": "the user, phase 9 CLOSE",
    },
}


def resolve(name: str) -> str | None:
    """Map a typed name onto an artifact key (`status`, `STATUS`, `status.md`, `.rh/status.md`)."""
    raw = str(name or "").strip().strip("`").strip()
    if not raw:
        return None
    lookup = {k.lower(): k for k in ARTIFACTS}
    stem = raw.lower().removeprefix(".rh/")
    if stem in lookup:
        return lookup[stem]
    if not stem.endswith(".md"):
        stem = f"{stem}.md"
    return lookup.get(stem)


def names() -> list[str]:
    """Artifact names in pipeline order: ENVIRONMENT.md first, then one per phase."""
    order = ["ENVIRONMENT.md", "PROBLEM.md", "LITERATURE.md", "OUTPUT_LAYOUT.md", "GAPS.md",
             "PLAN.md", "STATUS.md", "HANDOFF.md", "MANUSCRIPT.md"]
    return [n for n in order if n in ARTIFACTS]


