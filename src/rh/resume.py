"""`rh resume` — spawn a configured harness running the agent with a go-forward prompt.

Flow: load ENV.md config (phase-0 gate required) → pick harness backend
(config `agents.backend`, else interactive choice of installed: tmux/herdr/
tuios) → pick agent CLI (config `agents.cli`, else detected: opencode/claude/
codex/...) → build prompt from live project state → write .rh/resume-prompt.md
+ .rh/tmp/resume.sh → spawn pane → record spawn in STATUS.md.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config, paths, ui
from .tasks import TaskStore, phase_name

HARNESS_BINS = {"tmux": "tmux", "herdr": "herdr", "tuios": "tuios"}
AGENT_CLIS = ("opencode", "claude", "codex", "gemini", "aider", "goose")


def detect_harnesses() -> list[str]:
    return [name for name, binary in HARNESS_BINS.items() if shutil.which(binary)]


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
    slug = env.get("project", {}).get("slug") or "untitled"
    current = gate["phase"]
    lines = [
        f"You are the Orchestrator for the research project '{slug}' at {root}.",
        "",
        "Load the research-helper skill and follow it exactly — it is law, not advice",
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
        f"  - {paths.artifact_path(root, 'ENV.md')} (config block + environment notes)",
        f"  - {paths.artifact_path(root, 'STATUS.md')}" if paths.artifact_path(root, "STATUS.md").exists() else "  - STATUS.md (does not exist yet — create it in phase 5, not before)",
        "",
        "Then continue the pipeline from the current phase. Do not skip exit gates;",
        "do not pick models (they live in the ENV.md config block).",
    ]
    if extra:
        lines += ["", "User instructions for this session:", extra]
    return "\n".join(lines)


def write_launcher(root: Path, agent_cli: str, prompt_file: Path) -> Path:
    script = paths.rh_dir(root) / "tmp" / "resume.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env bash\n"
        f"cd {shlex.quote(str(root))}\n"
        f"exec {agent_cli} \"$(cat {shlex.quote(str(prompt_file))})\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def launch(backend: str, root: Path, script: Path, slug: str) -> tuple[bool, str]:
    """Spawn the pane. Returns (ok, detail)."""
    name = f"rh-{slug}"
    try:
        if backend == "tmux":
            if os.environ.get("TMUX"):
                cmd = ["tmux", "new-window", "-c", str(root), "-n", name, "--", "bash", str(script)]
                subprocess.run(cmd, check=True, timeout=15)
                return True, f"tmux window '{name}' opened (inside tmux)"
            session = name
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session, "-c", str(root), "bash", str(script)],
                check=True, timeout=15,
            )
            return True, f"detached tmux session '{session}' — attach: tmux attach -t {session}"
        if backend == "herdr":
            cmd = ["herdr", "tab", "create", "--cwd", str(root), "--label", name, "--", "bash", str(script)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode != 0:
                return False, f"herdr tab create failed: {(proc.stderr or proc.stdout).strip()[:200]}"
            return True, f"herdr tab '{name}' created"
        if backend == "tuios":
            session = os.environ.get("TUIOS_SESSION")
            if not session:
                return False, "tuios: not inside a tuios session ($TUIOS_SESSION unset); use tmux or herdr"
            cmd = ["tuios", "new-window", "-s", session, name, "--no-focus", "--", "bash", str(script)]
            subprocess.run(cmd, check=True, timeout=15)
            return True, f"tuios window '{name}' opened in session {session}"
    except FileNotFoundError as e:
        return False, f"{backend} not found: {e.filename}"
    except subprocess.CalledProcessError as e:
        err = (getattr(e, "stderr", "") or "") or e.returncode
        return False, f"{backend} exited {e.returncode}: {str(err)[:200]}"
    except subprocess.TimeoutExpired:
        return False, f"{backend} timed out"
    return False, f"unknown backend {backend!r}"


def resolve_backend(args_backend: str | None, env: dict, *, interactive: bool = True) -> tuple[str | None, bool]:
    """Returns (backend, changed).

    Interactive whenever the config value is missing/default ('none') or not
    installed — the user chooses in the CLI itself. Explicit --backend wins.
    (None, True) with interactive=False means 'would ask' (dry-run).
    """
    cfg = (env.get("agents", {}) or {}).get("backend", "")
    installed = detect_harnesses()
    pick = args_backend or cfg
    if args_backend == "none":
        return None, False
    if pick and pick != "none" and pick in installed:
        return pick, False
    if not interactive:
        return None, True
    if not installed:
        print(ui.colorize("No agent harness found (tmux/herdr/tuios). Printing the prompt instead.", ui.YELLOW))
        return None, True
    pick = choose_interactively("Which agent harness should rh spawn?", installed + (
        [f"{b} (not on PATH)" for b in HARNESS_BINS if b not in installed]
    ), allow_none=True)
    return pick, True


def resolve_agent_cli(args_cli: str | None, env: dict, *, interactive: bool = True) -> tuple[str | None, bool]:
    cfg = (env.get("agents", {}) or {}).get("cli", "")
    installed = detect_agent_clis()
    pick = args_cli or cfg
    if pick and shutil.which(pick):
        return pick, False
    if not interactive:
        return None, True
    if not installed:
        manual = input("No coding-agent CLI found (opencode/claude/codex/...). Enter command to run: ").strip()
        return (manual or None), True
    pick = choose_interactively("Which agent CLI should run the project?", installed, allow_none=True)
    return pick, True
