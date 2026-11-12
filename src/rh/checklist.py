"""The Orchestrator's checklist — setup tasks, SKILL.md §0 rules + phase exits.

The Orchestrator carries a long rule list in its prompt; a list that lives
only in prose is easy to forget under load. This module gives the checks a
machine form: one item per task/rule the Orchestrator must never miss, each
with its live status checked against the project on disk (via
`config.phase_gate` and the task board), never self-reported by the agent.

`rh init` writes `.rh/CHECKLIST.md` from this module (so the Orchestrator has
its to-do list in a file from the first session), and the orchestrator role file
points the agent at it as its first read.
"""
from __future__ import annotations

from pathlib import Path

from . import agents as agents_mod
from . import config, paths
from .tasks import PHASE_EXIT, TaskStore, phase_exit, phase_name

# Roles that get their own agent, per agents.count (SKILL.md §5).
LAUNCH_ROLES = {
    1: ("orchestrator",),
    2: ("orchestrator", "researcher"),
    3: ("orchestrator", "researcher", "critique"),
    4: ("orchestrator", "researcher", "critique", "reviewer"),
}
# A role file still holding this line was scaffolded, never tailored.
SCAFFOLD_MARK = "Role: <"

# Skill rule numbers this checklist is authoritative for (SKILL.md §0).
RULE_REFS = {
    "status_truth": "§0.9",
    "rereread_env": "§0.10",
    "waiver": "§0.11",
    "verify_path": "§0.12",
    "close_agents": "§0.13",
    "fresh_session": "§0.14",
    "pane_names": "§0.15",
    "plan_approval": "§3 phase 4",
    "critique_veto": "§3 phase 7",
}


def _phase_items(root: Path, env: dict | None = None) -> list[dict]:
    """One OK/pending item per phase exit gate, from live gate state."""
    env = env if env is not None else config.load_env(root)
    gate = config.phase_gate(root, env)
    store = TaskStore(root)
    current = store.current_phase() if paths.tasks_json(root).exists() else 0
    items: list[dict] = []
    for i in range(10):
        done = bool(gate["done"][i])
        if done:
            status, detail = "ok", ""
        elif i == current:
            status, detail = "current", "gate not yet met"
        elif i > current:
            status, detail = "later", f"not reached yet (phase {current})"
        else:
            status, detail = "pending", "gate not yet met"
        items.append({
            "id": f"phase-{i}",
            "label": f"{phase_name(i)} exit: {phase_exit(i, config.user_plans(env))}",
            "status": status,
            "ref": f"§3 phase {i}",
            "detail": detail,
        })
    return items


def _due(ok: bool, needed_at: int, current: int) -> str:
    """`ok`, or `later` when the item belongs to a phase not reached yet."""
    if ok:
        return "ok"
    return "later" if needed_at > current else "pending"


