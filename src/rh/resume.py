"""`rh resume` — run the agent harness in THIS terminal with a go-forward prompt.

Flow: load .rh/env.json config (phase-0 gate required) → resolve the launch
command (agents.commands.orchestrator, else agents.cli) → write the short
skill-read prompt to .rh/resume-prompt.md → exec the harness in place, silently.

Exec-in-place is deliberate: the Orchestrator must run where the user called
it. Parallel agents spawned later by the Orchestrator are its own business
(`agents.backend` + the tmux/herdr/tuios skills), not `rh resume`'s.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import ui
from .tasks import TaskStore

AGENT_CLIS = ("pi", "opencode", "claude", "codex", "gemini", "aider", "goose")


def detect_agent_clis() -> list[str]:
    return [c for c in AGENT_CLIS if shutil.which(c)]


def choose_interactively(title: str, options: list[str], *, allow_none: bool = False) -> str | None:
    """Numbered in-CLI picker. Returns choice, or None when 'none' chosen."""
    print(ui.colorize(f"? {title}", ui.BOLD))
    shown = list(options) + (["none (print the prompt instead of spawning)"] if allow_none else [])
    for i, opt in enumerate(shown, 1):
        marker = ui.colorize("  (not on PATH)", ui.YELLOW) if opt.endswith("(not on PATH)") else ""
        print(f"  {i}) {opt}{marker}")
    while True:
        try:
            raw = input(f"  choice [1-{len(shown)}, enter=default 1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw == "":
            raw = "1"
        if raw.isdigit() and 1 <= int(raw) <= len(shown):
            pick = shown[int(raw) - 1]
            if allow_none and pick.startswith("none"):
                return None
            return pick.split(" ")[0]
        print(ui.colorize("  invalid choice", ui.RED))


def next_tasks(store: TaskStore) -> list[dict]:
    """working first, then idle, ordered by phase then id."""
    tasks = store.list()
    prio = {"working": 0, "idle": 1, "complete": 2}
    return sorted(tasks, key=lambda t: (prio.get(t["state"], 3), t["phase"], t["id"]))[:5]


def build_prompt(root: Path, env: dict, gate: dict, store: TaskStore, extra: str = "",
                 include_role_file: bool = False) -> str:
    """The FIRST message the harness receives: load the skill, then follow it.

    Deliberately short. Project state lives in `.rh/CHECKLIST.md` / `rh phase` /
    `.rh/STATUS.md`, so the orchestrator reads it live instead of trusting a
    snapshot printed here. `include_role_file` is the fallback for a launch
    template that does not wire `.rh/agents/orchestrator.md` into the harness
    system prompt: then the role file is prepended to this prompt instead.
    """
    agents = env.get("agents", {}) or {}
    skills = agents.get("skills") or ["research-helper"]
    lines: list[str] = []
    if include_role_file:
        try:
            from . import agents as agents_mod
            role_text = (agents_mod.read_role(root, "orchestrator") or "").strip()
        except (ImportError, OSError):
            role_text = ""
        if role_text:
            lines += [role_text, "", "---", ""]
    lines += [
        f"Load the `{skills[0]}` skill now, then follow it exactly — it is law, not advice.",
        f"Skills for this session (and only these): {', '.join(skills)}.",
        f"Project root: {root}",
        "",
        "Your checklist is `.rh/CHECKLIST.md` — read it first and work it top to bottom.",
        "Then `rh phase` and `.rh/STATUS.md`. Ask the user before every state-changing",
        "action (SKILL.md §0.3).",
    ]
    if extra:
        lines += ["", "User instructions for this session:", extra.strip()]
    return "\n".join(lines)


def resolve_agent_cli(args_cli: str | None, env: dict, *, interactive: bool = True) -> tuple[str | None, bool]:
    cfg = (env.get("agents", {}) or {}).get("cli", "")
    installed = detect_agent_clis()
    pick = args_cli or cfg
    if pick and shutil.which(pick):
        return pick, False
    if not interactive:
        return None, True
    if not installed:
        manual = input("No coding-agent CLI found (pi/claude/opencode/...). Enter command to run: ").strip()
        return (manual or None), True
    pick = choose_interactively("Which agent CLI should run the project?", installed, allow_none=True)
    return pick, True


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
