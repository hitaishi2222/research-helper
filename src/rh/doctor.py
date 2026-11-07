"""`rh doctor` — verify what env.json names actually works on this machine.

Checks are by name only: does the binary, shell, or file env.json names exist?
`rh doctor` never decides what the user should use — it only reports whether
the named thing is where the command expects it to be.
"""
from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from . import agents as agents_mod
from . import config, paths
from .spawn import detect_shell


def _bin_ok(name: str) -> tuple[bool, str]:
    if not name:
        return False, "not set"
    if shutil.which(name):
        return True, shutil.which(name) or name
    if Path(name).is_file() and Path(name).stat().st_mode & 0o111:
        return True, name
    return False, f"not found: {name}"


def check(root: Path, env: dict | None = None) -> dict:
    """Run every doctor check. Returns {root, ok, checks:[{id, ok, detail}]}."""
    env = env if env is not None else config.load_env(root)
    c: list[dict] = []

    def add(id_: str, ok: bool, detail: str):
        c.append({"id": id_, "ok": ok, "detail": detail})

    # workspace
    rh = paths.rh_dir(root)
    add("workspace", rh.is_dir(), f".rh/ at {rh}" if rh.is_dir() else f"{rh} missing — run `rh init`")
    # config: the single file `rh env set` writes
    env_file = paths.env_json(root)
    add("env-json", env_file.exists() and config.config_written(root),
        str(env_file) if env_file.exists() else f"{env_file} missing — run `rh init` / phase 0")

    # shell: agents.shell, else $SHELL, else sh — named shell verifies on PATH
    shell = detect_shell(env)
    ok, path = _bin_ok(shell)
    add("shell", ok, f"{shell} → {path}")

    # split: valid or blank (blank = ask user; not an error)
    split = str((env.get("agents") or {}).get("split") or "").strip()
    add("split", split == "" or split in ("vertical", "horizontal", "window"),
        split or "blank — Orchestrator asks the user at spawn")

    # agents.count
    count = (env.get("agents") or {}).get("count")
    add("count", count in (1, 2, 3, 4), f"agents.count = {count!r}")

    # per-role commands: template present, splittable, has {agent_file}, role file exists
    cmds = (env.get("agents") or {}).get("commands") or {}
    if not isinstance(cmds, dict):
        cmds = {}
    named_roles = [r for r in cmds if r != "default"]
    command_roles: set[str] = set()
    configured = 0
    for role in sorted(named_roles):
        tmpl = cmds.get(role)
        if not isinstance(tmpl, str) or not tmpl.strip():
            continue
        configured += 1
        try:
            toks = shlex.split(tmpl)
            first = toks[0] if toks else ""
        except ValueError as exc:
            add(f"commands.{role}", False, f"{role}: template not shell-splittable: {exc}")
            continue
        # binary check: first token is usually the harness binary name
        ok, where = _bin_ok(first) if first and "{" not in first else (True, "placeholder binary")
        if not ok:
            add(f"commands.{role}.binary", False, f"{role}: {where}")
        else:
            add(f"commands.{role}.binary", True, f"{role}: {where}")
        has_agent = "{agent_file}" in tmpl
        has_prompt = "{prompt}" in tmpl or "{prompt_file}" in tmpl
        add(f"commands.{role}.placeholders", has_agent and has_prompt,
            f"{role}: has agent_file={has_agent} prompt={has_prompt}")
        command_roles.add(role)

    # role files: a role with a launch command or a configured model must have
    # its `.rh/agents/<role>.md` — that file *is* the role, nothing is hardcoded.
    configured_roles = {r for r, spec in ((env.get("agents") or {}).get("roles") or {}).items()
                        if isinstance(spec, dict) and any(str(v).strip() for v in spec.values())}
    for role in sorted(command_roles | configured_roles):
        role_ok = agents_mod.read_role(root, role) is not None
        add(f"role-file.{role}", role_ok,
            f".rh/agents/{role}.md" + ("" if role_ok else " missing — `rh agents <role> --write`, then fill it in with the user"))
    if not configured:
        add("commands", False,
            "no agents.commands.<role> template set — rh resume/spawn have nothing to run; "
            "pick a harness at `rh init` or add one (`rh env set agents.commands.orchestrator=...`)")

    # spawn template splittable
    spawn_tmpl = (env.get("agents") or {}).get("spawn") or ""
    if spawn_tmpl.strip():
        try:
            shlex.split(spawn_tmpl)
            add("spawn-template", True, "agents.spawn is shell-splittable")
        except ValueError as exc:
            add("spawn-template", False, f"agents.spawn: {exc}")
    else:
        add("spawn-template", True, "agents.spawn blank — detached process + .rh/logs/ log")

    # backend binary (tmux / herdr) when named
    backend = (env.get("agents") or {}).get("backend") or "none"
    if backend in ("tmux", "herdr"):
        ok, where = _bin_ok(backend)
        add("backend", ok, f"{backend} → {where}")
    else:
        add("backend", True, f"agents.backend={backend}")

    # cli fallback binary
    cli = str((env.get("agents") or {}).get("cli") or "").strip()
    if cli:
        ok, where = _bin_ok(cli)
        add("cli", ok, f"agents.cli={cli} → {where}")

    # config valid
    problems = config.validate(env)
    add("config", not problems, "; ".join(problems) if problems else "config valid")

    ok_all = all(x["ok"] for x in c)
    return {"root": str(root), "ok": ok_all, "checks": c, "failures": sum(1 for x in c if not x["ok"])}
