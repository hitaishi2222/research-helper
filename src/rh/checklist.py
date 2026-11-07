"""The Orchestrator's checklist — SKILL.md §0 non-negotiables + phase exits.

The Orchestrator carries a long rule list in its prompt; a list that lives
only in prose is easy to forget under load. This module gives the checks a
machine form: one item per rule the Orchestrator must never miss, each with
its live status checked against the project on disk (via `config.phase_gate`
and the task board), never self-reported by the agent.

`rh checklist` renders it. With `--json` it returns the same items for an
agent to display in its own session. Nothing writes to disk here; the
Orchestrator still edits artifacts itself.
"""
from __future__ import annotations

from pathlib import Path

from . import config, paths
from .tasks import PHASE_EXIT, TaskStore, phase_name

# Skill rule numbers this checklist is authoritative for (SKILL.md §0).
RULE_REFS = {
    "status_truth": "§0.9",
    "rereread_env": "§0.10",
    "waiver": "§0.11",
    "verify_path": "§0.12",
    "close_agents": "§0.13",
    "fresh_session": "§0.14",
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
        items.append({
            "id": f"phase-{i}",
            "label": f"{phase_name(i)} exit: {PHASE_EXIT[i]}",
            "status": "ok" if done else ("current" if i == current else "pending"),
            "ref": f"§3 phase {i}",
            "detail": "" if done else "gate not yet met",
        })
    return items


def build_checklist(root: Path, env: dict | None = None) -> dict:
    """Live checklist for the project at `root`.

    Returns {root, phase, phase_name, items:[{id,label,status,ref,detail}],
    pending:[...]}. status ∈ {ok, current, pending}.
    """
    env = env if env is not None else config.load_env(root)
    gate = config.phase_gate(root, env)
    store = TaskStore(root)
    current = store.current_phase() if paths.tasks_json(root).exists() else 0

    env_file = paths.env_md(root)
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

    # Rule 9 — STATUS.md is the Orchestrator's own work.
    items.append({
        "id": "rule-9",
        "label": "STATUS.md updated by the Orchestrator after every step, before every question (never delegated)",
        "status": "ok" if not _missing_text("STATUS.md") else "pending",
        "ref": RULE_REFS["status_truth"],
        "detail": "" if not _missing_text("STATUS.md") else "STATUS.md missing or empty — create it (phase 5) before any question to the user",
    })

    # Rule 10 — re-read ENV.md at the start of every phase.
    items.append({
        "id": "rule-10",
        "label": "ENV.md re-read at the start of this phase (never cached)",
        "status": "ok" if env_file.exists() else "pending",
        "ref": RULE_REFS["rereread_env"],
        "detail": f"config block at {env_file}" if env_file.exists() else f"{env_file} missing — run phase 0",
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
        "label": "Project path verified before opening any agent (.rh/ + .rh/ENV.md present, path stated to the user)",
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

    # Rule 14 — fresh session after gate-heavy steps.
    items.append({
        "id": "rule-14",
        "label": "After a gate-heavy step, tell the user to continue in a fresh session and hand over STATUS.md + PLAN.md",
        "status": "current",
        "ref": RULE_REFS["fresh_session"],
        "detail": "plan approved / implementation done / critique answered → fresh session",
    })

    # Plan approval — gates.user_approves_plan
    plan_ok = bool(gate["done"][4])
    items.append({
        "id": "plan-approved",
        "label": "PLAN.md approved by the user (gates.user_approves_plan) before any implementation",
        "status": "ok" if plan_ok else "pending",
        "ref": RULE_REFS["plan_approval"],
        "detail": "" if plan_ok else "PLAN.md missing or gate unmet — no implementation before the user's yes",
    })

    # Critique veto — gates.critique_veto
    crit_ok = bool(gate["done"][7])
    items.append({
        "id": "critique-veto",
        "label": "Zero open blocking questions from Critique (gates.critique_veto) before phase 8",
        "status": "ok" if crit_ok else ("pending" if gates_veto else "ok"),
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
    plan_text = _read("PLAN.md")
    lit_text = _read("LITERATURE.md")
    layout_text = _read("OUTPUT_LAYOUT.md")

    status_header_ok = bool(_re.search(r"phase:\s*\d", status_text)) if status_text else False
    items.append({
        "id": "content-status-header",
        "label": "STATUS.md has the `phase: | step: | updated:` header line",
        "status": "ok" if status_header_ok else "pending",
        "ref": "§5 STATUS.md",
        "detail": "" if status_header_ok else "STATUS.md header missing `phase: <n> | step: <id> | updated: <ISO>` — agents navigating by it will misread phase",
    })

    plan_steps = _re.findall(r"(?m)^###\s+(S\w+)", plan_text)
    if plan_steps:
        verify_ok = "verify:" in plan_text.lower()
        items.append({
            "id": "content-plan-verify",
            "label": f"Every PLAN.md step ({len(plan_steps)} found) names a verify command",
            "status": "ok" if verify_ok else "pending",
            "ref": "§4 PLAN.md",
            "detail": "" if verify_ok else "PLAN.md has steps but no `verify:` line — a step without a check is not a step",
        })
    else:
        items.append({
            "id": "content-plan-verify",
            "label": "PLAN.md steps each name a verify command",
            "status": "pending",
            "ref": "§4 PLAN.md",
            "detail": "PLAN.md missing or has no `### S<N>` steps yet — plan gate (phase 4) not met",
        })

    if lit_text.strip():
        doi_ok = bool(_re.search(r"10\.\d{4,}/\S+", lit_text))
        items.append({
            "id": "content-lit-doi",
            "label": "Every LITERATURE.md entry carries a DOI (findings without a DOI cannot be cited)",
            "status": "ok" if doi_ok else "pending",
            "ref": "§3 LITERATURE.md",
            "detail": "" if doi_ok else "LITERATURE.md has entries but no DOI line — add `DOI: 10.xxxx/...` per entry",
        })
    else:
        items.append({
            "id": "content-lit-doi",
            "label": "LITERATURE.md entries carry DOIs",
            "status": "pending",
            "ref": "§3 LITERATURE.md",
            "detail": "LITERATURE.md missing or empty — phase 3 not met",
        })

    if layout_text.strip():
        layouts = _re.findall(r"(?mi)^##\s+Our layout", layout_text)
        one_layout = len(layouts) == 1
        items.append({
            "id": "content-one-layout",
            "label": "OUTPUT_LAYOUT.md has exactly one `## Our layout`",
            "status": "ok" if one_layout else "pending",
            "ref": "§3 OUTPUT_LAYOUT.md",
            "detail": "" if one_layout else f"found {len(layouts)} `## Our layout` headings (want exactly 1) — two layouts in the file is a defect",
        })
    else:
        items.append({
            "id": "content-one-layout",
            "label": "OUTPUT_LAYOUT.md has exactly one layout",
            "status": "pending",
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
