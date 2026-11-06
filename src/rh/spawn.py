"""ENV.md-authored launch commands → argv, plus the role prompts agents receive.

Nothing about *how* an agent CLI starts is hardcoded here. `.rh/ENV.md` carries
`agents.commands.<role>` (one launch template per role) and `agents.spawn` (how a
parallel agent is opened); the user or the Orchestrator writes them. This module
only substitutes values into those templates and runs the result, so the same
code drives `rh resume` (orchestrator, in this terminal) and `rh spawn <role>`.

Placeholders understood in a command template:

  {role} {agent}    role name (aliases)
  {prompt}          the full role prompt (one argv element, newlines intact)
  {prompt_file}     path of the prompt file written under `.rh/`
  {root} {slug}     project root, project slug
  {provider} {model} {thinking}   from `agents.roles.<role>`
  {skills}          comma-joined `agents.skills`

`agents.spawn` additionally gets `{command}` — the launch command, shell-quoted.

A template that omits `{model}`, `{thinking}` or `{skills}` is not an error (the
user may want their harness defaults), but `launch_plan()` reports it in `notes`
so `rh resume`/`rh spawn` can tell the user their ENV.md is not being honoured.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, paths
from .add import slugify
from .tasks import TaskStore, phase_name

# --- roles (SKILL.md §5) -------------------------------------------------------

ROLE_INFO: dict[str, dict] = {
    "orchestrator": {
        "one_line": "the head of the project — the current runner is always the Orchestrator",
        "owns": "routing, STATUS.md, PLAN.md merges, every question to the user",
        "may": "delegate, gate, escalate, edit artifacts",
        "may_not": "implement, fix code, approve its own plan, pick models",
        "artifacts": ["STATUS.md", "PLAN.md", "ENV.md"],
    },
    "literature": {
        "one_line": "survey and read the literature, decide the output layout",
        "owns": "papers/, LITERATURE.md, OUTPUT_LAYOUT.md, GAPS.md",
        "may": "download open-access papers, read, cite, flag code smells in sources",
        "may_not": "paraphrase unread papers, substitute references, change the plan",
        "artifacts": ["LITERATURE.md", "OUTPUT_LAYOUT.md", "GAPS.md"],
    },
    "researcher": {
        "one_line": "implement the approved plan steps and record every number",
        "owns": "src/, results/",
        "may": "implement, test, probe tools, append to OUTPUT_LAYOUT.md from sources it reads",
        "may_not": "change scope, delete user files, install system packages, edit tests to pass",
        "artifacts": ["PLAN.md", "OUTPUT_LAYOUT.md"],
    },
    "reviewer": {
        "one_line": "independent review of what was built — findings only",
        "owns": "review verdicts (STATUS.md, .rh/logs/)",
        "may": "read everything, file findings, demand evidence",
        "may_not": "fix what it finds (independence is the point)",
        "artifacts": ["STATUS.md"],
    },
    "critique": {
        "one_line": "adversarial questions against the artifacts, with veto power",
        "owns": "the blocking-question list, the critique gate",
        "may": "question anything, block a gate, demand falsification",
        "may_not": "implement, soften its own findings",
        "artifacts": ["STATUS.md"],
    },
    "writer": {
        "one_line": "draft the manuscript from artifacts, never from memory",
        "owns": "MANUSCRIPT.md",
        "may": "draft, restructure, cite from artifacts",
        "may_not": "introduce evidence not in results/ or LITERATURE.md",
        "artifacts": ["MANUSCRIPT.md", "OUTPUT_LAYOUT.md"],
    },
}

ROLES = tuple(ROLE_INFO)

# --- template engine ----------------------------------------------------------

# `{name}` but not `${name}` (shell variables in a spawn template survive intact)
_PLACEHOLDER = re.compile(r"(?<!\$)\{(\w+)\}")

PLACEHOLDERS = ("role", "agent", "prompt", "prompt_file", "root", "slug",
                "provider", "model", "thinking", "skills")
SPAWN_PLACEHOLDERS = PLACEHOLDERS + ("command",)


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def substitute(text: str, values: dict[str, str], notes: list[str] | None = None) -> str:
    """Replace `{placeholder}` in `text`. Unknown/lowercase names are reported."""

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name in values:
            value = values[name]
            if not value and notes is not None:
                notes.append(f"`{{{name}}}` is empty in .rh/ENV.md")
            return value
        # uppercase braces are usually shell (${HOME}); only flag lowercase typos
        if name.islower() and notes is not None:
            notes.append(f"unknown placeholder `{{{name}}}` left as-is")
        return m.group(0)

    return _PLACEHOLDER.sub(repl, text)


def role_spec(env: dict, role: str) -> dict:
    """provider/model/thinking for `role` from the ENV.md config block."""
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


def launch_plan(root: Path, env: dict, role: str, prompt: str, prompt_file: Path) -> dict:
    """Resolve the argv that starts `role`, using the command written in ENV.md.

    Returns {argv, source, template, provider, model, thinking, skills, notes}.
    `argv` is None when ENV.md names neither a command template nor a CLI.
    """
    role = (role or "orchestrator").strip().lower()
    spec = role_spec(env, role)
    skills = skills_for(env)
    template, source = find_template(env, role)
    agents = env.get("agents") or {}
    cli = str(agents.get("cli") or "").strip()
    notes: list[str] = []
    values = {
        "role": role,
        "agent": role,
        "prompt": prompt,
        "prompt_file": str(prompt_file),
        "root": str(root),
        "slug": str((env.get("project") or {}).get("slug") or ""),
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
                "(or agents.commands.default) in .rh/ENV.md — e.g. "
                "rh env set agents.commands.default='pi --model {model}'"
            )
        else:
            plan["argv"] = [cli, prompt]
            plan["source"] = "agents.cli (fallback)"
            notes.append(
                "no agents.commands.<role>/default in .rh/ENV.md — fell back to "
                f"`{cli} <prompt>`; add a template to pass the model"
            )
            if spec["model"]:
                notes.append(f"model {spec['model']} is NOT passed (no {{model}} in the command)")
            if spec["thinking"]:
                notes.append(f"thinking level {spec['thinking']} is NOT passed (no {{thinking}})")
            if skills:
                notes.append("skills are described in the prompt but not restricted at the CLI")
        if not spec["model"]:
            notes.append(f"agents.roles.{role}.model is empty — the harness default model will run")
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
    empty = {name for name in ("provider", "model", "thinking", "skills") if not values[name]}
    argv: list[str] = []
    for tok in tokens:
        whole = re.fullmatch(r"\{(\w+)\}", tok)
        if whole and whole.group(1) in empty:
            if argv and argv[-1].startswith("-") and "{" not in argv[-1]:
                argv.pop()
            continue
        rendered = substitute(tok, values, notes)
        if re.fullmatch(r"--[\w-]+=", rendered):
            notes.append(f"`{rendered}` dropped — that value is empty in .rh/ENV.md")
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
        notes.append(f"model {spec['model']} is NOT passed — add `--model {{model}}` to {source}")
    if spec["thinking"] and "{thinking}" not in template:
        notes.append(f"thinking {spec['thinking']} is NOT passed — add it to {source}")
    if skills and "{skills}" not in template:
        notes.append(
            f"skills {', '.join(skills)} are in the prompt but not restricted at the CLI — "
            f"add the harness flag to {source} (e.g. one `--skill` per name, expanded from {{skills}})"
        )
    if not spec["model"]:
        notes.append(f"agents.roles.{role}.model is empty — the harness default model will run")
    plan["notes"] = _uniq(notes)
    return plan


def spawn_preview(root: Path, env: dict, role: str, plan: dict) -> dict:
    """What `rh spawn` would run: an ENV.md pane template, or a background process."""
    if not plan.get("argv"):
        return {"mode": "none", "command": "", "log": "", "notes": list(plan.get("notes") or [])}
    template = str((env.get("agents") or {}).get("spawn") or "").strip()
    if template:
        notes: list[str] = []
        values = {
            "role": role, "agent": role, "root": str(root),
            "slug": str((env.get("project") or {}).get("slug") or ""),
            "prompt_file": plan.get("prompt_file", ""),
            "provider": plan.get("provider", ""),
            "model": plan.get("model", ""),
            "thinking": plan.get("thinking", ""),
            "skills": ",".join(plan.get("skills") or []),
            "command": shlex.join(plan["argv"]),
        }
        return {"mode": "pane", "command": substitute(template, values, notes),
                "log": "", "notes": _uniq(notes)}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log = paths.logs_dir(root) / f"spawn-{slugify(role)}-{stamp}.log"
    return {"mode": "background", "command": shlex.join(plan["argv"]), "log": str(log), "notes": []}


def spawn_now(root: Path, env: dict, role: str, plan: dict) -> dict:
    """Open the agent: pane via `agents.spawn` when set, else a detached process."""
    preview = spawn_preview(root, env, role, plan)
    if preview["mode"] == "pane":
        proc = subprocess.run(preview["command"], shell=True, cwd=str(root), check=False)
        preview["returncode"] = proc.returncode
        return preview
    if preview["mode"] != "background":
        return preview
    log_path = Path(preview["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as fh:
        proc = subprocess.Popen(
            plan["argv"], cwd=str(root), stdin=subprocess.DEVNULL,
            stdout=fh, stderr=subprocess.STDOUT, start_new_session=True,
        )
    preview["pid"] = proc.pid
    return preview


def exec_argv(root: Path, argv: list[str]) -> tuple[bool, str]:
    """Replace this process with the agent, in the terminal the user called from.

    Returns (False, detail) only when the exec could not start; on success rh is
    gone (the agent owns the terminal) and the return value is never seen.
    """
    root = root.resolve()
    if not (root / paths.RH_DIR).is_dir():
        return False, f"{root} has no .rh/ — refusing to open an agent in the wrong project"
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
    prio = {"working": 0, "idle": 1, "complete": 2}
    owned = [t for t in tasks if str(t.get("owner") or "").lower() == role]
    if not owned and role == "orchestrator":
        owned = tasks
    return sorted(owned, key=lambda t: (prio.get(t["state"], 3), t["phase"], t["id"]))[:limit]


def _artifact_one_liners(names: list[str]) -> list[tuple[str, str]]:
    """(name, one-line purpose) for a role's artifacts — same text as `rh info`."""
    from .artifacts import ARTIFACTS, resolve

    out = []
    for name in names:
        key = resolve(name)
        if key:
            out.append((name, ARTIFACTS[key]["purpose"]))
    return out


