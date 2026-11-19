"""env.json-authored launch commands → argv, plus the role prompts agents receive.

Nothing about *how* an agent CLI starts is hardcoded here. `.rh/env.json` carries
`agents.commands.<role>` (one launch template per role) and `agents.spawn` (how a
parallel agent is opened); the user or the Orchestrator writes them. This module
only substitutes values into those templates and runs the result, so the same
code drives `rh resume` (orchestrator, in this terminal) and `rh spawn <role>`.

Placeholders understood in a command template:

  {role} {agent}    role name (aliases)
  {agent_name}      the unique agent name (`rh-<project>-<role>`, `-2` on collision) —
                    use it for the pane/window name so a second agent of one role
                    gets its own pane; `{role}` stays the bare role
  {prompt}          the launch message (one line: read the brief and execute it)
  {prompt_file}     path of the prompt file written under `.rh/`
  {agent_file}      path of `.rh/agents/<role>.md` — use it in the CLI's
                    system-prompt-append area (e.g. pi: `--append-system-prompt
                    {agent_file}`; never a flag that REPLACES the system prompt)
  {agent_file_contents}  contents of `.rh/agents/<role>.md` inline (for harnesses
                    that take the text, not a path)
  {root} {name}     project root, project name (from .rh/env.json)
  {project}         project-name slug for pane/window names, so two projects
                    never fight over `rh-<role>` (`rh-{project}-{agent}`)
  {provider} {model} {thinking}   from `agents.roles.<role>`
  {skills}          comma-joined `agents.skills`
  {skills:list}     ONE token per skill, no flag attached (bare token only; for
                    harnesses whose flag takes a JSON/list arg — pair with the
                    harness's list flag yourself, e.g. --skills={skills:list})

`agents.spawn` additionally gets `{command}` — the launch command, shell-quoted.

A template that omits `{model}`, `{thinking}` or `{skills}` is not an error (the
user may want their harness defaults), but `launch_plan()` reports it in `notes`
so `rh resume`/`rh spawn` can tell the user their env.json is not being honoured.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import agentstate, config, paths
from .add import slugify
from .tasks import TaskStore, phase_name

# --- roles (SKILL.md §5) -------------------------------------------------------
# No hardcoded role info. Roles are files: `.rh/agents/<role>.md` (see agents.py).
# The set is whatever the user defines there and/or in
# `agents.commands.<role>` in `.rh/env.json`.

# --- template engine ----------------------------------------------------------

# `{name}` but not `${name}` (shell variables in a spawn template survive intact)
_PLACEHOLDER = re.compile(r"(?<!\$)\{(\w+)\}")

PLACEHOLDERS = (
    "role",
    "agent",
    "agent_name",
    "prompt",
    "prompt_file",
    "agent_file",
    "agent_file_contents",
    "root",
    "name",
    "project",
    "provider",
    "model",
    "thinking",
    "skills",
)
SPAWN_PLACEHOLDERS = PLACEHOLDERS + ("command",)


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def substitute(
    text: str, values: dict[str, str], notes: list[str] | None = None
) -> str:
    """Replace `{placeholder}` in `text`. Unknown/lowercase names are reported."""

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name in values:
            value = values[name]
            if not value and notes is not None:
                notes.append(f"`{{{name}}}` is empty in .rh/env.json")
            return value
        # uppercase braces are usually shell (${HOME}); only flag lowercase typos
        if name.islower() and notes is not None:
            notes.append(f"unknown placeholder `{{{name}}}` left as-is")
        return m.group(0)

    return _PLACEHOLDER.sub(repl, text)


def project_slug(env: dict) -> str:
    """Short project name for backend pane/window names (`rh-<project>-<role>`)."""
    return slugify(str((env.get("project") or {}).get("name") or ""))


def derive_name(root: Path, env: dict, role: str, suffix: str = "") -> str:
    """The unique agent name: `rh-<project>-<role>`, then `-2`, `-3` … if taken."""
    return agentstate.derive_name(root, env, role, suffix)


def role_spec(env: dict, role: str) -> dict:
    """provider/model/thinking for `role` from `.rh/env.json`."""
    roles = (env.get("agents") or {}).get("roles") or {}
    spec = roles.get(role) or {}
    if not isinstance(spec, dict):
        spec = {}
    return {k: str(spec.get(k) or "") for k in ("provider", "model", "thinking")}


def skills_for(env: dict) -> list[str]:
    """The ONLY skills a session should load (`agents.skills`, SKILL.md §2)."""
    raw = (env.get("agents") or {}).get("skills") or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(s).strip() for s in raw if str(s).strip()]


def find_template(env: dict, role: str) -> tuple[str, str]:
    """(template, source-key) for `role`; falls back to `agents.commands.default`."""
    cmds = (env.get("agents") or {}).get("commands") or {}
    if not isinstance(cmds, dict):
        return "", ""
    for key in (role, role.lower(), "default"):
        value = cmds.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), f"agents.commands.{key}"
    return "", ""


def launch_plan(
    root: Path, env: dict, role: str, prompt: str, prompt_file: Path,
    agent_name: str = "",
) -> dict:
    """Resolve the argv that starts `role`, using the command written in env.json.

    Returns {argv, source, template, provider, model, thinking, skills, notes}.
    `argv` is None when env.json names neither a command template nor a CLI.
    """
    role = (role or "orchestrator").strip().lower()
    spec = role_spec(env, role)
    skills = skills_for(env)
    template, source = find_template(env, role)
    agents = env.get("agents") or {}
    cli = str(agents.get("cli") or "").strip()
    notes: list[str] = []
    # Role file: `.rh/agents/<role>.md`. Candidates: lowercase, UPPERCASE, Capitalized.
    agent_file_path = ""
    agent_file_contents = ""
    try:
        from . import agents as _agents

        agent_file_path = str(_agents.role_file(root, role))
        agent_file_contents = _agents.read_role(root, role) or ""
    except (ImportError, OSError):
        agent_file_path = ""
    values = {
        "role": role,
        "agent": role,
        "agent_name": agent_name or role,
        "prompt": prompt,
        "prompt_file": str(prompt_file),
        "agent_file": agent_file_path,
        "agent_file_contents": agent_file_contents,
        "root": str(root),
        "name": str((env.get("project") or {}).get("name") or ""),
        "project": project_slug(env),
        "provider": spec["provider"],
        "model": spec["model"],
        "thinking": spec["thinking"],
        "skills": ",".join(skills),
    }
    plan = {
        "argv": None,
        "error": "",
        "source": source,
        "template": template,
        "agent_name": agent_name or role,
        "prompt_file": str(prompt_file),
        "provider": spec["provider"],
        "model": spec["model"],
        "thinking": spec["thinking"],
        "skills": skills,
        "cli": cli,
        "notes": notes,
    }

    if not template:
        if not cli:
            plan["error"] = (
                f"no launch command for '{role}': set agents.commands.{role} "
                "(or agents.commands.default) in .rh/env.json — e.g. "
                "rh env set agents.commands.default='pi --model {model}'"
            )
        else:
            plan["argv"] = [cli, prompt]
            plan["source"] = "agents.cli (fallback)"
            notes.append(
                "no agents.commands.<role>/default in .rh/env.json — fell back to "
                f"`{cli} <prompt>`; add a template to pass the model"
            )
            if spec["model"]:
                notes.append(
                    f"model {spec['model']} is NOT passed (no {{model}} in the command)"
                )
            if spec["thinking"]:
                notes.append(
                    f"thinking level {spec['thinking']} is NOT passed (no {{thinking}})"
                )
            if skills:
                notes.append(
                    "skills are described in the prompt but not restricted at the CLI"
                )
        if not spec["model"]:
            notes.append(
                f"agents.roles.{role}.model is empty — the harness default model will run"
            )
        plan["notes"] = _uniq(notes)
        return plan

    # split first, substitute per token: a prompt with spaces/newlines/quotes
    # stays exactly one argv element
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        plan["error"] = f"{source} is not shell-splittable: {exc}"
        plan["notes"] = _uniq(notes)
        return plan
    if not tokens:
        plan["error"] = f"{source} is empty"
        plan["notes"] = _uniq(notes)
        return plan
    # Split first, then substitute per token so a prompt with spaces/commas/quotes
    # stays exactly one argv element. A placeholder that resolves to "" drops the
    # flag that introduced it (`--model {model}` with no model set → no flag).
    empty = {
        name for name in ("provider", "model", "thinking", "skills") if not values[name]
    }
    argv: list[str] = []
    # Named whole-token expansions that produce 0+ argv elements:
    #   {skills:list} → ONE token per skill (for `--skill a --skill b` style flags,
    #   written as `--skill {skills:list}` with the flag repeated by the template;
    #   a template that writes the flag once gets a single expansion token list).
    # Plain {skills} stays comma-joined for backwards compatibility.
    for tok in tokens:
        if tok == "{skills:list}":
            if not skills:
                if argv and argv[-1].startswith("-") and "{" not in argv[-1]:
                    argv.pop()
                continue
            argv.extend(skills)
            continue
        whole = re.fullmatch(r"\{(\w+)\}", tok)
        if whole and whole.group(1) in empty:
            if argv and argv[-1].startswith("-") and "{" not in argv[-1]:
                argv.pop()
            continue
        rendered = substitute(tok, values, notes)
        if re.fullmatch(r"--[\w-]+=", rendered):
            notes.append(f"`{rendered}` dropped — that value is empty in .rh/env.json")
            continue
        argv.append(rendered)
    if "{prompt}" not in template and "{prompt_file}" not in template:
        # the harness needs the instructions somewhere: positional is the default
        argv.append(prompt)
    if not argv:
        plan["error"] = f"{source} expanded to nothing — check its placeholders"
        plan["notes"] = _uniq(notes)
        return plan
    plan["argv"] = argv
    if spec["model"] and "{model}" not in template:
        notes.append(
            f"model {spec['model']} is NOT passed — add `--model {{model}}` to {source}"
        )
    if spec["thinking"] and "{thinking}" not in template:
        notes.append(f"thinking {spec['thinking']} is NOT passed — add it to {source}")
    if skills and "{skills}" not in template and role != "orchestrator":
        # the orchestrator deliberately sees every skill — it assigns them
        notes.append(
            f"skills {', '.join(skills)} are in the prompt but not restricted at the CLI — "
            f"add the harness flag to {source} (e.g. one `--skill` per name, expanded from {{skills}})"
        )
    if "{agent_file}" not in template:
        notes.append(
            f"{{agent_file}} is not in {source} — .rh/agents/{role}.md is not wired into the "
            "harness's system prompt (use the harness's flag, e.g. --append-system-prompt {agent_file})"
        )
    if not spec["model"]:
        notes.append(
            f"agents.roles.{role}.model is empty — the harness default model will run"
        )
    plan["notes"] = _uniq(notes)
    return plan


def detect_shell(env: dict | None = None) -> str:
    """User shell: agents.shell in env.json, else $SHELL, else sh. Never probes binaries."""
    env = env or {}
    cfg = str((env.get("agents") or {}).get("shell") or "").strip()
    if cfg:
        return cfg
    # $SHELL is usually a full path (/usr/bin/fish); the name is what we run
    return Path(os.environ.get("SHELL", "").strip()).name or "sh"


def detect_split(env: dict | None = None) -> str:
    """Pane layout: agents.split in env.json, else '' (the Orchestrator asks the user)."""
    env = env or {}
    raw = str((env.get("agents") or {}).get("split") or "").strip().lower()
    return "window" if raw in ("new-window", "new_workspace", "workspace") else raw


def terminal_plan(
    root: Path, env: dict, command: str, split: str | None = None
) -> dict:
    """Plan for opening a plain shell terminal (not an agent) in a pane/window.

    One-shot: `shell -c command`. Layout comes from agents.split. Returns
    {argv, shell, split, command, notes}.
    """
    shell = detect_shell(env)
    chosen = (split or "").strip().lower() or detect_split(env)
    notes: list[str] = []
    if not chosen:
        notes.append(
            "agents.split is not set — ask the user: vertical-split, horizontal-split, or new workspace/window, or set agents.split=vertical|horizontal|window"
        )
    return {
        "argv": [shell, "-c", command],
        "shell": shell,
        "split": chosen,
        "command": command,
        "notes": notes,
    }


def spawn_preview(root: Path, env: dict, role: str, plan: dict) -> dict:
    """What `rh spawn` would run: an env.json pane template, or a background process."""
    if not plan.get("argv"):
        return {
            "mode": "none",
            "command": "",
            "log": "",
            "source": "",
            "notes": list(plan.get("notes") or []),
        }
    agents = env.get("agents") or {}
    template = str(agents.get("spawn") or "").strip()
    source = "agents.spawn"
    if not template:
        # No hand-written pane template: the configured backend's data owns it.
        backend = str(agents.get("backend") or "").strip().lower()
        template = str((config.load_backends().get(backend) or {}).get("spawn") or "").strip()
        source = f"backends.{backend}" if template else ""
    if template:
        notes: list[str] = []
        values = {
            "role": role,
            "agent": role,
            "agent_name": plan.get("agent_name") or role,
            "root": str(root),
            "name": str((env.get("project") or {}).get("name") or ""),
            "project": project_slug(env),
            "prompt_file": plan.get("prompt_file", ""),
            "provider": plan.get("provider", ""),
            "model": plan.get("model", ""),
            "thinking": plan.get("thinking", ""),
            "skills": ",".join(plan.get("skills") or []),
            "command": shlex.join(plan["argv"]),
        }
        if "{agent_name}" not in template and (
            "{role}" in template or "{agent}" in template
        ):
            notes.append(
                "pane name is not the unique agent name — use `{agent_name}` in "
                "agents.spawn, or two agents of one role share a pane name"
            )
        return {
            "mode": "pane",
            "command": substitute(template, values, notes),
            "log": "",
            "source": source,
            "notes": _uniq(notes),
        }
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log = paths.logs_dir(root) / f"spawn-{slugify(role)}-{stamp}.log"
    return {
        "mode": "background",
        "command": shlex.join(plan["argv"]),
        "log": str(log),
        "source": "",
        "notes": [],
    }


def spawn_now(root: Path, env: dict, role: str, plan: dict) -> dict:
    """Open the agent: pane via `agents.spawn` when set, else a detached process."""
    return _start(root, role, plan, spawn_preview(root, env, role, plan))


def terminal_preview(root: Path, env: dict, plan: dict) -> dict:
    """`spawn_preview` for a shell terminal (no agent, role=`terminal`)."""
    synthetic = {
        "argv": plan["argv"],
        "prompt_file": "",
        "provider": "",
        "model": "",
        "thinking": "",
        "skills": [],
        "notes": [],
    }
    preview = spawn_preview(root, env, "terminal", synthetic)
    preview["shell"] = plan["shell"]
    preview["split"] = plan.get("split", "")
    preview["terminal"] = True
    return preview


def spawn_terminal_now(
    root: Path, env: dict, plan: dict, preview: dict | None = None
) -> dict:
    """Start the shell terminal planned by `terminal_plan`."""
    return _start(root, "terminal", plan, preview or terminal_preview(root, env, plan))


def _start(root: Path, role: str, plan: dict, preview: dict) -> dict:
    """Run a preview: pane template or detached process. Records the spawn."""
    if preview["mode"] == "pane":
        proc = subprocess.run(
            preview["command"], shell=True, cwd=str(root), check=False
        )
        preview["returncode"] = proc.returncode
        _spawn_record(root, role, plan, None, "pane", preview.get("source", ""))
        _state_record(root, role, plan, preview, None)
        return preview
    if preview["mode"] != "background":
        return preview
    log_path = Path(preview["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as fh:
        proc = subprocess.Popen(
            plan["argv"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    preview["pid"] = proc.pid
    _spawn_record(root, role, plan, proc.pid, "background")
    _state_record(root, role, plan, preview, proc.pid)
    return preview


def _state_record(
    root: Path, role: str, plan: dict, preview: dict, pid: int | None
) -> None:
    """Write `.rh/agents/<name>.json` — the file `rh agent status` reads.

    A plain shell terminal is not an agent: it gets no state file. If the pane
    command failed the record still lands, so a failed spawn is visible instead
    of silently absent (close it with `rh agent done <name> --outcome closed`).
    """
    if role == "terminal":
        return
    name = str(plan.get("agent_name") or role)
    agentstate.write_open(
        root,
        name=name,
        role=role,
        model=str(plan.get("model") or ""),
        mode=str(preview.get("mode") or ""),
        report=str(plan.get("report") or f"{paths.RH_DIR}/reports/{name}.md"),
        brief=str(plan.get("brief") or ""),
        source=str(preview.get("source") or plan.get("source") or ""),
        pid=pid,
    )


def _spawn_record(
    root: Path,
    role: str,
    plan: dict,
    pid: int | None,
    mode: str,
    pane_source: str = "",
) -> None:
    """Append one JSON line per spawn to .rh/logs/spawns.jsonl (agent status + budget)."""
    log_dir = paths.logs_dir(root)
    log_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "role": role,
        "name": plan.get("agent_name", ""),
        "pid": pid,
        "mode": mode,
        "model": plan.get("model", ""),
        "source": pane_source or plan.get("source", ""),
        "log": "",
        "ts": datetime.now().isoformat(),
    }
    with (log_dir / "spawns.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def running_count(root: Path) -> int:
    """Concurrent agents: open state files, plus legacy records with a live pid.

    State files are the count now, because they are what `rh agent done` closes —
    so pane spawns count too. Rows in `spawns.jsonl` written before state files
    existed carry no name and are still counted by pid.
    """
    alive = len(agentstate.open_records(root))
    f = paths.logs_dir(root) / "spawns.jsonl"
    if not f.exists():
        return alive
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn line at the tail of an append-only file
        if rec.get("closed") or rec.get("name"):
            continue  # named rows are state files; counting both double-counts
        pid = rec.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                alive += 1
            except OSError:
                pass
    return alive


def exec_argv(root: Path, argv: list[str]) -> tuple[bool, str]:
    """Replace this process with the agent, in the terminal the user called from.

    Returns (False, detail) only when the exec could not start; on success rh is
    gone (the agent owns the terminal) and the return value is never seen.
    """
    root = root.resolve()
    if not (root / paths.RH_DIR).is_dir():
        return (
            False,
            f"{root} has no .rh/ — refusing to open an agent in the wrong project",
        )
    # exec replaces this process: buffered UI would otherwise vanish in a pipe
    sys.stdout.flush()
    sys.stderr.flush()
    os.chdir(root)
    try:
        os.execvp(argv[0], argv)
    except OSError as exc:
        return False, f"{argv[0]} could not start: {exc}"
    return False, "unreachable"  # pragma: no cover


# --- role prompt --------------------------------------------------------------


def role_tasks(store: TaskStore, role: str, limit: int = 8) -> list[dict]:
    """Board tasks owned by `role` (the Orchestrator sees the whole next-up list)."""
    tasks = store.list()
    prio = {"working": 0, "idle": 1, "complete": 2, "cancelled": 3}
    owned = [t for t in tasks if str(t.get("owner") or "").lower() == role]
    if not owned and role == "orchestrator":
        owned = tasks
    return sorted(owned, key=lambda t: (prio.get(t["state"], 3), t["phase"], t["id"]))[
        :limit
    ]


def build_role_prompt(
    root: Path, env: dict, role: str, store: TaskStore, extra: str = "",
    agent_name: str = "",
) -> str:
    """The prompt `rh spawn` hands to a role agent.

    Role definition comes from `.rh/agents/<role>.md` (the Orchestrator's
    tailored agent file). If the file is missing the prompt names that and
    points at `rh agent write <role>`; rh never invents role rules.
    """
    role = (role or "").strip().lower()
    try:
        from . import agents as agents_mod

        role_file_text = agents_mod.read_role(root, role)
        agent_path = str(agents_mod.role_file(root, role))
    except (ImportError, OSError):
        role_file_text = None
        agent_path = f".rh/agents/{role}.md"
    spec = role_spec(env, role)
    skills = skills_for(env)
    project_name = (env.get("project") or {}).get("name") or "untitled"
    pane_name = agent_name or f"rh-{project_slug(env)}-{role}"
    report_rel = f"{paths.RH_DIR}/reports/{pane_name}.md"
    current = store.current_phase()
    gate = config.phase_gate(root, env)
    model_line = (
        f"{spec['provider']}/{spec['model']}"
        if spec["provider"] and spec["model"]
        else spec["model"] or "not set in .rh/env.json"
    )
    if spec["thinking"]:
        model_line += f" (thinking: {spec['thinking']})"
    lines = [
        f"You are the {role.upper()} agent for the research project '{project_name}'.",
        f"Your name in the backend is `{pane_name}` — the Orchestrator addresses you by it.",
        f"Project root (verify you are here before writing anything): {root}",
        f"Session model: {model_line}",
        f"Role file: {agent_path} — your tailored job description; follow it.",
        "",
    ]
    if role_file_text:
        lines += [
            "## Role file (.rh/agents/<role>.md) — this is your tailored job description:",
            "",
        ]
        lines += role_file_text.strip().splitlines()
        lines += [""]
    else:
        lines += [
            f"No role file yet at {agent_path} — the Orchestrator creates it with",
            f"  rh agent write {role}",
            "and edits it with user approval. Ask the Orchestrator for your scope",
            "until then; do not guess at your role.",
            "",
        ]
    lines += [
        (
            "Load exactly these skills for this session, and no others "
            "(keeping the session lean is the point):"
        ),
    ]
    lines += [f"  - {s}" for s in skills] or [
        "  - (none configured — ask the Orchestrator)"
    ]
    lines += [
        "Then follow the research-helper skill exactly — it is law, not advice",
        "(SKILL.md §0 non-negotiables; ask before every state-changing action).",
        "",
        f"Current phase: {phase_name(current)}",
    ]
    lines += [
        "Before writing any artifact, run `rh info <FILE>` — it describes purpose,",
        "sections, template and the rules that bite there (SKILL.md §1).",
    ]
    if gate["problems"]:
        lines.append("Unmet gates you must not paper over:")
        lines += [f"  - {p}" for p in gate["problems"]]
    tasks = role_tasks(store, role)
    if tasks:
        lines += ["", f"Tasks on the board for this role (owner={role}):"]
        for t in tasks:
            bits = [f"[{t['state']}] {t['id']} {t['title']}"]
            if t.get("deliverable"):
                bits.append(f"deliverable: {t['deliverable']}")
            if t.get("verify"):
                bits.append(f"verify: `{t['verify']}`")
            if t.get("depends_on"):
                bits.append(f"after: {', '.join(t['depends_on'])}")
            lines.append("  - " + " · ".join(bits))
    else:
        lines += [
            "",
            (
                "No board tasks for this role yet — the Orchestrator mirrors PLAN.md "
                "into the board with `rh add task` (steps and subtasks are created explicitly)."
            ),
        ]
    lines += [
        "",
        f"Report: write your report to `{report_rel}` — what you changed, the",
        "evidence (command + number), and what you need from the Orchestrator.",
        f"Your last act is `rh agent done {pane_name}`. It refuses an empty report,",
        "so write the file first; `--outcome blocked` asks for the Orchestrator,",
        "and `--outcome closed` is only for the Orchestrator closing your pane.",
        "Never update STATUS.md unless you are the Orchestrator — that file is its",
        "own work (SKILL.md rule 9).",
    ]
    if extra:
        lines += [
            "",
            "Instructions from the Orchestrator/user for this session:",
            extra.strip(),
        ]
    return "\n".join(lines)
