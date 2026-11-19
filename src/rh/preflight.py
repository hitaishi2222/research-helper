"""`rh preflight` — reconcile the three descriptions of a project's state.

A resumed session inherits the board (`.rh/tasks.json`), the narrative
(`STATUS.md`) and the artifacts, and they drift. This module compares them and
applies one precedence, so the Orchestrator fixes the source that lies instead
of guessing which one to believe.

Precedence: artifacts > STATUS.md > board and logs.

It never writes: fixing a source stays the Orchestrator's own work.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import agentstate, config, paths, statusmd
from .tasks import TaskStore, phase_name

PRECEDENCE = "artifacts > STATUS.md > board and logs"


def _task_time(value: str) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _deliverable_path(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def check(root: Path, env: dict | None = None) -> dict:
    """Every finding, the three sources, and which one to fix first."""
    env = env if env is not None else config.load_env(root)
    store = TaskStore(root)
    board = store.current_phase()
    gate = config.phase_gate(root, env)
    try:
        status_text = paths.artifact_path(root, "STATUS.md").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        status_text = ""
    header = statusmd.parse_header(status_text)
    waived_rules = statusmd.waivers(status_text)

    # The phase the artifacts actually support: the contiguous run of satisfied
    # artifact gates, not a claim. `done[i]` is set from files by phase_gate().
    artifact_phase = -1
    for i, done in enumerate(gate["done"]):
        if done:
            artifact_phase = i
        else:
            break

    findings: list[dict] = []

    def add(id_: str, severity: str, source: str, message: str, rule: int = 0):
        findings.append(
            {
                "id": id_,
                "severity": severity,
                "source": source,
                "message": message,
                "rule": rule,
                "waived": bool(rule) and rule in waived_rules,
            }
        )

    # 1. phase: board vs STATUS.md header, arbitrated by the artifacts
    if header["phase"] is None:
        add(
            "status-header",
            "error",
            "STATUS.md",
            "no `phase:` header — write `phase: <n NAME> | step: <id> | updated: <ISO>`",
            rule=9,
        )
    elif header["phase"] != board:
        if header["phase"] == artifact_phase and board != artifact_phase:
            fix = ".rh/tasks.json"
            why = "the artifacts support STATUS.md, not the board"
        elif board == artifact_phase and header["phase"] != artifact_phase:
            fix = "STATUS.md"
            why = "the artifacts support the board, not STATUS.md"
        else:
            fix = "both"
            why = (
                f"the artifacts support {phase_name(artifact_phase) if artifact_phase >= 0 else 'no phase yet'}"
            )
        add(
            "phase-disagreement",
            "error",
            fix,
            f"board says {phase_name(board)}, STATUS.md says "
            f"{phase_name(header['phase'])} — {why}; fix {fix} first",
            rule=9,
        )

    elif artifact_phase >= 0 and artifact_phase < board:
        # board and header agree, the artifacts do not back them: a forced skip
        # is allowed, but it is a waiver (rule 11), not a silent state.
        add(
            "artifacts-behind",
            "advisory",
            "artifacts",
            f"board and STATUS.md claim {phase_name(board)} but the artifacts reach "
            f"{phase_name(artifact_phase)} — a skipped gate is a rule-11 waiver",
            rule=11,
        )

    # 2. complete tasks must have their declared deliverable on disk, and it must
    #    not predate the task itself. No mtime heuristics beyond a declared file.
    undeclared: list[str] = []
    for task in store.list():
        if task.get("state") != "complete":
            continue
        deliverable = str(task.get("deliverable") or "").strip()
        if not deliverable:
            undeclared.append(str(task["id"]))
            continue
        path = _deliverable_path(root, deliverable)
        if not path.exists():
            add(
                f"deliverable-missing:{task['id']}",
                "error",
                "artifacts",
                f"{task['id']} is complete but {deliverable} does not exist",
                rule=7,
            )
            continue
        claimed = _task_time(task.get("updated_at") or "")
        if claimed is not None and path.stat().st_mtime < claimed:
            add(
                f"deliverable-stale:{task['id']}",
                "error",
                "artifacts",
                f"{task['id']} is complete but {deliverable} predates the task — "
                "regenerate it or reopen the task",
                rule=7,
            )
    if undeclared:
        add(
            "deliverable-undeclared",
            "advisory",
            "board",
            "complete without a declared deliverable: " + ", ".join(undeclared),
        )

    # 3. a `working` task needs an agent open behind it, and an open agent needs
    #    a working task; either alone means "unreported work" or "stale spawn".
    open_agents = agentstate.open_records(root)
    open_roles = {str(r.get("role") or "") for r in open_agents}
    working = [t for t in store.list() if t.get("state") == "working"]
    working_owners = {str(t.get("owner") or "") for t in working}
    for task in working:
        if str(task.get("owner") or "") not in open_roles:
            add(
                f"working-without-agent:{task['id']}",
                "advisory",
                "board",
                f"{task['id']} is working but no agent is open for role "
                f"{task.get('owner') or '?'}",
                rule=13,
            )
    for rec in open_agents:
        if str(rec.get("role") or "") not in working_owners:
            add(
                f"agent-without-task:{rec.get('name')}",
                "advisory",
                "board",
                f"{rec.get('name')} is open but no {rec.get('role') or '?'} task is "
                "working — unreported work, or a spawn to close",
                rule=13,
            )

    errors = [f for f in findings if f["severity"] == "error" and not f["waived"]]
    fix_first = errors[0]["source"] if errors else ""
    return {
        "root": str(root),
        "precedence": PRECEDENCE,
        "sources": {
            "board": {"phase": board, "phase_name": phase_name(board)},
            "status": header,
            "artifacts": {
                "phase": artifact_phase,
                "phase_name": phase_name(artifact_phase) if artifact_phase >= 0 else "",
            },
        },
        "waived_rules": sorted(waived_rules),
        "findings": findings,
        "fix_first": fix_first,
        "ok": not errors,
    }