def _setup_items(root: Path, env: dict, current: int) -> list[dict]:
    """Concrete setup tasks: missing config, launch commands, notes, workflow."""
    agents = env.get("agents") or {}
    roles = agents.get("roles") or {}
    commands = agents.get("commands") or {}
    if not isinstance(commands, dict):
        commands = {}
    count = agents.get("count") if agents.get("count") in LAUNCH_ROLES else 1
    launch = LAUNCH_ROLES[count]
    items: list[dict] = []

    # 1. config written + valid (phase 0)
    written = config.config_written(root)
    problems = config.validate(env)
    items.append({
        "id": "setup-config",
        "label": "Config written to .rh/env.json and valid (`rh env show`)",
        "status": "ok" if written and not problems else "pending",
        "ref": "§0.2 §2",
        "detail": "" if written and not problems else "; ".join(problems) or "run `rh env set KEY=VALUE`",
    })

    # 2. missing environment values — ask the user, never invent
    missing: list[str] = []
    if not isinstance(roles.get("orchestrator"), dict) or not str(roles["orchestrator"].get("model") or ""):
        missing.append("agents.roles.orchestrator (provider/model/thinking)")
    for role in launch[1:]:
        spec = roles.get(role)
        if not isinstance(spec, dict) or not str(spec.get("model") or ""):
            missing.append(f"agents.roles.{role}")
    if not str(agents.get("cli") or "") and not find_any_command(commands):
        missing.append("agents.cli (or a launch command)")
    items.append({
        "id": "setup-env-values",
        "label": "Ask the user for every missing environment value (models, CLI)",
        "status": "pending" if missing else "ok",
        "ref": "§2 §0.2",
        "detail": ("ask the user: " + ", ".join(missing)) if missing else "",
    })

    # 3. environment notes (phase 2)
    has_notes = bool(config.environment_notes(root))
    items.append({
        "id": "setup-env-notes",
        "label": "Interview the user and write `.rh/ENVIRONMENT.md` (tools + versions)",
        "status": "ok" if has_notes else "pending",
        "ref": "§3 phase 2",
        "detail": "" if has_notes else "never probe: ask which runtimes/packages/versions this project uses, then record them",
    })

    # 4. launch commands for the roles this project will spawn
    broken: list[str] = []
    for role in launch:
        template, _ = _template_for(commands, role)
        if not template:
            broken.append(f"agents.commands.{role}")
        elif "{agent_file}" not in template and "{agent_file_contents}" not in template:
            broken.append(f"agents.commands.{role} lacks {{agent_file}}")
        elif "{prompt}" not in template and "{prompt_file}" not in template:
            broken.append(f"agents.commands.{role} lacks {{prompt_file}}")
    items.append({
        "id": "setup-commands",
        "label": "Fill every launch command (needs {agent_file} + {prompt_file}); check with `rh doctor`",
        "status": "pending" if broken else "ok",
        "ref": "§2 §10.7",
        "detail": ("; ".join(broken) + " — ask the user for the harness flags") if broken else "",
    })

    # 5. role files tailored with the user (init scaffolds them)
    untailored = [r for r in launch
                  if (agents_mod.read_role(root, r) or "").find(SCAFFOLD_MARK) >= 0]
    items.append({
        "id": "setup-role-files",
        "label": "Edit the scaffolded `.rh/agents/<role>.md` files with the user",
        "status": "pending" if untailored else "ok",
        "ref": "§5",
        "detail": ("still the default scaffold: " + ", ".join(f".rh/agents/{r}.md" for r in untailored))
        if untailored else "",
    })

    # 6. pane layout / spawn command for the chosen backend
    backend = str(agents.get("backend") or "none")
    spawn_tmpl = str(agents.get("spawn") or "").strip()
    needs_spawn = backend != "none" and not spawn_tmpl
    items.append({
        "id": "setup-spawn",
        "label": "Set `agents.spawn` when agents.open in panes (blank backend = detached process)",
        "status": "pending" if needs_spawn else "ok",
        "ref": "§2",
        "detail": (f"agents.backend={backend} but agents.spawn is blank — ask the user for the pane command (e.g. tmux new-window -n rh-{{project}}-{{agent}} -c {{root}} {{command}})")
        if needs_spawn else f"backend={backend}",
    })

    # 7. workflow diagram — authored after the plan exists
    wf = paths.rh_dir(root) / "workflow.mmd"
    if wf.exists() and wf.stat().st_size > 0:
        wf_status, wf_detail = "ok", ""
    elif current < 4:
        wf_status, wf_detail = "later", "write it after PLAN.md is approved (phase 4)"
    else:
        wf_status, wf_detail = "pending", "author .rh/workflow.mmd (PLAN.md step DAG, in the syntax `rh workflow --tools` lists)"
    items.append({
        "id": "setup-workflow",
        "label": "Author `.rh/workflow.mmd` once the plan is approved",
        "status": wf_status,
        "ref": "§10.1",
        "detail": wf_detail,
    })
    return items


def find_any_command(commands: dict) -> bool:
    return any(isinstance(v, str) and v.strip() for v in commands.values())


