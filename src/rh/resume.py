"""`rh resume` — run the agent harness in THIS terminal with a go-forward prompt.

Flow: load .rh/ENV.md config (phase-0 gate required) → pick agent CLI (config
`agents.cli`, else the detected one, else ask) → build the prompt from live
project state → write .rh/resume-prompt.md → exec the agent in place.

Exec-in-place is deliberate: the Orchestrator must run where the user called
it. Parallel agents spawned later by the Orchestrator are its own business
(`agents.backend` + the tmux/herdr/tuios skills), not `rh resume`'s.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import paths, ui
from .tasks import TaskStore, phase_name

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


def build_prompt(root: Path, env: dict, gate: dict, store: TaskStore, extra: str = "") -> str:
    project_name = env.get("project", {}).get("name") or "untitled"
    agents = env.get("agents", {}) or {}
    skills = agents.get("skills") or ["research-helper"]
    orch = (agents.get("roles") or {}).get("orchestrator") or {}
    if not isinstance(orch, dict):
        orch = {}
    model = str(orch.get("model") or "")
    provider = str(orch.get("provider") or "")
    thinking = str(orch.get("thinking") or "")
    session = (f"{provider}/{model}" if provider and model else model) or "not set in .rh/ENV.md"
    if thinking:
        session += f" · thinking: {thinking}"
    current = gate["phase"]
    lines = [
        f"You are the Orchestrator for the research project '{project_name}'.",
        f"Project root (verify you are here before writing anything): {root}",
        f"Session model (agents.roles.orchestrator): {session}",
        "",
        "Load exactly these skills for this session, and no others — nothing else,",
        "so the context stays small and the pipeline stays authoritative:",
    ]
    lines += [f"  - {s}" for s in skills]
    lines += [
        "Then follow the research-helper skill exactly — it is law, not advice",
        "(SKILL.md §0 non-negotiables; ask before every state-changing action).",
        "",
        f"Current phase: {phase_name(current)}",
    ]

    if gate["problems"]:
        lines.append("Unmet gates (resolve these first, or ask the user to waive):")
        lines += [f"  - {p}" for p in gate["problems"]]
    else:
        lines.append("Gates: all satisfied for the current phase.")
    tasks = next_tasks(store)
    if tasks:
        lines.append("Next tasks:")
        lines += [f"  - [{t['state']}] {t['id']} {t['title']}" for t in tasks]
    else:
        lines.append("No tasks on the board — mirror PLAN.md steps (`rh plan import`) or proceed by phase.")
    lines += [
        "",
        "Start by re-reading, never caching (SKILL.md §0 rules 9 and 10):",
        f"  - {paths.env_md(root)} (config block + environment notes)",
        f"  - {paths.artifact_path(root, 'STATUS.md')}" if paths.artifact_path(root, "STATUS.md").exists()
        else "  - STATUS.md (does not exist yet — create it in phase 5, not before)",
        "  - `rh info <FILE.md>` describes any artifact before you write it",
        "",
        "Then continue the pipeline from the current phase. Do not skip exit gates;",
        "do not pick models (they live in the ENV.md config block).",
        "You own STATUS.md — update it yourself after every step; never delegate that.",
        "",
        "To put another role to work, use the launch commands from .rh/ENV.md:",
        "  rh spawn <role> \"<instructions>\"      # literature | researcher | reviewer | critique | writer",
    ]
    if extra:
        lines += ["", "User instructions for this session:", extra]
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
