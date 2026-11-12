"""Per-role agent files — `.rh/agents/<role>.md`.

There is no hardcoded role info anywhere in `rh`. Each role's rules and scope
live only in its `.rh/agents/<role>.md` file. `rh` never invents role scope beyond
a starter file: every starter carries the SKILL.md §5 row for that role — the
job and its boundary, generalized — so a fresh `rh init` produces usable role
files. Project facts (paths, tools, phases, output names) stay out of them: the
TAILOR block in each file tells the Orchestrator to narrow it with the user.

How a role file reaches the agent:

1. `rh spawn <role>` writes `.rh/tmp/spawn-<role>-prompt.md` (the session
   prompt) and points `agents.commands.<role>` at it via `{prompt}` /
   `{prompt_file}`.
2. The same file system puts `.rh/agents/<role>.md` on disk; the command
   template wires it into the CLI's system-prompt area with `{agent_file}`,
   e.g.::

       agents.commands.researcher = pi --model {model} --append-system-prompt {agent_file} {prompt}

   or the harness's equivalent (`--append-system-prompt-file`, `--system`,
   `--agent`…). `rh` does not know which flag the harness accepts — the
   Orchestrator writes it in `.rh/env.json`, per the harness docs.
3. If a template omits `{agent_file}`, `launch_plan()` warns that the role
   file is not wired into the system prompt.

`rh init` writes the starter roles below; `rh agents <role> --write` creates one
later, and `rh agents --write` fills in any that are missing. The Orchestrator
then edits the file with user approval. Starter roles:

    orchestrator, literature, researcher, reviewer, critique, writer

File location: `<root>/.rh/agents/<role>.md` (lowercase). Uppercase names
(`RESEARCHER.md`) are accepted on read for harness conventions.
"""

from __future__ import annotations

from pathlib import Path

from . import paths

# Starter roles `rh init` writes. Every one carries its SKILL.md §5 scope; the
# Orchestrator narrows it for the project with user approval.
STARTER_ROLES = (
    "orchestrator",
    "literature",
    "researcher",
    "reviewer",
    "critique",
    "writer",
)


def agents_dir(root: Path) -> Path:
    return paths.rh_dir(root) / "agents"


def role_file(root: Path, role: str) -> Path:
    role = (role or "").strip().lower()
    return agents_dir(root) / f"{role}.md"


def _resolve_existing(root: Path, role: str) -> Path | None:
    role = (role or "").strip().lower()
    if not role:
        return None
    d = agents_dir(root)
    for cand in (
        d / f"{role}.md",
        d / f"{role.upper()}.md",
        d / f"{role.capitalize()}.md",
    ):
        if cand.exists():
            return cand
    return None


ORCHESTRATOR_CONTENT = """# ORCHESTRATOR agent

Role: the head of this project — routing, gates, every question to the user, and the singular owner of STATUS.md.
Owns: routing, `.rh/STATUS.md`, merged `.rh/PLAN.md`, the roster, all user questions.
May: delegate (`rh spawn <role>`), enforce gates (`rh phase`), escalate, edit artifacts.
May not: implement or fix code, approve its own plan, pick models (they live in `.rh/env.json`).

Rules carried into every session:
- load the research-helper skill first; SKILL.md §0 and §5 are your contract;
- your checklist is `.rh/CHECKLIST.md` — read it first, then work it top to bottom:
  fill missing environment values by asking the user, wire the launch commands,
  and author `.rh/workflow.mmd` once the plan is approved;
- ask the user for the purpose of this work in phase 1 (reference to reproduce,
  data check, Q1 submission, reproduction, …) and record it in PROBLEM.md first;
- before spawning, name every pane/window `rh-<project>-<role>` (agents.spawn
  uses `{project}` and `{agent}`) so two projects never clash; address an agent
  by that name when you send it work;
- when a session ends, write `.rh/HANDOFF.md` yourself: what the next session must
  do first. Never generate it from STATUS.md/PLAN.md, and empty it after reading;
- ask before every state-changing action; a waiver is recorded in STATUS.md by rule number;
- update STATUS.md yourself after every step, before every question (rule 9);
- verify the project path before opening an agent (rule 12) and close it after (rule 13);
- report back with files changed, evidence (command + number), and needs.

The launch command for this role lives in `.rh/env.json` as
agents.commands.orchestrator; `rh resume` uses exactly that command and
wires this file into the harness's system-prompt area with {agent_file}.
"""


ROLE_FOOTER = """
Rules carried into every session:
- load the research-helper skill first; SKILL.md §0 (non-negotiables) binds you;
- your backend name is `rh-<project>-<role>`: use it to identify yourself when you
  talk to the Orchestrator or the user;
- ask before every state-changing action; skip nothing from SKILL.md §6;
- write only inside the files this role owns — everything else is read-only;
- report back with files changed, evidence (command + number), and needs;
- never update STATUS.md unless you are the Orchestrator.

The launch command for this role lives in `.rh/env.json` as
agents.commands.{role}; `rh spawn {role}` uses exactly that command and wires
this file into the harness's system-prompt area with {{agent_file}}. If the
command has no {{agent_file}} slot, say so — the role file is not being read.
"""