def _template_for(commands: dict, role: str) -> tuple[str, str]:
    for key in (role, "default"):
        value = commands.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), key
    return "", ""


def build_checklist(root: Path, env: dict | None = None) -> dict:
    """Live checklist for the project at `root`.

    Returns {root, phase, phase_name, items:[{id,label,status,ref,detail}],
    pending:[...]}. status ∈ {ok, current, pending}.
    """
    env = env if env is not None else config.load_env(root)
    gate = config.phase_gate(root, env)
    store = TaskStore(root)
    current = store.current_phase() if paths.tasks_json(root).exists() else 0

    env_file = paths.env_json(root)
    status_file = paths.artifact_path(root, "STATUS.md") if paths.rh_dir(root).exists() else None

    def _missing_text(name: str) -> bool:
        if status_file is not None and name == "STATUS.md":
            p = status_file
        else:
            p = paths.artifact_path(root, name) if paths.rh_dir(root).exists() else root / name
        return not (p.exists() and p.stat().st_size > 0)

    gates_veto = (env.get("gates") or {}).get("critique_veto", True)
    items: list[dict] = []

    items.extend(_phase_items(root, env))
    items.extend(_setup_items(root, env, current))

    # Rule 9 — STATUS.md is the Orchestrator's own work.
    items.append({
        "id": "rule-9",
        "label": "STATUS.md updated by the Orchestrator after every step, before every question (never delegated)",
        "status": "ok" if not _missing_text("STATUS.md") else "pending",
        "ref": RULE_REFS["status_truth"],
        "detail": "" if not _missing_text("STATUS.md") else "STATUS.md missing or empty — create it (phase 5) before any question to the user",
    })

    # Rule 10 — re-read the config at the start of every phase.
    items.append({
        "id": "rule-10",
        "label": "env.json + ENVIRONMENT.md re-read at the start of this phase (never cached)",
        "status": "ok" if env_file.exists() else "pending",
        "ref": RULE_REFS["rereread_env"],
        "detail": f"config at {env_file}" if env_file.exists() else f"{env_file} missing — run phase 0",
    })

    # Rule 11 — waivers recorded in STATUS.md by rule number.
    # Not observable from disk: no file says "rule 7 was waived". Human check.
    items.append({
        "id": "rule-11",
        "label": "Any waived rule recorded in STATUS.md history by rule number",
        "status": "current",
        "ref": RULE_REFS["waiver"],
        "detail": "not checkable from disk — when waiving, record the rule number in STATUS.md history + manuscript limitations",
    })

    # Rule 12 — verify path before opening any agent.
    rh_exists = paths.rh_dir(root).exists()
    items.append({
        "id": "rule-12",
        "label": "Project path verified before opening any agent (.rh/ + .rh/env.json present, path stated to the user)",
        "status": "ok" if (rh_exists and env_file.exists()) else "pending",
        "ref": RULE_REFS["verify_path"],
        "detail": f"root: {root}" if rh_exists else f"{root} has no .rh/ — run `rh init` first",
    })

    # Rule 13 — close what you opened.
    items.append({
        "id": "rule-13",
        "label": "Every opened agent closed when its job is done, and the close recorded in STATUS.md",
        "status": "current",
        "ref": RULE_REFS["close_agents"],
        "detail": "open panes/windows are visible to the user; check STATUS.md roster before assuming zero running agents",
    })

    # Rule 14 — fresh session after gate-heavy steps, with an authored handoff.
    items.append({
        "id": "rule-14",
        "label": "After a gate-heavy step, tell the user to continue in a fresh session; write `.rh/HANDOFF.md` first and clear it after reading",
        "status": "current",
        "ref": RULE_REFS["fresh_session"],
        "detail": "plan approved / implementation done / critique answered → write the handoff (what to do next, not a STATUS copy), then a fresh session; `rh handoff` shows it, `rh handoff --clear` empties it",
    })

    # Rule 15 — project-scoped pane names.
    items.append({
        "id": "rule-15",
        "label": "Every pane/window named `rh-<project>-<role>` and addressed by that name",
        "status": "current",
        "ref": RULE_REFS["pane_names"],
        "detail": "agents.spawn uses `-n rh-{project}-{agent}`; two projects never share a name — check STATUS.md for the roster",
    })

    # Plan approval — gates.user_approves_plan
    plan_ok = bool(gate["done"][4])
    items.append({
        "id": "plan-approved",
        "label": "PLAN.md approved by the user (gates.user_approves_plan) before any implementation",
        "status": _due(plan_ok, 4, current),
        "ref": RULE_REFS["plan_approval"],
        "detail": "" if plan_ok else "PLAN.md missing or gate unmet — no implementation before the user's yes",
    })

    # Critique veto — gates.critique_veto
    crit_ok = bool(gate["done"][7])
    items.append({
        "id": "critique-veto",
        "label": "Zero open blocking questions from Critique (gates.critique_veto) before phase 8",
        "status": _due(crit_ok, 7, current) if gates_veto else "ok",
        "ref": RULE_REFS["critique_veto"],
        "detail": "" if (crit_ok or not gates_veto) else "blocking questions still open — return to phase 6 (or 4 if scope changes)",
    })

    # Content checks (v2): not just "file exists" but "file says what it must".
    import re as _re
    def _read(name: str) -> str:
        if paths.rh_dir(root).exists():
            try:
                return paths.artifact_path(root, name).read_text(encoding="utf-8")
            except OSError:
                return ""
        return ""

    status_text = _read("STATUS.md")
    problem_text = _read("PROBLEM.md")
    purpose_ok = bool(_re.search(r"(?mi)^##\s+Purpose\b", problem_text))
    items.append({
        "id": "content-problem-purpose",
        "label": "PROBLEM.md starts with `## Purpose` (why this work: reference, data check, Q1, reproduction …)",
        "status": _due(purpose_ok, 1, current),
        "ref": "§3 phase 1",
        "detail": "" if purpose_ok else "ask the user why this work now, then record it under `## Purpose` before the question",
    })
    plan_text = _read("PLAN.md")
    lit_text = _read("LITERATURE.md")
    layout_text = _read("OUTPUT_LAYOUT.md")

    # `phase: **6 IMPLEMENT**` is as valid as `phase: 6 IMPLEMENT` — tolerate
    # markdown emphasis, and say which of the three parts is missing.
    header_parts = {
        "phase": r"phase:\s*\**[\d]+",
        "step": r"step:\s*\**\s*[^\s*|]+",
        "updated": r"updated:\s*\**\s*\S",
    }
    header_missing = [n for n, rx in header_parts.items()
                      if not (status_text and _re.search(rx, status_text, _re.IGNORECASE))]
    items.append({
        "id": "content-status-header",
        "label": "STATUS.md has the `phase: | step: | updated:` header (what agents read for state)",
        "status": _due(not header_missing, 5, current),
        "ref": "§5 STATUS.md",
        "detail": (f"header missing: {', '.join(header_missing)} — write `phase: <n NAME> | step: <id> | updated: <ISO>` "
                   "(markdown emphasis is fine)") if header_missing else "",
    })

    plan_steps = _re.findall(r"(?m)^###\s+(S\w+)", plan_text)
    if plan_steps:
        verify_ok = "verify:" in plan_text.lower()
        items.append({
            "id": "content-plan-verify",
            "label": f"Every PLAN.md step ({len(plan_steps)} found) names a verify command",
            "status": _due(verify_ok, 4, current),
            "ref": "§4 PLAN.md",
            "detail": "" if verify_ok else "PLAN.md has steps but no `verify:` line — a step without a check is not a step",
        })
    else:
        items.append({
            "id": "content-plan-verify",
            "label": "PLAN.md steps each name a verify command",
            "status": _due(False, 4, current),
            "ref": "§4 PLAN.md",
            "detail": "PLAN.md missing or has no `### S<N>` steps yet — plan gate (phase 4) not met",
        })

    if lit_text.strip():
        doi_ok = bool(_re.search(r"10\.\d{4,}/\S+", lit_text))
        items.append({
            "id": "content-lit-doi",
            "label": "Every LITERATURE.md entry carries a DOI (findings without a DOI cannot be cited)",
            "status": _due(doi_ok, 3, current),
            "ref": "§3 LITERATURE.md",
            "detail": "" if doi_ok else "LITERATURE.md has entries but no DOI line — add `DOI: 10.xxxx/...` per entry",
        })
    else:
        items.append({
            "id": "content-lit-doi",
            "label": "LITERATURE.md entries carry DOIs",
            "status": _due(False, 3, current),
            "ref": "§3 LITERATURE.md",
            "detail": "LITERATURE.md missing or empty — phase 3 not met",
        })

    if layout_text.strip():
        layouts = _re.findall(r"(?mi)^##\s+Our layout", layout_text)
        one_layout = len(layouts) == 1
        items.append({
            "id": "content-one-layout",
            "label": "OUTPUT_LAYOUT.md has exactly one `## Our layout`",
            "status": _due(one_layout, 3, current),
            "ref": "§3 OUTPUT_LAYOUT.md",
            "detail": "" if one_layout else f"found {len(layouts)} `## Our layout` headings (want exactly 1) — two layouts in the file is a defect",
        })
    else:
        items.append({
            "id": "content-one-layout",
            "label": "OUTPUT_LAYOUT.md has exactly one layout",
            "status": _due(False, 3, current),
            "ref": "§3 OUTPUT_LAYOUT.md",
            "detail": "OUTPUT_LAYOUT.md missing or empty (may be skipped if the output is not a manuscript/report)",
        })

    pending = [i for i in items if i["status"] == "pending"]
    return {
        "root": str(root),
        "phase": current,
        "phase_name": phase_name(current),
        "items": items,
        "pending": len(pending),
        "ok": len(pending) == 0,
    }


