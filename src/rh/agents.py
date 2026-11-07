"""Per-role agent files — `.rh/agents/<role>.md`.

There is no hardcoded role info anywhere in `rh`. Each role's rules and scope
live only in its `.rh/agents/<role>.md` file. `rh` never invents role content
beyond a minimal scaffold when the Orchestrator asks it to `--write`.

How a role file reaches the agent:

1. `rh spawn <role>` writes `.rh/tmp/spawn-<role>-prompt.md` (the session
   prompt) and points `agents.commands.<role>` at it via `{prompt}` /
   `{prompt_file}`.
2. The same file system puts `.rh/agents/<role>.md` on disk; the command
   template wires it into the CLI's system-prompt area with `{agent_file}`,
   e.g.::

       agents.commands.researcher = pi --model {model} --system-prompt-file {agent_file} --prompt-file {prompt_file}

   or the harness's equivalent (`--append-system-prompt-file`, `--system`,
   `--agent`…). `rh` does not know which flag the harness accepts — the
   Orchestrator writes it in `.rh/ENV.md`, per the harness docs.
3. If a template omits `{agent_file}`, `launch_plan()` warns that the role
   file is not wired into the system prompt.

`rh agents --write` creates the scaffold for every role the Orchestrator
names; `rh agents <role> --write` creates one. The Orchestrator then edits
the file with user approval. Canonical starter roles (written by hand, not
by rh, to `.rh/agents/`):

    orchestrator, literature, researcher, reviewer, critique, writer

File location: `<root>/.rh/agents/<role>.md` (lowercase). Uppercase names
(`RESEARCHER.md`) are accepted on read for harness conventions.
"""
from __future__ import annotations

from pathlib import Path

from . import paths

# Starter roles the Orchestrator may ask rh to scaffold. This is a scaffold
# list only — no role rules, scope, or contracts live here.
STARTER_ROLES = ("orchestrator", "literature", "researcher", "reviewer", "critique", "writer")


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
    for cand in (d / f"{role}.md", d / f"{role.upper()}.md", d / f"{role.capitalize()}.md"):
        if cand.exists():
            return cand
    return None


def default_content(role: str) -> str:
    """Minimal scaffold for a role file. The Orchestrator fills it in with the user."""
    role = (role or "").strip().lower()
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
lives in .rh/ENV.md as agents.commands.<role>; `rh spawn <role>`
uses exactly that command. Wire this file into the harness's
system-prompt flag in that command with {{agent_file}}, e.g.
`--system-prompt-file {{agent_file}}` (or the harness equivalent).
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