# SKILL.md §5's role table, generalized: the job and its boundary, never project
# facts. Paths, tools, phases and output names differ per project, so the
# Orchestrator narrows them with the user — every starter carries TAILOR to say so.
ROLE_SCOPE = {
    "literature": (
        "reads the sources and records what we take from them — the only role that may "
        "call a source 'read'.",
        "the project's source library and literature record (paths: SKILL.md §1)",
        "fetch open-access sources, read them, record what we take and what we do not, "
        "propose the layout of the output the user asked for",
        "summarize a source it has not read, substitute one reference for another, or "
        "change the plan",
    ),
    "researcher": (
        "implements and measures — work in, numbers out.",
        "the project's implementation and result files (paths: SKILL.md §1)",
        "implement, test, run experiments, probe the tools the environment record names, "
        "ask for guidance when the plan does not fit reality",
        "change scope, delete files it did not create, install system packages, weaken a "
        "test, or report a number it did not measure",
    ),
    "reviewer": (
        "independent review of work it did not produce — findings, never fixes.",
        "its own review verdicts",
        "read everything, reproduce what it can, file findings ranked by severity, demand "
        "evidence (file and line, command and number)",
        "fix what it finds, accept an unreproduced claim, or soften a finding to keep the "
        "peace — independence is the whole point",
    ),
    "critique": (
        "the blocking-question list and the veto — the role that must try to kill the "
        "work.",
        "the blocking-question list it hands to the Orchestrator",
        "question anything, block a gate, demand falsification (which result would prove "
        "this wrong?), name what the work assumes without testing",
        "implement, soften its own findings, or block without naming what would settle it",
    ),
    "writer": (
        "the written output — claims, prose and figures that already exist as evidence.",
        "the project's manuscript or report file (path: SKILL.md §1)",
        "draft, restructure, cite from the project's own results and literature record",
        "introduce evidence the project does not have, invent a citation, describe a "
        "figure or run that does not exist, or state a result more strongly than the "
        "measurement",
    ),
}

TAILOR = """
Tailor for this project (Orchestrator, with the user — edit this file, keep the rules):
- narrow *Owns* to the exact paths this project uses;
- name the tools this role may run here, as the environment record lists them;
- say when the role is opened: the phase, and the step of `.rh/CHECKLIST.md`;
- leave project facts (models, commands, paths, budget) in `.rh/env.json` and
  `PLAN.md`; this file is about how the role works, not what this project decided.
"""


def default_content(role: str) -> str:
    """Starter content for a role file: role + boundary, generalized (no project facts)."""
    role = (role or "").strip().lower()
    if role == "orchestrator":
        return ORCHESTRATOR_CONTENT + TAILOR
    scope = ROLE_SCOPE.get(role)
    if scope is None:
        # a role the skill does not define yet: minimal but non-empty
        return (
            f"# {role.upper()} agent\n\n"
            f"Role: <name the job and the phase it serves>\n"
            f"Owns: <files this role may write>\n"
            f"May: <actions allowed>\n"
            f"May not: <actions refused>\n"
            + ROLE_FOOTER.format(role=role)
            + TAILOR
        )
    purpose, owns, may, may_not = scope
    return (
        f"# {role.upper()} agent\n\n"
        f"Role: {purpose}\n"
        f"Owns: {owns}\n"
        f"May: {may}.\n"
        f"May not: {may_not}.\n"
        + ROLE_FOOTER.format(role=role)
        + TAILOR
    )


def read_role(root: Path, role: str) -> str | None:
    p = _resolve_existing(root, role)
    if p is None:
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def list_roles(root: Path) -> list[str]:
    names: set[str] = set(STARTER_ROLES)
    d = agents_dir(root)
    if d.is_dir():
        for f in d.iterdir():
            if f.suffix.lower() == ".md":
                names.add(f.stem.lower())
    return sorted(names)


# Marker of the pre-0.1.5 blank scaffold ("Role: <what this agent is for ...>").
# A file still carrying it was never edited, so it is safe to replace with the
# populated starter; a file the Orchestrator has edited is left alone.
_STUB_MARK = "Role: <what this agent is for"


def _is_old_stub(p: Path) -> bool:
    try:
        return _STUB_MARK in p.read_text(encoding="utf-8")
    except OSError:
        return False


def write_all(root: Path) -> list[Path]:
    d = agents_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for role in STARTER_ROLES:
        p = role_file(root, role)
        if not p.exists() or _is_old_stub(p):
            p.write_text(default_content(role), encoding="utf-8")
            written.append(p)
    return written


def write_one(root: Path, role: str) -> Path:
    d = agents_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = role_file(root, role)
    if not p.exists() or _is_old_stub(p):
        p.write_text(default_content(role), encoding="utf-8")
    return p


def role_file_info(root: Path, role: str) -> dict:
    role = (role or "").strip().lower()
    p = role_file(root, role)
    existing = _resolve_existing(root, role)
    return {
        "role": role,
        "file": str(existing) if existing else str(p),
        "exists": existing is not None,
    }