# --- the checklist as a file --------------------------------------------------

GROUPS = (
    ("setup", "Setup tasks"),
    ("phase", "Phase exit gates (SKILL.md §3)"),
    ("rule", "Never-miss rules (SKILL.md §0)"),
    ("content", "Content checks"),
)

_MARK = {"ok": "x", "pending": " ", "current": "~", "later": "·"}


def _group_of(item_id: str) -> str:
    if item_id.startswith("setup-"):
        return "setup"
    if item_id.startswith("phase-"):
        return "phase"
    if item_id.startswith("content-"):
        return "content"
    return "rule"


def render_markdown(data: dict) -> str:
    """Render the live checklist as `.rh/CHECKLIST.md`."""
    lines = [
        f"# Orchestrator checklist — {data['phase_name']}",
        "",
        f"root: {data['root']}",
        "",
        "Generated by `rh init`. Work it top to bottom; ask the user for every value you do not have.",
        "Tick each item as you finish it; STATUS.md remains the truth (§5).",
        "",
    ]
    for key, title in GROUPS:
        items = [i for i in data["items"] if _group_of(i["id"]) == key]
        if not items:
            continue
        lines += [f"## {title}", ""]
        for item in items:
            lines.append(f"- [{_MARK.get(item['status'], ' ')}] {item['label']}  ({item['ref']})")
            if item.get("detail"):
                lines.append(f"      {item['detail']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_checklist(root: Path, env: dict | None = None) -> tuple[Path, dict]:
    """Write `.rh/CHECKLIST.md` from live state; returns (path, checklist data).

    Called by `rh init`; the orchestrator reads the file itself (its system
    prompt points at it), so there is no separate CLI command for it.
    """
    data = build_checklist(root, env)
    dest = paths.checklist_md(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_markdown(data), encoding="utf-8")
    return dest, data