def build_role_prompt(root: Path, env: dict, role: str, store: TaskStore,
                      extra: str = "") -> str:
    """The prompt `rh spawn` hands to a role agent."""
    role = (role or "").strip().lower()
    info = ROLE_INFO.get(role, {
        "one_line": f"a project-defined agent role '{role}'",
        "owns": "whatever .rh/ENV.md / the Orchestrator assigns",
        "may": "act inside its assignment",
        "may_not": "change scope, models, or the plan",
        "artifacts": ["STATUS.md"],
    })
    spec = role_spec(env, role)
    skills = skills_for(env)
    slug = (env.get("project") or {}).get("slug") or "untitled"
    current = store.current_phase()
    gate = config.phase_gate(root, env)
    model_line = (f"{spec['provider']}/{spec['model']}"
                  if spec["provider"] and spec["model"] else spec["model"] or "not set in .rh/ENV.md")
    if spec["thinking"]:
        model_line += f" (thinking: {spec['thinking']})"
    lines = [
        f"You are the {role.upper()} agent for the research project '{slug}'.",
        f"Project root (verify you are here before writing anything): {root}",
        f"Session model: {model_line}",
        "",
        f"Role: {info['one_line']}",
        f"You own: {info['owns']}",
        f"You may: {info['may']}",
        f"You may not: {info['may_not']}",
        "",
        ("Load exactly these skills for this session, and no others "
         "(keeping the session lean is the point):"),
    ]
    lines += [f"  - {s}" for s in skills] or ["  - (none configured — ask the Orchestrator)"]
    lines += [
        "Then follow the research-helper skill exactly — it is law, not advice",
        "(SKILL.md §0 non-negotiables; ask before every state-changing action).",
        "",
        f"Current phase: {phase_name(current)}",
    ]
    if gate["problems"]:
        lines.append("Unmet gates you must not paper over:")
        lines += [f"  - {p}" for p in gate["problems"]]
    owned_artifacts = _artifact_one_liners(info["artifacts"])
    if owned_artifacts:
        lines += ["", "Artifacts you own — run `rh info <FILE>` before writing any of them:"]
        lines += [f"  - {name}: {purpose}" for name, purpose in owned_artifacts]
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
        lines += ["", ("No board tasks for this role yet — the Orchestrator mirrors PLAN.md "
                       "into the board with `rh plan import`.")]
    lines += [
        "",
        "Report back with: what you changed (files), the evidence (command + number),",
        "and what you need from the Orchestrator. Never update STATUS.md unless you are",
        "the Orchestrator — that file is its own work (SKILL.md rule 9).",
    ]
    if extra:
        lines += ["", "Instructions from the Orchestrator/user for this session:", extra.strip()]
    return "\n".join(lines)
