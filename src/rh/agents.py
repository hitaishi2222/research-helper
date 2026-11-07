"""Per-role agent files — `.rh/agents/<role>.md`.

There is no hardcoded role info anywhere in `rh`. Each role's rules and scope
live only in its `.rh/agents/<role>.md` file. `rh` never invents role scope beyond
a starter file: the orchestrator starter carries the SKILL.md §5 contract (it is
the head of the project), the other roles get a minimal scaffold to fill in.

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

# Starter roles `rh init` writes. Only the orchestrator starter carries a
# contract (SKILL.md §5); the rest are scaffolds the Orchestrator fills in.
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
- ask before every state-changing action; a waiver is recorded in STATUS.md by rule number;
- update STATUS.md yourself after every step, before every question (rule 9);
- verify the project path before opening an agent (rule 12) and close it after (rule 13);
- report back with files changed, evidence (command + number), and needs.

The launch command for this role lives in `.rh/env.json` as
agents.commands.orchestrator; `rh resume` uses exactly that command and
wires this file into the harness's system-prompt area with {agent_file}.
"""


def default_content(role: str) -> str:
    """Starter content for a role file. The Orchestrator fills the rest in with the user."""
    role = (role or "").strip().lower()
    if role == "orchestrator":
        return ORCHESTRATOR_CONTENT
    return f"""# {role.upper()} agent

Role: <what this agent is for — one sentence>

Owns: <artifacts and directories this role may write>
May: <what this role may do>
May not: <what this role must not do>

Rules carried into every session:
- follow the research-helper skill exactly (SKILL.md §0 non-negotiables);
- ask before every state-changing action;
- report back with files changed, evidence (command + number), and needs;
- never update STATUS.md unless you are the Orchestrator.

Edit this file with user approval. The launch command for this role
lives in .rh/env.json as agents.commands.<role>; `rh spawn <role>`
uses exactly that command. Wire this file into the harness's
system-prompt area in that command with {{agent_file}}, e.g.
`--append-system-prompt {{agent_file}}` (never a replacing flag), and pass the
prompt positionally with {{prompt}} (or the harness equivalent).
"""


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


def write_all(root: Path) -> list[Path]:
    d = agents_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for role in STARTER_ROLES:
        p = role_file(root, role)
        if not p.exists():
            p.write_text(default_content(role), encoding="utf-8")
            written.append(p)
    return written


def write_one(root: Path, role: str) -> Path:
    d = agents_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = role_file(root, role)
    if not p.exists():
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
